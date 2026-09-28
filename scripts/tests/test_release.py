import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "VERSION.txt").write_text("1.2.3\n")
        (self.root / "TDM_VERSION").write_text("1.0.0\n")
        self.root_patch = patch.object(release, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        for name in ("thymio-2-device-manager-1.2.3-macos-universal.dmg",
                     "thymio-2-device-manager-1.2.3-windows-x64.exe",
                     "thymio-2-device-manager_1.2.3-1_amd64.deb"):
            (self.root / name).write_bytes(b"build output")

    def test_versions_and_tag_mismatch(self):
        self.assertEqual(release.versions("refs/tags/v1.2.3"), ("1.2.3", "1.0.0"))
        with self.assertRaises(ValueError):
            release.versions("refs/tags/v1.2.4")

    def test_create_or_update_only_drafts(self):
        for state in ("missing", "draft", "published", "network-error"):
            calls = []

            def gh(*args, check=True):
                calls.append(args)
                if args[0] == "api":
                    if state in ("missing", "network-error"):
                        return subprocess.CompletedProcess(args, 1, "", "HTTP 404" if state == "missing" else "HTTP 500")
                    return subprocess.CompletedProcess(args, 0, json.dumps({"draft": state == "draft"}), "")
                return subprocess.CompletedProcess(args, 0, "", "")

            with self.subTest(state=state), patch.object(release, "gh", side_effect=gh):
                if state in ("published", "network-error"):
                    with self.assertRaises(ValueError):
                        release.publish(self.root, "refs/tags/v1.2.3", "owner/repo", "commit")
                    self.assertEqual(len(calls), 1)
                else:
                    release.publish(self.root, "refs/tags/v1.2.3", "owner/repo", "commit")
                    self.assertEqual(len((self.root / "SHA256SUMS").read_text().splitlines()), 3)
                    operations = [call[:2] for call in calls]
                    self.assertIn(("release", "upload"), operations)
                    self.assertIn(("release", "create" if state == "missing" else "edit"), operations)

    def test_incomplete_builds_never_create_release(self):
        (self.root / "thymio-2-device-manager-1.2.3-windows-x64.exe").unlink()
        with patch.object(release, "gh") as gh, self.assertRaises(ValueError):
            release.publish(self.root, "refs/tags/v1.2.3", "owner/repo", "commit")
        gh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
