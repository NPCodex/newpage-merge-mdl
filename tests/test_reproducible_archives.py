import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location('archive_impl', Path(__file__).resolve().parents[1] / '.github/scripts/upstream_release.py')
archive_impl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive_impl)
COMPARE_SPEC = importlib.util.spec_from_file_location('compare_impl', Path(__file__).resolve().parents[1] / '.github/scripts/compare_builds.py')
compare_impl = importlib.util.module_from_spec(COMPARE_SPEC)
COMPARE_SPEC.loader.exec_module(compare_impl)


class Archives(unittest.TestCase):
    def test_root_mtime_permissions_do_not_change_archive_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            outputs = []
            for index in range(2):
                source = root / str(index)
                source.mkdir()
                file = source / 'source.cpp'
                file.write_bytes(b'int main(){return 0;}\n')
                os.utime(file, (1700000000 + index * 1000, 1700000000 + index * 1000))
                target = root / f'{index}.zip'
                with archive_impl.ReproducibleZipFile(target, 'w', archive_impl.zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                    archive.write(file, 'source.cpp')
                    archive.writestr('metadata.json', '{"schema":1}\n')
                outputs.append(target.read_bytes())
            self.assertEqual(*outputs)

    def test_comparison_requires_member_and_container_byte_equality(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for index in (0, 1):
                with zipfile.ZipFile(root / f'{index}.zip', 'w') as archive:
                    info = zipfile.ZipInfo('program', date_time=(2026, 1, index + 1, 0, 0, 0))
                    archive.writestr(info, b'identical program')
            result = compare_impl.compare(root / '0.zip', root / '1.zip')
            self.assertEqual(result['changed'], {})
            self.assertFalse(result['archive_bytes_equal'])
            self.assertFalse(result['equal'])
            with archive_impl.ReproducibleZipFile(root / '1.zip', 'w') as archive:
                archive.writestr('program', b'changed program')
            self.assertIn('program', compare_impl.compare(root / '0.zip', root / '1.zip')['changed'])


if __name__ == '__main__':
    unittest.main()
