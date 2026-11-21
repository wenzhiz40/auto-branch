import unittest
import uuid

from auto_branch.adapters import ClaudeAdapter, CodexAdapter


class AdapterTests(unittest.TestCase):
    def test_codex_commands(self):
        adapter = CodexAdapter()
        self.assertEqual(adapter.build_fork_command("abc", "hello"), ["codex", "exec", "fork", "abc", "--skip-git-repo-check", "--json", "hello"])
        self.assertEqual(adapter.build_resume_command("abc"), ["codex", "exec", "resume", "abc", "--skip-git-repo-check", "--json"])
        self.assertEqual(adapter.build_fork_command("abc", "hello", headless=False), ["codex", "fork", "abc", "hello"])
        self.assertEqual(adapter.build_start_command("hello"), ["codex", "exec", "--skip-git-repo-check", "--json", "hello"])
        self.assertEqual(adapter.parse_session_id('{"type":"thread.started","thread_id":"thread-1"}'), "thread-1")

    def test_claude_commands(self):
        adapter = ClaudeAdapter()
        self.assertEqual(adapter.build_fork_command("abc", "hello"), ["claude", "--resume", "abc", "--fork-session", "--print", "--output-format", "json", "hello"])
        self.assertEqual(adapter.build_resume_command("abc"), ["claude", "--resume", "abc", "--print", "--output-format", "json"])
        self.assertEqual(adapter.build_resume_command("abc", headless=False), ["claude", "--resume", "abc"])
        command = adapter.build_start_command("hello")
        self.assertEqual(command[0:2], ["claude", "--session-id"])
        self.assertEqual(command[-1], "hello")
        uuid.UUID(command[2])
        self.assertEqual(adapter.parse_session_id('{"type":"result","session_id":"session-1"}'), "session-1")


if __name__ == "__main__":
    unittest.main()
