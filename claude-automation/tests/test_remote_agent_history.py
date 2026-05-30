from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from argparse import Namespace
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

    def test_resolve_config_reuses_remote_dir_for_matching_host_user(self) -> None:
        self.remote_agent.save_history(
            "10.0.0.10",
            "ubuntu",
            "/home/ubuntu/deploy",
            "ansible",
            "deploy",
        )
        args = Namespace(
            host="10.0.0.10",
            user="ubuntu",
            remote_dir=None,
            cmd="ansible-playbook -i inventory.yaml playbooks/site.yml",
            dry_run=True,
            profile=None,
            use_last=False,
            save_profile="",
        )

        cfg = self.remote_agent.resolve_config(args)

        self.assertEqual(cfg.remote_dir, "/home/ubuntu/deploy")

    def test_expect_script_shell_quotes_remote_dir(self) -> None:
        cfg = self.remote_agent.AgentConfig(
            host="10.0.0.10",
            user="ubuntu",
            password="",
            cmd="pwd",
            remote_dir="/home/ubuntu/deploy dir",
            dry_run=False,
        )

        script = self.remote_agent._build_expect_script(cfg)

        self.assertIn("set remote_dir {'/home/ubuntu/deploy dir'}", script)


if __name__ == "__main__":
    unittest.main()
