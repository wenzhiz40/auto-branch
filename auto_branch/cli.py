from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import ClaudeAdapter, CodexAdapter
from .decision import DecisionMode
from .prompt_runner import PromptRunner
from .service import AutoBranchService


def _service(args: argparse.Namespace) -> AutoBranchService:
    return AutoBranchService(Path(args.data_dir).expanduser())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="auto-branch")
    parser.add_argument("--data-dir", default=".auto-branch")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init")

    route = sub.add_parser("route")
    route.add_argument("--prompt", required=True)
    route.add_argument("--mode", choices=[mode.value for mode in DecisionMode], default="suggest")

    listing = sub.add_parser("list")
    listing.add_argument("--all", action="store_true")

    show = sub.add_parser("show")
    show.add_argument("branch_id")

    topic = sub.add_parser("set-topic")
    topic.add_argument("branch_id")
    topic.add_argument("topic")

    summary = sub.add_parser("set-summary")
    summary.add_argument("branch_id")
    summary.add_argument("summary")

    create = sub.add_parser("create")
    create.add_argument("title")
    create.add_argument("--topic", required=True)
    create.add_argument("--platform", choices=["codex", "claude", "logical"], default="logical")
    create.add_argument("--session-id")
    create.add_argument("--summary", default="")

    switch = sub.add_parser("switch")
    switch.add_argument("branch_id")

    bind = sub.add_parser("bind-session")
    bind.add_argument("branch_id")
    bind.add_argument("platform", choices=["codex", "claude"])
    bind.add_argument("session_id")

    prompt = sub.add_parser("prompt")
    prompt.add_argument("--platform", choices=["codex", "claude"], required=True)
    prompt.add_argument("--prompt", required=True)
    prompt.add_argument("--mode", choices=[mode.value for mode in DecisionMode], default="suggest")
    prompt.add_argument("--confirm", action="store_true", help="confirm a suggested route without prompting")
    prompt.add_argument(
        "--branch-mode",
        choices=["native", "seeded"],
        default="native",
        help="native forks full history; seeded starts a new session with bounded Auto-Branch context",
    )
    prompt.add_argument("--timeout", type=float, default=300.0, help="native CLI timeout in seconds")

    archive = sub.add_parser("archive")
    archive.add_argument("branch_id")

    for name in ("adopt", "rejoin"):
        command = sub.add_parser(name)
        command.add_argument("branch_id")
        command.add_argument("--yes", action="store_true", help="confirm the displayed memory update")

    adapter = sub.add_parser("adapter-command")
    adapter.add_argument("platform", choices=["codex", "claude"])
    adapter.add_argument("action", choices=["fork", "resume"])
    adapter.add_argument("session_id")
    adapter.add_argument("--prompt")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    service = _service(args)

    if args.command == "init":
        print(f"initialized {service.data_dir}")
    elif args.command == "route":
        print(json.dumps(service.route(args.prompt, DecisionMode(args.mode)).as_dict(), ensure_ascii=False, indent=2))
    elif args.command == "list":
        active_id = service.storage.active_branch_id()
        branches = service.storage.list_branches(args.all)
        for branch in branches:
            branch["is_active"] = branch["id"] == active_id
        print(json.dumps(branches, ensure_ascii=False, indent=2))
    elif args.command == "show":
        branch = service.storage.get_branch(args.branch_id)
        if branch is None:
            parser.error(f"branch does not exist: {args.branch_id}")
        print(json.dumps(branch, ensure_ascii=False, indent=2))
    elif args.command == "set-topic":
        service.set_topic(args.branch_id, args.topic)
        print(f"topic updated: {args.branch_id}")
    elif args.command == "set-summary":
        revision = service.set_summary(args.branch_id, args.summary)
        print(f"summary updated: {args.branch_id} (revision {revision})")
    elif args.command == "create":
        print(json.dumps(service.create_branch(title=args.title, topic=args.topic, platform=args.platform, native_session_id=args.session_id, summary=args.summary), ensure_ascii=False, indent=2))
    elif args.command == "switch":
        service.switch(args.branch_id)
        print(f"active branch: {args.branch_id}")
    elif args.command == "bind-session":
        service.bind_session(args.branch_id, args.platform, args.session_id)
        print(f"bound {args.platform} session {args.session_id} to {args.branch_id}")
    elif args.command == "prompt":
        if DecisionMode(args.mode) == DecisionMode.MANUAL:
            print(json.dumps(service.route(args.prompt, DecisionMode.MANUAL).as_dict(), ensure_ascii=False, indent=2))
            return 0
        try:
            result = PromptRunner(service, timeout=args.timeout).run(
                platform=args.platform,
                prompt=args.prompt,
                mode=DecisionMode(args.mode),
                confirm=args.confirm,
                branch_mode=args.branch_mode,
            )
        except Exception as exc:
            parser.error(str(exc))
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)
        print(json.dumps({
            "action": result.action,
            "branch_id": result.branch_id,
            "session_id": result.session_id,
            "returncode": result.returncode,
            "branch_mode": result.branch_mode,
            "delivery_status": result.delivery_status,
            "stdout": result.stdout,
        }, ensure_ascii=False, indent=2))
        if result.returncode != 0:
            print("Native CLI exited unsuccessfully. The session ID was saved when available; do not replay the prompt automatically.", file=sys.stderr)
            return result.returncode
    elif args.command == "archive":
        service.archive(args.branch_id)
        print(f"archived: {args.branch_id}")
    elif args.command in {"adopt", "rejoin"}:
        branch = service.storage.get_branch(args.branch_id)
        if branch is None:
            parser.error(f"branch does not exist: {args.branch_id}")
        summary = branch["summary"] or service.memory.read_branch_summary(args.branch_id, "(no summary recorded)")
        print(f"Operation: {args.command}")
        print(f"Source: {branch['title']} ({args.branch_id})")
        print(f"Target: mainline memory")
        print(f"Summary revision: {branch['summary_revision']}\n")
        print(summary)
        if args.command == "rejoin":
            print("\nAfter confirmation, future routing returns to mainline. Native transcript remains separate.")
        else:
            print("\nAfter confirmation, current routing stays on its existing branch.")
        if not args.yes:
            if not sys.stdin.isatty():
                parser.error("confirmation required in non-interactive mode; pass --yes after reviewing the preview")
            answer = input("\nApply this memory update? [y/N] ").strip().lower()
            if answer not in {"y", "yes"}:
                print("cancelled")
                return 0
        adoption_id, created = service.adopt(args.branch_id, kind=args.command, rejoin=args.command == "rejoin")
        print(json.dumps({"adoption_id": adoption_id, "created": created, "active_branch": service.storage.active_branch_id()}, indent=2))
    elif args.command == "adapter-command":
        adapter = CodexAdapter() if args.platform == "codex" else ClaudeAdapter()
        command = adapter.build_fork_command(args.session_id, args.prompt) if args.action == "fork" else adapter.build_resume_command(args.session_id, args.prompt)
        print(json.dumps({"command": command, "capabilities": adapter.capabilities.__dict__}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
