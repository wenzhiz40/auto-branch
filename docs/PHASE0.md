# Phase 0: Platform Verification

## Environment

- Codex CLI: `codex-cli 0.170.0`
- Claude Code: `2.1.325`

## Verified

- Codex exposes interactive `fork` and `resume` commands.
- Codex exposes non-interactive `codex exec fork` and `codex exec resume`; both accept a session ID and prompt, and support `--json`.
- Claude Code exposes `--resume` and `--fork-session`.
- Claude Code supports `--print --output-format json`; an invalid session ID fails before model execution with `No conversation found with session ID ...`.
- Codex app-server can complete the `initialize` and `thread/start` handshake in an isolated `CODEX_HOME`.
- Codex app-server exposes `thread/fork` and returns a thread object containing an ID and `forkedFromId` in its generated protocol schema.
- A Codex app-server fork of an empty thread is rejected with `no rollout found for thread id ...`; a persistent session with an existing rollout is required for a real fork test.

## Not Yet Verified

- Codex `exec fork --json` output shape for the newly created session ID. The current sandbox rejected the probe before session lookup because the project was untrusted/read-only for Codex initialization.
- Whether the current native Codex/Claude session can be paused before the prompt is delivered by a hook. The wrapper remains the supported routing surface.
- End-to-end prompt delivery exactly once after a successful native fork.

## Live Probe Attempt (2026-11-20)

- A disposable Codex `CODEX_HOME` inside the workspace created parent and child thread IDs using the configured custom provider. Neither turn returned within 90 seconds, so there was no completed assistant response and no valid rollout for resume verification. The incomplete temporary state was removed.
- A Claude Code live probe was blocked by configuration isolation: `CLAUDE_CONFIG_DIR` points to a directory that lacks the user's authenticated config, while using the existing user config would write session state under the read-only `~/.claude` tree.
- Codex reports no official account login; the only available provider is the user's custom provider. Its turn did not complete in the restricted sandbox.
- No completed model turn or resumable test conversation was produced. Do not report live fork/resume or exactly-once delivery as passed.
- Further live testing requires a runtime that can reach the configured provider and write to a disposable session store. This workspace sandbox does not permit changing those permissions.

## User-Run Codex End-to-End Probe (2026-11-20)

The live probe was run from a disposable temporary directory using a locally configured Codex CLI. All three completed successfully:

- Parent: a disposable thread returned `PARENT_READY`.
- Fork: a new child thread returned `CHILD_READY`.
- Resume: returned `RESUME_OK` on the same child thread ID.
- Each invocation emitted one `turn.started` and one `turn.completed`; the supplied prompt was delivered once per invocation.
- A non-fatal MCP `AuthRequired` diagnostic was emitted, but the assistant turn completed. This is an auxiliary MCP authentication issue, not a fork/resume failure.

**Codex end-to-end status: PASS** for parent creation, native fork, child ID capture, resume, and one completed turn per submitted prompt.

## User-Run Claude Code End-to-End Probe (2026-11-20)

The live probe was run in a disposable Claude Code project after removing the variadic `--add-dir` argument that had consumed the prompt:

- Parent: a disposable session returned `PARENT_READY`.
- Fork: a new child session returned `CHILD_READY`.
- Resume: returned `RESUME_OK` on the same child session ID.
- The first Claude command's assistant response differed from the literal requested string, but the session was created successfully. Fork and resume returned their requested markers.

Claude Code also printed an Auto Mode classifier billing notice from the configured gateway. The CLI continued and all three model turns completed. This is unrelated to Auto-Branch topic classification.

**Claude Code end-to-end status: PASS** for parent creation, native fork, child ID capture, and resume. The adapter must surface stderr notices without treating a nonzero-looking warning line as a failed turn; process exit code and structured JSON result remain authoritative.

## Wrapper Implementation Status

The MVP now includes `auto-branch prompt` and `bind-session`:

- `bind-session` associates an existing native session ID with a logical branch without sending a Prompt.
- The first `prompt` on a logical branch without a native ID starts a native session and binds the returned ID.
- A continuation calls native resume once.
- A confirmed suggested branch calls native fork once, registers the returned child ID, creates the logical child branch, and switches to it.
- If the native process exits ambiguously but returns a session ID, Auto-Branch preserves that ID and does not retry the Prompt.
- Core and fake-process wrapper tests pass. Live wrapper execution through the user's ccswitch environment remains a user-side smoke test because this sandbox cannot complete those model calls.

## User-Run Wrapper Smoke Test (2026-11-20)

- Claude wrapper start passed: a disposable session returned `CLAUDE_PARENT_READY` with exit code 0.
- Codex wrapper start passed: a disposable thread returned `WRAPPER_PARENT_READY` with exit code 0.
- Codex wrapper resume passed on the same thread ID and returned `WRAPPER_RESUME_OK` with exit code 0.
- Codex emitted non-fatal MCP transport/auth diagnostics during both turns; the structured turn completion and exit code remained successful.
- Codex confirmation-first fork was invoked with `--confirm`; final child registration/output remains pending until the command returns. The user must not replay the same prompt while it is running.
- The fork completed: a logical child branch was created with a native child thread under the disposable mainline thread.
- The real wrapper fork path is therefore verified through child creation and native session ID registration. The remaining smoke step is resume inside that child and then logical `rejoin`.
- The remaining smoke step also completed: child resume returned `CHILD_RESUME_OK` on the same native thread, and `rejoin` created an adoption record with active route returned to `mainline`.
- The child resume reported approximately 74K input tokens. This confirms that native fork/resume preserves substantial inherited context and makes context trimming a priority before frequent automatic branching.

## Context Budget Follow-up

The wrapper now supports `--branch-mode seeded`. Native mode keeps the verified platform fork behavior. Seeded mode starts a fresh native session with the `Branch Context` package and current Prompt, then registers it as a logical child. The inherited summary is capped at 12,000 characters. It is intentionally labeled as a new context-seeded session, not a transcript fork.

Live measurement passed: the user's seeded Codex turn used approximately 18.6K input tokens, compared with approximately 74.1K on native child resume (about 75% fewer input tokens). This is a single-run comparison, not a universal savings guarantee; the fresh session still includes the configured Codex/system context.

## Adapter Decision

- Default headless Codex command: `codex exec fork <session-id> <prompt> --json`.
- Default headless Codex resume command: `codex exec resume <session-id> <prompt> --json`.
- Default headless Claude fork command: `claude --resume <session-id> --fork-session --print --output-format json <prompt>`.
- Default headless Claude resume command: `claude --resume <session-id> --print --output-format json <prompt>`.
- Interactive commands remain available through adapter `headless=False`, but they are not suitable for an unattended wrapper because they require a terminal.
- Adapters extract a session/thread ID from JSON or JSONL output and fail clearly if the output contains no ID.

## Next Safe Test

Run an integration test with a disposable, already-persisted session created specifically for this project. The test must capture the new native session ID, verify one prompt delivery, and write the resulting session mapping into a temporary Auto-Branch data directory. Do not use a user's research session for this test.
