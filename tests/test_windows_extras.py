"""Offline release tests: ship only verified, pinned Windows helper binaries."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fetch_windows_extras',
                                            ROOT / '.github/scripts/fetch_windows_extras.py')
extras = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extras)


def archive_bytes(members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            for name, data in members:
                archive.writestr(name, data)
    return stream.getvalue()


class WindowsExtrasTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.config_path = self.root / 'config.json'
        self.dist = self.root / 'dist'
        self.dist.mkdir()
        self.binary = b'MZpinned-helper-test-data'
        self.member = 'NewPageMergeMDL/NewPageMergeMDL-C4D.exe'
        self.data = archive_bytes([(self.member, self.binary),
                                   ('NewPageMergeMDL/SDK/private.h', b'not redistributable')])
        self.config = {
            'schema': 1,
            'source': {
                'release_tag': 'v1.2.23',
                'url': 'https://github.com/NPCodex/newpage-merge-mdl/releases/download/v1.2.23/full.zip',
                'api_url': 'https://api.github.com/repos/NPCodex/newpage-merge-mdl/releases/assets/123',
                'sha256': hashlib.sha256(self.data).hexdigest(),
            },
            'files': [{'member': self.member, 'name': 'NewPageMergeMDL-C4D.exe',
                       'sha256': hashlib.sha256(self.binary).hexdigest()}],
        }

    def stage(self, data=None):
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')
        fetch = Mock(return_value=self.data if data is None else data)
        result = extras.stage(self.config_path, self.dist, fetch=fetch)
        fetch.assert_called_once_with(self.config['source']['api_url'], accept='application/octet-stream')
        return result

    def test_selected_helper_and_provenance_are_staged_without_sdk_files(self):
        self.assertEqual(self.stage(), self.config)
        self.assertEqual((self.dist / 'NewPageMergeMDL-C4D.exe').read_bytes(), self.binary)
        self.assertEqual(json.loads((self.dist / 'windows-extras-manifest.json').read_text()), self.config)
        self.assertEqual({p.name for p in self.dist.iterdir()},
                         {'NewPageMergeMDL-C4D.exe', 'windows-extras-manifest.json'})

    def test_archive_mismatch_preserves_existing_output(self):
        old = self.dist / 'NewPageMergeMDL-C4D.exe'
        old.write_bytes(b'old-valid-helper')
        with self.assertRaisesRegex(ValueError, 'archive SHA256 mismatch'):
            self.stage(b'corrupt download')
        self.assertEqual(old.read_bytes(), b'old-valid-helper')
        self.assertFalse((self.dist / 'windows-extras-manifest.json').exists())

    def test_member_mismatch_stages_nothing(self):
        self.config['files'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'helper SHA256 mismatch'):
            self.stage()
        self.assertEqual(list(self.dist.iterdir()), [])

    def test_missing_or_duplicate_member_stages_nothing(self):
        for entries in ([], [(self.member, self.binary), (self.member, self.binary)]):
            with self.subTest(entries=entries):
                data = archive_bytes(entries)
                self.config['source']['sha256'] = hashlib.sha256(data).hexdigest()
                with self.assertRaisesRegex(ValueError, 'Missing or ambiguous'):
                    self.stage(data)
                self.assertEqual(list(self.dist.iterdir()), [])

    def test_all_helpers_must_pass_before_any_output_changes(self):
        self.config['files'].append({'member': 'NewPageMergeMDL/missing.exe',
                                     'name': 'missing.exe', 'sha256': '0' * 64})
        with self.assertRaisesRegex(ValueError, 'Missing or ambiguous'):
            self.stage()
        self.assertEqual(list(self.dist.iterdir()), [])

    def test_matching_non_executable_is_rejected(self):
        data = archive_bytes([(self.member, b'wrong file')])
        self.config['source']['sha256'] = hashlib.sha256(data).hexdigest()
        self.config['files'][0]['sha256'] = hashlib.sha256(b'wrong file').hexdigest()
        with self.assertRaisesRegex(ValueError, 'not a PE executable'):
            self.stage(data)

    def test_unpinned_and_foreign_urls_are_rejected(self):
        for url in ('http://github.com/NPCodex/newpage-merge-mdl/releases/download/v1/file.zip',
                    'https://github.com/NPCodex/newpage-merge-mdl/releases/latest/download/file.zip',
                    'https://github.com/another/project/releases/download/v1/file.zip',
                    'https://example.com/file.zip'):
            with self.subTest(url=url):
                config = copy.deepcopy(self.config)
                config['source']['url'] = url
                with self.assertRaises(ValueError):
                    extras.validate_config(config)

    def test_unsafe_paths_or_duplicate_outputs_are_rejected(self):
        for member in ('../file.exe', '/absolute.exe', 'NewPageMergeMDL/../file.exe',
                       'NewPageMergeMDL\\file.exe', '.', 'NewPageMergeMDL/C:/file.exe'):
            with self.subTest(member=member):
                config = copy.deepcopy(self.config)
                config['files'][0]['member'] = member
                with self.assertRaises(ValueError):
                    extras.validate_config(config)
        for name in ('../file.exe', 'subdir/file.exe', 'C:evil.exe', 'file.dll'):
            with self.subTest(name=name):
                config = copy.deepcopy(self.config)
                config['files'][0]['name'] = name
                with self.assertRaises(ValueError):
                    extras.validate_config(config)
        self.config['files'].append(dict(self.config['files'][0], name='newpagemergemdl-c4d.exe'))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            extras.validate_config(self.config)

    def test_foreign_asset_api_is_rejected(self):
        for url in ('http://api.github.com/repos/NPCodex/newpage-merge-mdl/releases/assets/123',
                    'https://api.github.com/repos/another/project/releases/assets/123',
                    'https://api.github.com/repos/NPCodex/newpage-merge-mdl/releases/latest'):
            with self.subTest(url=url):
                config = copy.deepcopy(self.config)
                config['source']['api_url'] = url
                with self.assertRaises(ValueError):
                    extras.validate_config(config)

    def test_repository_pins_real_sha256_values(self):
        config = json.loads((ROOT / 'automation/windows-extras.json').read_text())
        extras.validate_config(config)
        self.assertEqual(config['files'][0]['name'], 'NewPageMergeMDL-C4D.exe')


if __name__ == '__main__':
    unittest.main()
