import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from diagnostic_bundle import build, redact


class Bundle(unittest.TestCase):
    def test_redaction(self):
        text = 'C:\\Users\\Person\\secret-model.smd\n/home/person/project/foo\ntoken=abc\nAuthorization: Bearer xyz\nghp_12345'
        result = redact(text)
        for private in ('Person', 'person', 'secret-model', 'abc', 'xyz', 'ghp_12345'):
            self.assertNotIn(private, result)

    def test_only_selected_text_and_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = root / 'upstream-manifest.json'
            manifest.write_text(json.dumps(dict(controller_sha='a' * 40, unrelated_private='private')))
            log = root / 'compile.log'
            log.write_text('NP1300\ntoken=secret\n')
            output = root / 'bundle.zip'
            build(output, manifest, [log])
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist(), ['build.json', 'logs/1.log'])
                self.assertNotIn('unrelated_private', archive.read('build.json').decode())
                self.assertNotIn('secret', archive.read('logs/1.log').decode())
            original = manifest.read_bytes()
            with self.assertRaises(ValueError):
                build(manifest, manifest, [log])
            self.assertEqual(manifest.read_bytes(), original)
            model = root / 'secret.mdl'
            model.write_bytes(b'model')
            prior = output.read_bytes()
            with self.assertRaises(ValueError):
                build(output, manifest, [model])
            self.assertEqual(output.read_bytes(), prior)


if __name__ == '__main__':
    unittest.main()
