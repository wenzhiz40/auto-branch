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

    def runner(self, command):
        self.calls.append(command)
        if command[0] == "codex" and "fork" in command:
            return FakeProcess({"type": "thread.started", "thread_id": "child-session"})
        if command[0] == "codex" and command[-1].startswith("# Branch Context"):
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
        self.assertEqual(len(self.calls), 1)

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
        self.assertIn("# Branch Context", self.calls[0][-1])
        self.assertIn("Open a new unrelated topic", self.calls[0][-1])

    def test_resume_keeps_same_session(self):
        self.service.bind_session("mainline", "codex", "parent-session")
        result = PromptRunner(self.service, runner=self.runner).run(
            platform="codex", prompt="Continue the current topic"
        )
        self.assertEqual(result.action, "resume")
        self.assertEqual(result.session_id, "parent-session")
        self.assertEqual(len(self.calls), 1)

    def test_failed_fork_with_session_id_is_registered_without_retry(self):
        self.service.bind_session("mainline", "codex", "parent-session")

        def ambiguous_runner(command):
            self.calls.append(command)
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
        self.assertEqual(self.service.storage.active_branch_id(), result.branch_id)
        self.assertEqual(len(self.calls), 1)

    def test_manual_mode_does_not_call_native_cli(self):
        self.service.bind_session("mainline", "codex", "parent-session")
        # CLI handles manual mode by reporting the decision without entering the runner.
        decision = self.service.route("Continue the current topic", DecisionMode.MANUAL)
        self.assertEqual(decision.action.value, "continue")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
