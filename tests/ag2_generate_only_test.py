"""Verify generate-only removes stale generated resources without touching unrelated files."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HARNESS = Path(sys.argv.pop(1)).resolve()


class Ag2GenerateOnly(unittest.TestCase):
    def run_harness(self, mode):
        with tempfile.TemporaryDirectory(prefix="newpage-ag2-generate-only-") as folder:
            root = Path(folder)
            result = subprocess.run([str(HARNESS), str(root), mode], capture_output=True,
                                    text=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return {path.relative_to(root).as_posix(): path.read_bytes()
                    for path in root.rglob("*") if path.is_file()
                    and ".newpage-txn-" not in path.name}

    def test_generate_only_removes_only_generated_compiled_outputs(self):
        files = self.run_harness("generate-only")
        self.assertNotIn("game/csgo_addons/addon/model/anims/proportions.vnmclip_c", files)
        self.assertNotIn("game/csgo_addons/addon/model/graphs/proportions_worldmodel.vnmgraph_c", files)
        self.assertNotIn("game/csgo_addons/addon/model/graphs/proportions_uimodel.vnmgraph_c", files)
        self.assertEqual(files["game/csgo_addons/addon/model/unrelated.resource_c"], b"unrelated output")

    def test_full_mode_does_not_remove_existing_compiled_outputs(self):
        files = self.run_harness("full")
        self.assertEqual(files["game/csgo_addons/addon/model/anims/proportions.vnmclip_c"], b"old clip")
        self.assertEqual(files["game/csgo_addons/addon/model/graphs/proportions_worldmodel.vnmgraph_c"],
                         b"old world graph")
        self.assertEqual(files["game/csgo_addons/addon/model/graphs/proportions_uimodel.vnmgraph_c"], b"old UI graph")


if __name__ == "__main__":
    unittest.main()
