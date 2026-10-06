"""Offline tests for update detection, release gating and distributable contents."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('upstream_release', ROOT / '.github/scripts/upstream_release.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def asset(name='tools.zip', identifier=1):
    return dict(id=identifier, name=name, size=3, updated_at='2026-01-01',
                browser_download_url='https://github.com/official/releases/download/v1/' + name)


class AutomationTests(unittest.TestCase):
    def test_asset_replacement_changes_fingerprint_even_at_same_tag(self):
        old = sync.select_tools({'assets': [asset()]}, ['tools.zip'])
        new = sync.select_tools({'assets': [asset(identifier=2)]}, ['tools.zip'])
        self.assertNotEqual(sync.fingerprint(old), sync.fingerprint(new))

    def test_missing_or_ambiguous_asset_fails(self):
        for assets in ([], [asset(), asset()]):
            with self.assertRaises(ValueError):
                sync.select_tools({'assets': assets}, ['tools.zip'])

    def test_fingerprint_is_stable_across_key_order(self):
        self.assertEqual(sync.fingerprint({'a': 1, 'b': 2}), sync.fingerprint({'b': 2, 'a': 1}))

    def test_published_state_ignores_drafts_but_accepts_prereleases(self):
        releases = [dict(draft=True, tag_name='newpage-auto-draft', assets=[asset('upstream-manifest.json')]),
                    dict(draft=False, prerelease=True, tag_name='newpage-auto-ready',
                         assets=[asset('upstream-manifest.json')])]
        with patch.object(sync, 'api', return_value=releases), patch.object(sync, 'fetch', return_value=b'{"fingerprint":"ready"}') as download:
            self.assertEqual(sync.published_manifest('owner/repo')['fingerprint'], 'ready')
            download.assert_called_once()

    def test_unchanged_versions_skip_download_and_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'automation').mkdir()
            config = dict(pulsemodel='p/p', studiomdl_ce='c/c', tools_repository='t/t', tools_tag='v1', tools_assets=['tools.zip'])
            (root / 'automation/upstreams.json').write_text(json.dumps(config))
            (root / 'automation/compatibility.patch').write_text('patch')
            with patch.object(sync, 'ROOT', root), patch.dict(os.environ, GITHUB_SHA='controller', GITHUB_REPOSITORY='o/r'), \
                 patch.object(sync, 'latest_commit', return_value='sha'), patch.object(sync, 'api', return_value={'assets': [asset()]}), \
                 patch.object(sync, 'fingerprint', return_value='unchanged'), patch.object(sync, 'published_manifest', return_value={'fingerprint': 'unchanged'}), \
                 patch.object(sync, 'fetch') as download, patch.object(sync, 'create_source') as merge, patch.object(sync, 'emit') as emit:
                sync.prepare(argparse.Namespace(work=root / 'work', force=False))
                download.assert_not_called()
                merge.assert_not_called()
                emit.assert_called_once_with(changed=False, tag='newpage-auto-unchanged')
                self.assertFalse((root / 'work').exists())

    def test_candidate_refuses_existing_directory(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sync, 'run') as git:
            with self.assertRaises(ValueError):
                sync.create_source(folder, 'p/p', 'sha', 'base', 'patch')
            git.assert_not_called()

    def test_source_archive_excludes_git_and_build_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source'
            for name in ('main.cpp', '.git/config', 'build/compiler.exe', '__pycache__/test.pyc', 'automation/compatibility.patch'):
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('content')
            sync.source_archive(argparse.Namespace(source=source, output=root / 'source.zip'))
            with zipfile.ZipFile(root / 'source.zip') as archive:
                self.assertEqual(set(archive.namelist()), {'NewPageMergeMDL/main.cpp', 'NewPageMergeMDL/automation/compatibility.patch'})

    def test_package_requires_both_compiler_and_decompiler(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                sync.package(argparse.Namespace(dist=folder, output=Path(folder) / 'out.zip', platform='win64'))

    def test_binary_package_contains_provenance_and_licenses(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist, source = root / 'dist', root / 'source'
            dist.mkdir(); source.mkdir()
            for name in ('NewPageMergeMDL.exe', 'NewPageMergeMDL-Decompiler.exe'):
                (dist / name).write_bytes(b'binary')
            for name in ('LICENSE', 'README.md', 'COMPATIBILITY.md', 'AUTOMATION.md'):
                (source / name).write_text(name)
            (source / 'libs/vendor').mkdir(parents=True)
            (source / 'libs/vendor/LICENSE').write_text('vendor notice')
            (root / 'manifest.json').write_text('{}')
            (root / 'StudioMDL-CE.exe').write_text('reference only')
            sync.package(argparse.Namespace(dist=dist, source=source, output=root / 'out.zip',
                                            platform='win64', manifest=root / 'manifest.json'))
            with zipfile.ZipFile(root / 'out.zip') as archive:
                self.assertIn('NewPageMergeMDL/upstream-manifest.json', archive.namelist())
                self.assertIn('NewPageMergeMDL/libs/vendor/LICENSE', archive.namelist())
                self.assertFalse(any('StudioMDL-CE' in name for name in archive.namelist()))

    def test_checksums_verify_actual_artifacts_and_are_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'a.zip').write_bytes(b'actual artifact')
            args = argparse.Namespace(folder=root)
            sync.checksums(args)
            expected = hashlib.sha256(b'actual artifact').hexdigest() + '  a.zip\n'
            self.assertEqual((root / 'SHA256SUMS.txt').read_text(), expected)
            sync.checksums(args)
            self.assertEqual((root / 'SHA256SUMS.txt').read_text(), expected)


if __name__ == '__main__':
    unittest.main()
