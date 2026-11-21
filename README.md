# Auto-Branch

Auto-Branch is a confirmation-first local conversation branch manager for Codex CLI and Claude Code.

## Current MVP

- SQLite branch tree and active-branch tracking.
- Markdown memory for mainline and branches.
- Conservative offline prompt classification fallback.
- `suggest` decision mode with explicit `adopt` and `rejoin` operations.
- Safe headless Codex/Claude command construction without touching native session stores.
- Headless `prompt` wrapper for starting, resuming, and confirmation-first forking native sessions.

## Quick Start

From the repository directory, create the local environment once:

```bash
cd /path/to/Auto-Branch
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --no-deps --no-build-isolation --editable .
source .venv/bin/activate
```

The `--system-site-packages` flag keeps installation offline-friendly on machines where build dependencies are already provided by the system Python. After activation, `auto-branch` and `python3 -m auto_branch` work from any directory.

Initialize a data directory and configure the mainline:

```bash
auto-branch --data-dir ~/.auto-branch init
auto-branch --data-dir ~/.auto-branch set-topic mainline "Flow Matching research"
auto-branch --data-dir ~/.auto-branch set-summary mainline "Probability paths, velocity fields, and ODE solvers."
auto-branch --data-dir ~/.auto-branch list
auto-branch --data-dir ~/.auto-branch route --prompt "Ubuntu 怎么安装 Zotero？"
auto-branch --data-dir ~/.auto-branch create "Ubuntu Zotero" --topic "Ubuntu software installation" --platform codex --summary "Installation findings."
```

The `create` command prints JSON. Copy the value of its `id` field and use that actual value in later commands; do not type `<branch-id>` literally because Bash treats angle brackets as redirection syntax:

```bash
auto-branch --data-dir ~/.auto-branch show BRANCH_ID
auto-branch --data-dir ~/.auto-branch switch BRANCH_ID
auto-branch --data-dir ~/.auto-branch rejoin BRANCH_ID --yes
```

For a one-off invocation without activating the environment, replace `auto-branch` with `<project-root>/.venv/bin/auto-branch`.

## Native Session Routing

The first call starts a native session and binds its returned session ID to `mainline`:

```bash
auto-branch --data-dir ~/.auto-branch prompt \
  --platform codex \
  --prompt "Reply with exactly: MAINLINE_READY. Do not use tools."
```

After that, normal continuation resumes the bound session:

```bash
auto-branch --data-dir ~/.auto-branch prompt \
  --platform codex \
  --prompt "Continue the current Flow Matching discussion."
```

For an unrelated prompt, `suggest` mode asks before forking. In a script or a reviewed one-shot command, pass `--confirm` to accept the suggested fork:

```bash
auto-branch --data-dir ~/.auto-branch prompt \
  --platform codex \
  --confirm \
  --prompt "Open a new unrelated topic about Ubuntu package management."
```

By default, a confirmed branch uses `--branch-mode native`, which preserves the native platform history. When the parent history is large, use `--branch-mode seeded` to create a new native session containing only a bounded Auto-Branch context package and the current Prompt:

```bash
auto-branch --data-dir ~/.auto-branch prompt \
  --platform codex \
  --confirm \
  --branch-mode seeded \
  --prompt "Open a new unrelated topic about Ubuntu package management."
```

The result reports `branch_mode: seeded`; this is a new session seeded with context, not a native transcript fork.

The same flow works with `--platform claude`. The wrapper invokes the headless commands, parses the returned native session ID, writes it to the branch tree, and never retries a failed native command automatically because the Prompt may already have been delivered.

`--mode manual` only classifies and does not invoke Codex or Claude. `--mode auto` skips confirmation for a high-confidence unrelated classification; it is opt-in and is not the default. The wrapper is a one-shot/headless entry point; it does not intercept text typed into an already-running interactive TUI.

The default data directory is `.auto-branch`. Use `--data-dir` to choose another local directory.

## Branch Return Semantics

`adopt` adds a versioned branch summary to mainline memory but leaves the active route unchanged. `rejoin` does the same and switches the active logical route to `mainline`. Neither operation rewrites or physically merges native Codex/Claude transcripts; the source branch remains resumable and auditable.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The native CLI wrapper is intentionally not executed by the core tests. The current adapter uses `codex exec fork/resume --json` for headless Codex routing and `claude --print --resume --fork-session --output-format json` for headless Claude routing. Live routing still requires a valid persistent session and must be enabled only after version-specific integration tests.
