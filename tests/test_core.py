import json
import tempfile
import unittest
from pathlib import Path

from auto_branch.decision import DecisionMode
from auto_branch.service import AutoBranchService


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.service = AutoBranchService(Path(self.tempdir.name))

    def tearDown(self):
        self.tempdir.cleanup()

    def test_suggest_mode_is_conservative(self):
        decision = self.service.route("Ubuntu 怎么安装 Zotero？")
        self.assertEqual(decision.action.value, "ask")
        self.assertTrue(decision.needs_confirmation)

    def test_mainline_topic_and_summary_are_used_for_classification(self):
        self.service.set_topic("mainline", "Flow Matching research")
        self.service.set_summary("mainline", "Flow Matching probability path and velocity field")
        decision = self.service.route("Continue analyzing the Flow Matching probability path")
        self.assertEqual(decision.classification.relationship.value, "same")
        self.assertEqual(decision.action.value, "continue")

    def test_explicit_continue_is_labeled_same_even_without_topic_overlap(self):
        self.service.set_topic("mainline", "Flow Matching research")
        decision = self.service.route("Continue analyzing the probability path")
        self.assertEqual(decision.classification.relationship.value, "same")
        self.assertEqual(decision.action.value, "continue")

    def test_create_and_rejoin_branch_is_idempotent(self):
        branch = self.service.create_branch(
            title="Ubuntu Zotero",
            topic="Ubuntu software installation",
            platform="codex",
            native_session_id="session-1",
            summary="Zotero should be installed through the supported package path.",
        )
        self.service.switch(branch["id"])
        first_id, created = self.service.adopt(branch["id"], kind="rejoin", rejoin=True)
        self.assertTrue(created)
        self.assertEqual(self.service.storage.active_branch_id(), "mainline")
        self.assertEqual(self.service.storage.get_branch(branch["id"])["status"], "rejoined")

        second_id, created_again = self.service.adopt(branch["id"], kind="rejoin", rejoin=True)
        self.assertEqual(first_id, second_id)
        self.assertFalse(created_again)
        mainline = self.service.memory.mainline_path.read_text(encoding="utf-8")
        self.assertEqual(mainline.count("Zotero should be installed"), 1)

    def test_adopt_does_not_switch_active_branch(self):
        branch = self.service.create_branch(
            title="Research subtopic",
            topic="Flow Matching",
            platform="claude",
            summary="A useful result.",
        )
        self.service.switch(branch["id"])
        self.service.adopt(branch["id"], kind="findings", rejoin=False)
        self.assertEqual(self.service.storage.active_branch_id(), branch["id"])
        self.assertEqual(self.service.storage.get_branch(branch["id"])["status"], "adopted")

    def test_context_package_truncates_oversized_summary(self):
        package = self.service.memory.context_package(
            original_goal="Research",
            current_topic="Subtopic",
            summary="x" * (self.service.memory.MAX_CONTEXT_SUMMARY_CHARS + 20),
            prompt="Question",
        )
        self.assertIn("[Summary truncated by Auto-Branch context budget.]", package)
        self.assertIn("Current Question\nQuestion", package)
        self.assertLess(len(package), self.service.memory.MAX_CONTEXT_SUMMARY_CHARS + 500)

    def test_topic_label_excludes_prompt_instructions(self):
        decision = self.service.route(
            "Open a new unrelated topic about Ubuntu package management. "
            "Reply with exactly: SEEDED_BRANCH_READY. Do not use tools."
        )
        self.assertEqual(decision.classification.new_topic, "Ubuntu package management")


if __name__ == "__main__":
    unittest.main()
