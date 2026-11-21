import json
import tempfile
import unittest
from pathlib import Path

from auto_branch.decision import DecisionMode
from auto_branch.prompt_runner import PromptRunner
from auto_branch.service import AutoBranchService


class FakeProcess:
    def __init__(self, payload: dict, returncode: int = 0, stderr: str = ""):
        self.args = []
        self.returncode = returncode
        self.stdout = json.dumps(payload)
        self.stderr = stderr


class PromptRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.service = AutoBranchService(Path(self.tempdir.name))
        self.calls = []

    def tearDown(self):
        self.tempdir.cleanup()

    def runner(self, command, prompt, timeout):
        self.calls.append((command, prompt, timeout))
        if command[0] == "codex" and "fork" in command:
            return FakeProcess({"type": "thread.started", "thread_id": "child-session"})
        if command[0] == "codex" and prompt.startswith("# Branch Context"):
            return FakeProcess({"type": "thread.started", "thread_id": "seeded-session"})
        if command[0] == "codex":
            return FakeProcess({"type": "thread.started", "thread_id": "parent-session"})
        return FakeProcess({"type": "result", "session_id": "session-1"})

    def test_first_prompt_starts_and_binds_session(self):
        result = PromptRunner(self.service, runner=self.runner).run(
            platform="codex", prompt="PARENT_READY"
        )
        self.assertEqual(result.action, "start")
        self.assertEqual(self.service.storage.get_branch("mainline")["native_session_id"], "parent-session")
        self.assertEqual(len(self.calls), 1)

    def test_confirmed_unrelated_prompt_forks_once_and_switches_branch(self):
        self.service.bind_session("mainline", "codex", "parent-session")
        result = PromptRunner(self.service, runner=self.runner).run(
            platform="codex", prompt="Open a new unrelated topic", confirm=True
        )
        self.assertEqual(result.action, "fork")
        self.assertEqual(result.session_id, "child-session")
        self.assertEqual(self.service.storage.active_branch_id(), result.branch_id)
        self.assertEqual(self.service.storage.get_branch(result.branch_id)["native_session_id"], "child-session")
        self.assertEqual(self.service.storage.get_branch(result.branch_id)["status"], "active")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][1], "Open a new unrelated topic")

    def test_seeded_branch_starts_new_session_with_context_package(self):
        self.service.set_topic("mainline", "Flow Matching research")
        self.service.set_summary("mainline", "Probability paths and velocity fields.")
        self.service.bind_session("mainline", "codex", "parent-session")
        result = PromptRunner(self.service, runner=self.runner).run(
            platform="codex",
            prompt="Open a new unrelated topic",
            confirm=True,
            branch_mode="seeded",
        )
        self.assertEqual(result.action, "start_seeded")
        self.assertEqual(result.branch_mode, "seeded")
        self.assertEqual(result.session_id, "seeded-session")
        self.assertIn("# Branch Context", self.calls[0][1])
        self.assertIn("Open a new unrelated topic", self.calls[0][1])

    def test_resume_keeps_same_session(self):
        self.service.bind_session("mainline", "codex", "parent-session")
        result = PromptRunner(self.service, runner=self.runner).run(
            platform="codex", prompt="Continue the current topic"
        )
        self.assertEqual(result.action, "resume")
        self.assertEqual(result.session_id, "parent-session")
        self.assertEqual(len(self.calls), 1)
        with self.service.storage._connect() as db:
            event = db.execute(
                "SELECT user_choice, adapter_result FROM routing_events ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(event["user_choice"], "continue")
        self.assertIn("parent-session", event["adapter_result"])

    def test_failed_fork_with_session_id_is_registered_without_retry(self):
        self.service.bind_session("mainline", "codex", "parent-session")

        def ambiguous_runner(command, prompt, timeout):
            self.calls.append((command, prompt, timeout))
            return FakeProcess(
                {"type": "thread.started", "thread_id": "child-session"},
                returncode=1,
                stderr="provider disconnected after turn start",
            )

        result = PromptRunner(self.service, runner=ambiguous_runner).run(
            platform="codex", prompt="Open a new unrelated topic", confirm=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.session_id, "child-session")
        self.assertEqual(self.service.storage.get_branch(result.branch_id)["native_session_id"], "child-session")
        self.assertEqual(self.service.storage.get_branch(result.branch_id)["status"], "delivery_unknown")
        self.assertEqual(self.service.storage.active_branch_id(), result.branch_id)
        self.assertEqual(len(self.calls), 1)

    def test_manual_mode_does_not_call_native_cli(self):
        self.service.bind_session("mainline", "codex", "parent-session")
        # CLI handles manual mode by reporting the decision without entering the runner.
        decision = self.service.route("Continue the current topic", DecisionMode.MANUAL)
        self.assertEqual(decision.action.value, "continue")
        self.assertEqual(self.calls, [])

    def test_manual_mode_is_rejected_by_runner(self):
        self.service.bind_session("mainline", "codex", "parent-session")
        with self.assertRaisesRegex(RuntimeError, "manual mode"):
            PromptRunner(self.service, runner=self.runner).run(
                platform="codex", prompt="Do not execute", mode=DecisionMode.MANUAL
            )

    def test_seeded_mode_uses_markdown_summary_when_database_summary_is_empty(self):
        self.service.set_topic("mainline", "Flow Matching research")
        self.service.bind_session("mainline", "codex", "parent-session")
        self.service.memory.write_branch_summary("mainline", "Stored markdown background")
        result = PromptRunner(self.service, runner=self.runner).run(
            platform="codex",
            prompt="Open a new unrelated topic",
            confirm=True,
            branch_mode="seeded",
        )
        self.assertEqual(result.action, "start_seeded")
        self.assertIn("Stored markdown background", self.calls[-1][1])


if __name__ == "__main__":
    unittest.main()
