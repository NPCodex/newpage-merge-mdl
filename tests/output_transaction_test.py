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

    def run_tool(self, mode, crash=None, code=0):
        env=os.environ.copy()
        if crash:env['NPMDL_TEST_CRASH']=crash
        else:env.pop('NPMDL_TEST_CRASH',None)
        p=subprocess.run([HARNESS,str(self.root),mode],env=env,capture_output=True,text=True)
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


if __name__=='__main__':
    unittest.main()
