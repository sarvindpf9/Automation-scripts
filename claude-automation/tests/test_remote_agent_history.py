from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


def load_remote_agent() -> object:
    module_path = Path(__file__).resolve().parents[1] / "remote-agent.py"
    spec = importlib.util.spec_from_file_location("remote_agent", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["remote_agent"] = module
    spec.loader.exec_module(module)
    return module


class RemoteAgentHistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.remote_agent = load_remote_agent()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.history_file = Path(self.tmpdir.name) / "history.json"
        self.remote_agent._HISTORY_FILE = self.history_file

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_save_history_dedupes_by_profile_name(self) -> None:
        self.remote_agent.save_history(
            "10.0.0.10",
            "ubuntu",
            "/home/ubuntu/old",
            "bash",
            "lab",
        )
        self.remote_agent.save_history(
            "10.0.0.11",
            "ubuntu",
            "/home/ubuntu/new",
            "ansible",
            "lab",
        )

        entries = json.loads(self.history_file.read_text())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "lab")
        self.assertEqual(entries[0]["SSH_HOST"], "10.0.0.11")
        self.assertEqual(entries[0]["REMOTE_DIR"], "/home/ubuntu/new")

    def test_find_history_entry_supports_name_and_last(self) -> None:
        self.remote_agent.save_history(
            "10.0.0.10",
            "ubuntu",
            "/home/ubuntu/a",
            "bash",
            "a",
        )
        self.remote_agent.save_history(
            "10.0.0.20",
            "rocky",
            "/home/rocky/b",
            "bash",
            "b",
        )

        named = self.remote_agent.find_history_entry("a")
        latest = self.remote_agent.find_history_entry(use_last=True)

        self.assertEqual(named["SSH_HOST"], "10.0.0.10")
        self.assertEqual(latest["name"], "b")
        self.assertEqual(latest["SSH_USER"], "rocky")

    def test_forget_history_profile_removes_only_named_profile(self) -> None:
        self.remote_agent.save_history(
            "10.0.0.10",
            "ubuntu",
            "/home/ubuntu/a",
            "bash",
            "a",
        )
        self.remote_agent.save_history(
            "10.0.0.20",
            "rocky",
            "/home/rocky/b",
            "bash",
            "b",
        )

        self.assertIs(self.remote_agent.forget_history_profile("a"), True)
        self.assertIsNone(self.remote_agent.find_history_entry("a"))
        self.assertEqual(
            self.remote_agent.find_history_entry("b")["SSH_HOST"],
            "10.0.0.20",
        )


if __name__ == "__main__":
    unittest.main()
