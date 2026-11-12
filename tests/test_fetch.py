import base64
import unittest

from viewer.fetch import clone_cmd
from viewer.load import repo_path

PUBLIC = {"name": "pub", "url": "https://example.org/pub.git", "ref": "dev"}
PRIVATE = {"name": "priv", "url": "https://example.org/priv.git",
           "auth": {"user_env": "U", "token_env": "T"}}


class FetchTests(unittest.TestCase):
    def test_public_clone_is_shallow_on_ref(self):
        cmd, extra = clone_cmd(PUBLIC, "repos/pub", {})
        self.assertEqual(cmd[:2], ["git", "clone"])
        self.assertIn("--depth", cmd)
        self.assertEqual(cmd[cmd.index("--branch") + 1], "dev")
        self.assertNotIn("GIT_CONFIG_COUNT", extra)

    def test_token_goes_in_env_header_not_in_command_or_url(self):
        cmd, extra = clone_cmd(PRIVATE, "repos/priv", {"U": "bot", "T": "s3cret"})
        self.assertNotIn("s3cret", " ".join(cmd))
        self.assertNotIn("bot", " ".join(cmd))
        header = extra["GIT_CONFIG_VALUE_0"].removeprefix("Authorization: Basic ")
        self.assertEqual(base64.b64decode(header).decode(), "bot:s3cret")

    def test_missing_credentials_fail_with_names_of_variables(self):
        with self.assertRaises(SystemExit) as e:
            clone_cmd(PRIVATE, "x", {"U": "bot"})
        self.assertIn("T", str(e.exception))

    def test_missing_url_fails(self):
        with self.assertRaises(SystemExit):
            clone_cmd({"name": "x"}, "x", {})

    def test_repo_path_prefers_repos_dir(self):
        cfg = {"name": "r", "path": "~/src/r"}
        self.assertEqual(str(repo_path(cfg, "repos")), "repos/r")
        self.assertTrue(str(repo_path(cfg)).endswith("/src/r"))
        self.assertNotIn("~", str(repo_path(cfg)))


if __name__ == "__main__":
    unittest.main()
