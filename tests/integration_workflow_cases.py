"""Fixed five-compiler workflow closure: ++ launch defaults and restart recovery."""
import json
import struct


def output_digest(data):
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return len(data), value


def journal_text(entries, nonce='123456789'):
    rows = [f'NPMDL_TXN_1 {nonce} {len(entries)}']
    for name, old, new in entries:
        rows.append(f'{json.dumps(name)} {int(old is not None)} '
                    f'{output_digest(old or b"")[0]} {output_digest(old or b"")[1]} '
                    f'{output_digest(new)[0]} {output_digest(new)[1]}')
    return '\n'.join(rows) + '\n'


class IntegrationWorkflowCases:
    def defaults_game(self, tools='', cfg=None):
        self.write('gameinfo.txt', 'GameInfo { game fixture Tools { studiomdl '
                   + json.dumps(tools) + ' } FileSystem { SteamAppId 220 '
                   'SearchPaths { Game "|gameinfo_path|." } } }')
        if cfg is not None:
            self.write('cfg/commandline.cfg', 'CommandLine { '
                       + json.dumps(cfg[0]) + ' { studiomdl '
                       + json.dumps(cfg[1]) + ' } }')

    def test_launch_defaults_precedence_matches_plusplus(self):
        self.defaults_game('-minlod 1', ('test', '-minlod 2'))
        qc='$modelname defaults\n$lod 10 { }\n$lod 20 { }\n'
        self.run_qc(qc)
        self.assertEqual(struct.unpack_from('<i', (self.root/'models/defaults.vvd').read_bytes(), 12)[0], 1)
        self.run_qc(qc, '-minlod', '0')
        self.assertEqual(struct.unpack_from('<i', (self.root/'models/defaults.vvd').read_bytes(), 12)[0], 3)
        self.run_qc(qc, '-minlod', '0', '-minlod', '1')
        self.assertEqual(struct.unpack_from('<i', (self.root/'models/defaults.vvd').read_bytes(), 12)[0], 2)

    def test_launch_defaults_qc_stem_case_quotes_and_no_extension(self):
        self.defaults_game('-modelname "from game"', ('TeSt', '-modelname "from cfg"'))
        self.run_qc('$modelname explicit_qc')
        self.assertTrue((self.root/'models/from cfg.mdl').exists())
        self.defaults_game('-modelname "from game"', ('test.qc', '-modelname wrong'))
        self.run_qc('$modelname explicit_qc')
        self.assertTrue((self.root/'models/from game.mdl').exists())
        self.assertFalse((self.root/'models/wrong.mdl').exists())
        self.run_qc('$modelname explicit_qc', '-modelname', 'explicit cli')
        self.assertTrue((self.root/'models/explicit cli.mdl').exists())

    def test_launch_defaults_can_be_disabled_and_bad_quotes_are_reported(self):
        self.defaults_game('-modelname "unterminated')
        text=self.run_qc('$modelname baseline', success=False)
        self.assertIn('unterminated command-line quote', text)
        self.run_qc('$modelname baseline', '-nodefaultargs')
        self.assertTrue((self.root/'models/baseline.mdl').exists())

    def test_launch_defaults_search_paths_and_pinned_variables(self):
        self.write('extra directory/piece.qci', '$modelname $selected$\n')
        self.defaults_game('-includesearchdir "'+(self.root/'extra directory').as_posix()
                           +'" -defvar selected from_game', ('test', '-defvar selected from_cfg'))
        self.run_qc('$include piece.qci', '-defvar', 'selected', 'from_cli')
        self.assertTrue((self.root/'models/from_cli.mdl').exists())

    def test_output_restart_recovers_before_sequence_preservation(self):
        qc='$modelname restart\n$sequence first mesh.smd\n$sequence second mesh.smd\n'
        self.run_qc(qc)
        directory=self.root/'models'
        entries=[]
        for i, path in enumerate(sorted(directory.glob('restart.*'))):
            old=path.read_bytes();new=b'interrupted replacement '+path.suffix.encode()
            entries.append((path.name, old, new))
            path.rename(str(path)+f'.npmdl-123456789-{i}.backup')
            path.write_bytes(new)
        self.write('models/restart.mdl.npmdl-journal', journal_text(entries))
        text=self.run_qc('$modelname restart\n$sequence second mesh.smd\n$sequence first mesh.smd\n')
        self.assertIn('Recovered interrupted output transaction', text)
        self.assertEqual([sequence[0] for sequence in self.sequences('restart')], ['first', 'second'])
        self.assertFalse(list(directory.glob('*.npmdl-*')))

    def test_output_recovery_retains_changed_files_and_backups(self):
        qc='$modelname changed\n';self.run_qc(qc)
        path=self.root/'models/changed.mdl';old=path.read_bytes();new=b'expected-new'
        backup=path.with_name(path.name+'.npmdl-123456789-0.backup')
        path.rename(backup);path.write_bytes(b'edited outside compiler')
        self.write('models/changed.mdl.npmdl-journal', journal_text([(path.name, old, new)]))
        text=self.run_qc(qc, success=False)
        self.assertIn('output changed since transaction', text)
        self.assertEqual(path.read_bytes(), b'edited outside compiler')
        self.assertEqual(backup.read_bytes(), old)

    def test_output_recovery_rejects_journal_path_escape(self):
        qc='$modelname unsafe\n';self.run_qc(qc)
        outside=self.write('outside.mdl', 'unrelated')
        self.write('models/unsafe.mdl.npmdl-journal', journal_text([
            ('unsafe.mdl', self.mdl('unsafe'), b'new'),
            ('../outside.mdl', b'unrelated', b'replacement')]))
        text=self.run_qc(qc, success=False)
        self.assertIn('unsafe output journal path', text)
        self.assertEqual(outside.read_text(), 'unrelated')
