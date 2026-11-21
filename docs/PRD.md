# PRD: Auto-Branch

## 1. Summary

Auto-Branch is a local-first CLI companion that classifies a new prompt against the current conversation topic and helps the user keep unrelated work in separate, resumable sessions. The first release targets Codex CLI and Claude Code, but keeps classification, branch metadata, and memory management independent of either platform.

The first release uses **suggest mode**: Auto-Branch classifies a prompt and asks the user before creating a branch. A user can also explicitly force continuation or branching. Automatic routing without confirmation is deferred until the routing path is proven reliable.

## 2. Problem Statement

Long-running research and development sessions accumulate unrelated questions. This makes the active context harder to navigate and increases the risk that a new topic pollutes the existing conversation. Users need a low-friction way to separate topics, return to prior work, and preserve useful conclusions without silently losing or rewriting conversation history.

## 3. Target Users

- Users who conduct multi-session research, learning, or software development with Codex CLI or Claude Code.
- Users who want topic separation but need explicit control over when a branch is created or its conclusions are adopted.

## 4. Goals and Success Criteria

- Classify a prompt as same-topic, related-but-separable, unrelated, or uncertain using the current branch summary and recent relevant context.
- In suggest mode, ask before creating a branch; never route a prompt away from the current session without confirmation.
- Create and resume platform-native sessions using documented CLI entry points, while storing a platform-independent branch tree locally.
- Let users adopt a branch back into the mainline memory without deleting the branch or rewriting native session history.
- Preserve a traceable record of classification, user choice, session IDs, and branch adoption actions.
- Run core metadata, decision, and memory tests without requiring either CLI or an LLM provider.

## 5. Non-Goals

- Physically merging or rewriting Codex and Claude Code transcript histories.
- Treating Claude Code subagents as user-resumable conversation branches.
- Modifying undocumented CLI databases, transcript formats, or internal session files.
- Automatically creating branches on every topic change.
- Building a vector database, knowledge graph, web UI, or multi-agent orchestration system in the MVP.
- Guaranteeing that a hook can switch the currently open native TUI to another session.

## 6. Assumptions

- The initial implementation is a local Python 3.11+ application with SQLite metadata and Markdown summaries.
- The user invokes Auto-Branch through its CLI/wrapper, or uses a supported hook only for classification, confirmation, or blocking. Native CLI hooks are not assumed to provide session-switching semantics.
- A classification provider may be configured separately. Prompt content sent to an external provider is disclosed and configurable; an offline/manual path remains available.
- “Mainline” is an Auto-Branch logical branch, not a special session type understood by the underlying CLIs.
- Branch adoption means updating mainline memory and routing state, not moving or deleting messages in the native session transcript.

## 7. User Stories / Primary Workflows

### 7.1 Continue the current topic

1. The user submits a prompt through Auto-Branch.
2. Auto-Branch classifies it as SAME or related-but-not-worth-separating.
3. Auto-Branch submits it to the current native session and records the decision.

### 7.2 Confirm a suggested branch

1. The user submits a prompt that appears unrelated or independently actionable.
2. Auto-Branch displays the current topic, proposed branch title, and concise reason.
3. The user confirms; Auto-Branch forks/resumes the appropriate native session using the platform adapter and submits the original prompt exactly once.
4. Auto-Branch records the new branch and native session ID.

### 7.3 Reject a suggested branch

1. Auto-Branch suggests a branch.
2. The user chooses “continue here”.
3. Auto-Branch sends the prompt to the current session and records the override, which can inform future tuning but does not silently train a model.

### 7.4 Adopt branch conclusions into mainline

1. The user runs a command such as `auto-branch adopt <branch>` or selects “adopt into mainline” from the confirmation prompt.
2. Auto-Branch generates or displays a proposed adoption note containing the branch question, conclusions, unresolved issues, and source branch/session reference.
3. The user reviews and confirms the note.
4. Auto-Branch appends the confirmed note to mainline memory, marks the branch as adopted (with timestamp and adopted revision), and leaves the branch session intact.
5. The original branch remains independently resumable. `adopt` alone does not change the active route; the user can separately switch to mainline. Use `rejoin` when the intent is to return routing to mainline.

### 7.5 Rejoin an accidentally branched conversation

1. The user runs `auto-branch rejoin <branch-id>`.
2. Auto-Branch previews the branch summary and the mainline memory update, including the source session reference.
3. The user confirms; Auto-Branch adds a revisioned conversation summary to mainline memory, marks the branch as rejoined, and changes the active logical route to the mainline session.
4. The branch and its native session remain available for resume/audit. Native transcript messages are not physically moved into the mainline session. If exact turn-by-turn context is needed, the user resumes the source session or explicitly includes an exported transcript/context in a later version.

## 8. Functional Requirements

- **FR-1 Classification:** Input includes prompt text, active branch ID, branch/mainline summaries, and a bounded set of recent relevant turns when available. Output is validated structured data: relationship, proposed action, confidence, reason, and whether context inheritance is recommended.
- **FR-2 Explicit intent precedence:** Explicit commands such as “continue here”, “new branch”, “switch to …”, “adopt … into mainline”, and “rejoin …” override model classification.
- **FR-3 Suggest-mode confirmation:** An unrelated/uncertain prompt must not be sent to another session until the user confirms. Decline, timeout, or classifier failure defaults to continuing in the current session or asks the user; it never silently branches.
- **FR-4 Branch lifecycle:** Create, list, inspect, resume, archive, adopt, and rejoin operations are available through the Auto-Branch CLI. A branch has a stable Auto-Branch ID and optional native session ID.
- **FR-5 Adapter capability reporting:** Each adapter declares supported capabilities, including fork-from-session, resume-by-ID, pre-submit interception, and session metadata. Unsupported operations fail clearly and do not create an orphan branch record.
- **FR-6 Context package:** A created branch receives a bounded context package containing original goal, relevant summary, current prompt, preferences explicitly available to Auto-Branch, and constraints. It does not copy full history by default.
- **FR-7 Adoption:** Adoption is an explicit, reviewable memory operation. It appends a versioned note to mainline memory, preserves the source branch, and records provenance. It does not rewrite native transcripts or imply that the conversation was physically merged.
- **FR-7a Rejoin:** A user-confirmed rejoin operation adds a revisioned summary of the branch to mainline memory, marks the branch as rejoined, and routes subsequent prompts to the mainline session. It preserves the source branch and native session ID; it does not physically merge native transcripts.
- **FR-8 Idempotency:** Retrying a create, route, or adoption operation must not submit the same prompt twice or append the same adoption revision twice. Operations use stable request/operation IDs.
- **FR-9 Auditability:** Record prompt-routing decisions, user overrides, native command outcomes, branch state changes, and adoption provenance. Do not log secrets; prompt logging is configurable and off by default beyond the minimal data needed for operation.
- **FR-10 Safe failure:** If classifier, adapter, or persistence operations fail, preserve the user's prompt and show the failure. Do not silently discard input or claim a branch exists when native session creation failed.
- **FR-11 Native execution safety:** Native commands have a configurable timeout, receive Prompt content through stdin where supported, and record `delivery_unknown` when a session ID exists but the native process exits unsuccessfully. Auto-Branch never retries an ambiguous Prompt delivery.
- **FR-12 Routing audit:** A routing event records the operation ID, user choice, executed action, native session ID, exit code, and delivery status after native execution completes.
- **FR-13 Concurrency:** Prompt routing serializes operations per data directory so concurrent wrappers cannot silently overwrite the active logical branch.

## 9. Non-Functional Requirements

- **NFR-1 Reliability:** The default behavior on uncertainty or integration error is non-destructive continuation or an explicit user choice.
- **NFR-2 Privacy:** Data remains local except text explicitly sent to a configured classifier. Users can select manual classification and disable prompt-content logging.
- **NFR-3 Compatibility:** Use documented CLI commands and version/capability checks. Adapter tests must cover supported versions and fail closed on unrecognized behavior.
- **NFR-4 Portability:** Core decision logic and SQLite schema do not import platform-specific adapter modules.
- **NFR-5 Recoverability:** Branch metadata and memory are durable across process restarts; archive and adoption/rejoin are reversible or append-only where practical.
- **NFR-6 Cost/latency:** Rule-based explicit-intent handling occurs before any model call. Classification has configurable provider, timeout, and maximum context size.

## 10. UX / API / Interface Requirements

Initial command surface:

```text
auto-branch run --platform codex|claude [--mode suggest|manual|disabled]
auto-branch list [--tree]
auto-branch show <branch-id>
auto-branch switch <branch-id>
auto-branch adopt <branch-id> [--preview]
auto-branch rejoin <branch-id> [--preview]
auto-branch archive <branch-id>
```

- Default mode is `suggest`.
- A branch suggestion shows the proposed title, relation, brief reason, and clear choices: branch, continue here, or cancel.
- `adopt` always previews the proposed memory change before writing unless the user explicitly opts into a documented non-interactive confirmation flag.
- `rejoin` previews the summary, mainline memory revision, and routing change; confirmation is required. The UI must state that the original native transcript remains separate.
- If a platform cannot create a native fork, offer a new session seeded with the context package only when the user confirms; label it as a new session, not a fork.
- Avoid changing existing CLI configuration automatically. Setup prints the exact opt-in configuration and supports uninstall/disable instructions.

## 11. Data Model / State Changes

Minimum SQLite entities:

- `branches`: stable ID, parent ID, title, topic, platform, native session ID, status, created/updated timestamps, summary revision, adopted revision.
- `routing_events`: operation ID, branch ID, relationship, proposed action, confidence, reason, user choice, adapter result, timestamp.
- `adoptions`: adoption ID, source branch ID/revision, target mainline ID, operation kind (`findings` or `rejoin`), appended memory revision, prior/new active route, user confirmation, timestamp.

Memory files:

- `global.md`: user/project facts intentionally shared across branches.
- `mainline.md`: mainline goal and confirmed adopted notes.
- Per-branch summary: branch goal, key conclusions, open questions, and native session reference.

Adoption should be append-only or revisioned. Editing/removing an adopted note must preserve provenance and avoid deleting the source branch summary.

## 12. Permissions, Privacy, and Security

- Require explicit user confirmation before sending the current prompt to a newly created branch in suggest mode.
- Explain which prompt/context fields are sent to an external classification provider; support local/manual mode.
- Treat stored prompt content and summaries as potentially sensitive. Apply restrictive file permissions where supported and never include API keys in logs or metadata.
- Do not run arbitrary shell fragments from config or classifier output. Adapter commands use argument arrays and validated session IDs.

## 13. Edge Cases and Failure Modes

- The user rejects a branch suggestion: submit the prompt once to the current session.
- The user confirms a branch but native fork fails: retain the prompt, report failure, and offer continue-here or start-new-session with context.
- Prompt was already submitted before routing: mark it as not rerouted; do not replay it automatically.
- The chosen branch is archived or its native session is unavailable: report state and offer a new context-seeded session without overwriting the old record.
- Classifier times out, returns invalid JSON, or returns low confidence: no automatic branch.
- Adoption is repeated: deduplicate by source branch revision and adoption operation ID.
- Mainline memory changed after the preview: detect stale revision and require a refreshed preview.
- User resumes a child branch after adoption: keep it valid; adoption is a snapshot, not a lock or destructive move.
- Two CLI sessions run concurrently: preserve distinct native session IDs and record which logical branch each belongs to; do not infer “current” solely from most-recently-used global state.

## 14. Risks

- **Pre-submit routing:** Native hooks may not support switching an active TUI session. The wrapper is the primary MVP routing surface; hook-only mode must not claim transparent routing.
- **Platform divergence:** Fork and resume semantics differ. Adapters must expose capability differences instead of promising identical behavior.
- **Classifier mistakes:** False-positive branches add friction. Suggest mode, explicit overrides, uncertainty handling, and evaluation cases mitigate this.
- **Context quality:** Summary-only context can omit needed details. Include user-approved relevant context and let the user preview it before branching.
- **Adoption pollution:** Incorrect conclusions could contaminate mainline memory. Preview, confirmation, source provenance, and revisioning are required.
- **Duplicate prompt delivery:** A failure between native session creation and prompt submission can cause retries. Use operation IDs and explicit delivery state.

## 15. Acceptance Criteria

- **AC-1:** SAME prompts route to the current session in suggest mode without asking to branch.
- **AC-2:** UNRELATED prompts produce a proposal; no other session is created and no prompt is sent there before confirmation.
- **AC-3:** Declining a proposal delivers the prompt to the current session exactly once.
- **AC-4:** Confirming a supported fork creates a branch record with parent, platform, and native session ID, and delivers the prompt exactly once.
- **AC-5:** An adapter that lacks native fork capability reports that limitation and offers a distinctly labeled new-session fallback only after confirmation.
- **AC-6:** `list`, `show`, `switch`, and `archive` persist correctly across application restarts.
- **AC-7:** Adopting a branch previews a note, requires confirmation, updates mainline memory with source provenance, records a revision, and leaves source branch/session intact.
- **AC-8:** Repeating the same adoption operation does not duplicate the mainline note.
- **AC-8a:** Rejoining a branch requires confirmation, appends a provenance-linked summary, changes the active logical route to mainline, and preserves the original native session for later resume.
- **AC-8b:** The rejoin UI and documentation explicitly state that native transcript messages are not physically merged.
- **AC-9:** Classifier/API/adapter failure never loses the prompt or silently routes it elsewhere.
- **AC-10:** Core tests run without network access; adapter contract tests can run with fake CLI executables.

## 16. Implementation Outline

### Phase 0: Platform proof of capability

- Verify exact fork/resume invocation, output/session-ID capture, prompt delivery, and non-interactive behavior for supported Codex CLI and Claude Code versions.
- Prototype wrapper routing for each platform. Confirm that the current prompt can be held until the user's choice and delivered once to the selected session.
- Decide supported adapter capability matrix from observed/documented behavior. Do not modify internal session stores.

### Phase 1: Local core MVP

- Python package and CLI.
- SQLite schema, branch tree, state transitions, operation IDs.
- Classifier protocol with deterministic fake/manual provider and optional LLM provider.
- Suggest-mode decision flow and context preview.
- Mainline memory and branch summaries.
- Adoption preview, confirmation, append, and provenance.

### Phase 2: Platform adapters

- Codex wrapper adapter and documented fork/resume commands.
- Claude Code wrapper adapter and documented resume/fork-session commands.
- Capability checks and fake-executable contract tests.

### Phase 2a: Headless prompt wrapper

- Provide `auto-branch prompt --platform codex|claude --prompt ...` as the primary live-routing entry point.
- Bind the first successful native session to the active logical branch.
- Resume SAME/RELATED prompts in the active native session.
- Require confirmation for suggested forks; register the returned child session ID before switching the active logical branch.
- Never automatically retry a native command after an ambiguous transport failure.
- Keep interactive TUI interception out of this phase; it requires separate hook behavior verification.

### Phase 3: Pilot and evaluation

- Evaluate representative same/related/unrelated/uncertain prompts.
- Measure false branch suggestions, user override rate, duplicate delivery, and routing latency.
- Keep auto mode disabled until pilot evidence supports a threshold and rollback behavior.

## 17. Open Questions

- **Non-blocking:** Should mainline adoption append only a concise conclusion note, or also include selected verbatim turns? MVP should default to a summary with links/IDs and avoid copying full transcripts.
- **Non-blocking:** Which classifier providers are supported in the first implementation? Keep provider interface pluggable; initially manual mode plus one configured provider is sufficient.
- **Non-blocking:** Should branch archive hide it from default listings or only mark status? Default: hide archived branches unless requested.
- **Blocking before adapter implementation:** What exact Codex CLI and Claude Code version range will be supported? Phase 0 should establish and document the initial tested versions.
- **Blocking before unattended automation:** What measured false-positive rate and confirmation/rollback UX are acceptable for a future auto mode? Auto mode remains out of MVP until decided.

## 18. Suggested Next Step

Run Phase 0 as a small technical spike against the installed Codex CLI and Claude Code versions. Verify fork/resume invocation and wrapper prompt delivery before implementing adapters. Then convert Phases 1–3 into execution issues and implement the local core first.
