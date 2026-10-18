"""Real process termination across the output journal protocol.

Run with a separately compiled output_transaction_harness.cpp; the released
compiler does not contain the NPMDL_TEST_CRASH environment-variable hook.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

HARNESS=str(Path(sys.argv.pop(1)).resolve())


class OutputRecovery(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def run_tool(self, mode, crash=None, code=0, root=None, folder=None):
        env=os.environ.copy()
        if crash:env['NPMDL_TEST_CRASH']=crash
        else:env.pop('NPMDL_TEST_CRASH',None)
        args=[HARNESS,str(root or self.root),mode]
        if folder is not None:args.append(str(folder))
        p=subprocess.run(args,env=env,capture_output=True,text=True)
        self.assertEqual(p.returncode,code,p.stdout+p.stderr);return p.stdout+p.stderr

    def files(self):
        return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*')
                if p.is_file() and '.npmdl-' not in str(p.relative_to(self.root))
                and '.npmdl_locks' not in p.parts}

    def test_termination_before_commit_restores_previous_complete_set(self):
        for phase in ('journal','stage','backup','install','mdl'):
            with self.subTest(phase=phase):
                self.run_tool('old');old=self.files()
                self.run_tool('new',crash=phase,code=86)
                self.run_tool('recover');self.assertEqual(self.files(),old)
                self.run_tool('recover');self.assertEqual(self.files(),old)

    def test_termination_after_commit_keeps_complete_new_set(self):
        self.run_tool('new');new=self.files();self.run_tool('old')
        self.run_tool('new',crash='commit',code=86);self.run_tool('recover')
        self.assertEqual(self.files(),new)

    def test_deletion_before_commit_restores_previous_complete_set(self):
        for phase in ('journal','stage','backup','install','delete','mdl'):
            with self.subTest(phase=phase):
                self.run_tool('old');old=self.files()
                self.run_tool('delete',crash=phase,code=86)
                self.run_tool('recover');self.assertEqual(self.files(),old)
                self.run_tool('recover');self.assertEqual(self.files(),old)

    def test_deletion_after_commit_stays_deleted(self):
        self.run_tool('old');self.run_tool('delete',crash='commit',code=86)
        self.assertFalse((self.root/'collision/other.phy').exists())
        self.run_tool('recover');self.run_tool('recover')
        self.assertFalse((self.root/'collision/other.phy').exists())
        self.assertEqual((self.root/'fixture.vertexanim.json').read_bytes(),b'delete-vertexanim')

    def test_externally_recreated_deleted_output_is_preserved(self):
        for phase in ('delete','commit'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                self.run_tool('old',root=root);self.run_tool('delete',crash=phase,code=86,root=root)
                target=root/'collision/other.phy';target.write_bytes(b'user replacement')
                self.assertIn('changed since transaction',self.run_tool('recover',code=1,root=root))
                self.assertEqual(target.read_bytes(),b'user replacement')

    def test_legacy_journal_still_recovers_vertexanim(self):
        self.run_tool('old');old=self.files();self.run_tool('new',crash='mdl',code=86)
        journal=self.root/'fixture.mdl.npmdl-journal'
        lines=journal.read_text().splitlines()
        lines[0]=lines[0].replace('NPMDL_TXN_2','NPMDL_TXN_1')
        journal.write_text('\n'.join([lines[0]]+[line.rsplit(' ',1)[0] for line in lines[1:]])+'\n')
        self.run_tool('recover');self.assertEqual(self.files(),old)

    def test_arbitrary_json_is_rejected_without_touching_outputs(self):
        self.run_tool('old');old=self.files()
        self.assertIn('unsupported output recovery extension',self.run_tool('badjson',code=1))
        self.assertEqual(self.files(),old)

    def test_termination_without_previous_outputs_removes_partial_new_set(self):
        for phase in ('journal','stage','install','mdl'):
            with self.subTest(phase=phase):
                self.run_tool('new',crash=phase,code=86)
                self.run_tool('recover');self.assertEqual(self.files(),{})

    def test_concurrent_writer_is_rejected_without_changing_outputs(self):
        self.run_tool('old');old=self.files()
        child=subprocess.Popen([HARNESS,str(self.root),'hold'],stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),'LOCKED')
            text=self.run_tool('new',code=1);self.assertIn('locked by another compiler',text)
            self.assertEqual(self.files(),old)
        finally:
            child.kill();child.wait(timeout=10);child.stdout.close()
        self.run_tool('new')

    def test_external_edits_are_not_overwritten_by_recovery(self):
        self.run_tool('old');self.run_tool('new',crash='install',code=86)
        target=self.root/'fixture.vvd';target.write_bytes(b'external edit')
        self.assertIn('changed since transaction',self.run_tool('recover',code=1))
        self.assertEqual(target.read_bytes(),b'external edit')
        self.assertTrue(list(self.root.glob('*.backup')))

    def test_new_nested_output_directory_and_escape_rejection(self):
        folder='new directory/not created yet'
        self.run_tool('old',folder=folder);old=self.files()
        self.assertIn(str(Path(folder)/'fixture.mdl'),old)
        self.run_tool('new',crash='install',code=86,folder=folder)
        self.run_tool('recover',folder=folder);self.assertEqual(self.files(),old)
        self.assertIn('unsafe output journal path',self.run_tool('new',code=1,folder='../outside'))
        self.assertEqual(self.files(),old)

    @unittest.skipUnless(os.name=='nt', 'Windows short-name and case aliases')
    def test_windows_directory_aliases_share_recovery_and_locks(self):
        import ctypes
        from ctypes import wintypes
        self.root=self.root/'Output directory with a long name';self.root.mkdir()
        short_path=ctypes.WinDLL('kernel32',use_last_error=True).GetShortPathNameW
        short_path.argtypes=[wintypes.LPCWSTR,wintypes.LPWSTR,wintypes.DWORD]
        short_path.restype=wintypes.DWORD
        buffer=ctypes.create_unicode_buffer(32768)
        self.assertTrue(short_path(str(self.root),buffer,len(buffer)))
        aliases={str(self.root).upper(),buffer.value}
        for alias in aliases:
            with self.subTest(alias=alias):
                self.run_tool('old');old=self.files()
                self.run_tool('new',crash='install',code=86,root=alias)
                self.run_tool('recover');self.assertEqual(self.files(),old)
                # Reverse the spellings for the next recovery.
                self.run_tool('new',crash='mdl',code=86)
                self.run_tool('recover',root=alias);self.assertEqual(self.files(),old)
                child=subprocess.Popen([HARNESS,str(self.root),'hold'],stdout=subprocess.PIPE,text=True)
                try:
                    self.assertEqual(child.stdout.readline().strip(),'LOCKED')
                    self.assertIn('locked by another compiler',self.run_tool('new',code=1,root=alias))
                    self.assertEqual(self.files(),old)
                finally:
                    child.kill();child.wait(timeout=10);child.stdout.close()

    @unittest.skipUnless(os.name=='nt', 'Windows short-name child directory aliases')
    def test_windows_short_child_alias_uses_same_lock_and_journal(self):
        import ctypes
        from ctypes import wintypes
        folder='Existing child with a long name'
        (self.root/folder).mkdir()
        short_path=ctypes.WinDLL('kernel32',use_last_error=True).GetShortPathNameW
        short_path.argtypes=[wintypes.LPCWSTR,wintypes.LPWSTR,wintypes.DWORD]
        short_path.restype=wintypes.DWORD
        buffer=ctypes.create_unicode_buffer(32768)
        self.assertTrue(short_path(str(self.root/folder),buffer,len(buffer)))
        alias=Path(buffer.value).name
        self.run_tool('old',folder=folder);old=self.files()
        self.run_tool('new',crash='mdl',code=86,folder=alias)
        self.run_tool('recover',folder=folder);self.assertEqual(self.files(),old)
        child=subprocess.Popen([HARNESS,str(self.root),'hold',folder],stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),'LOCKED')
            self.assertIn('locked by another compiler',self.run_tool('new',code=1,folder=alias))
            self.assertEqual(self.files(),old)
        finally:
            child.kill();child.wait(timeout=10);child.stdout.close()

    @unittest.skipUnless(os.name=='nt', 'Windows junction checks')
    def test_windows_junctions_below_root_remain_rejected(self):
        link=self.root/'collision'
        outside=self.root.parent/(self.root.name+'-outside');outside.mkdir()
        self.addCleanup(outside.rmdir)
        marker=outside/'other.phy';marker.write_bytes(b'unrelated')
        self.addCleanup(marker.unlink)
        # Include a junction back to root: matching the nearest physical
        # ancestor instead of the first would accidentally conceal this link.
        for target in (outside,self.root):
            with self.subTest(target=target):
                result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                try:
                    text=self.run_tool('old',code=1,root=str(self.root).upper())
                    self.assertTrue('reparse point' in text or 'symbolic link' in text,text)
                    self.assertEqual(marker.read_bytes(),b'unrelated')
                    self.assertFalse((self.root/'fixture.mdl').exists())
                finally:
                    link.rmdir()


if __name__=='__main__':
    unittest.main()
