"""Offline lifecycle tests; no real home, packages, services or desktop changes.

Execute a copy of the shipped shell scripts with only $HOME references renamed
to a task-specific fixture variable. The real HOME is never changed. Venv/pip,
systemctl and omarchy are stubbed; filesystem operations remain real in /tmp.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = 'io.github.justvicinity.omagato'


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='omagato-install-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.user_root = self.root / 'user'
        self.source = self.root / 'source'
        self.target = self.user_root / '.config/omarchy/plugins' / PLUGIN_ID
        self.venv = self.user_root / '.local/share/omagato/venv'
        self.unit = self.user_root / '.config/systemd/user/omagato.service'
        self.config = self.user_root / '.config/omarchy-elgato/config.json'
        self.log = self.root / 'commands.jsonl'
        shutil.copytree(ROOT, self.source, ignore=shutil.ignore_patterns('.git', '__pycache__', '.venv'))
        for name in ('install.sh', 'uninstall.sh'):
            path = self.source / name
            path.write_text(path.read_text().replace('$HOME', '$OMAGATO_TEST_ROOT'))
        self.stubs = self.root / 'stubs'
        self.stubs.mkdir()
        recorder = self.root / 'recorder.py'
        recorder.write_text(
            'import json,os,sys\n'
            'tool=sys.argv[1]\n'
            'with open(os.environ["OMAGATO_TEST_LOG"],"a") as log:\n'
            ' log.write(json.dumps([tool,*sys.argv[2:]])+"\\n")\n'
            'if tool=="pip" and os.environ.get("OMAGATO_FAIL_PIP")=="1": sys.exit(9)\n'
            'if tool=="systemctl" and os.environ.get("OMAGATO_FAIL_SYSTEMCTL")=="1": sys.exit(8)\n')
        python_shim = self.stubs / 'python3'
        python_shim.write_text(
            f'#!{sys.executable}\n'
            'import os,pathlib,sys\n'
            f'interpreter={sys.executable!r}\n'
            f'recorder={str(recorder)!r}\n'
            'if sys.argv[1:3]==["-m","venv"]:\n'
            ' path=pathlib.Path(sys.argv[3])/"bin/python"\n'
            ' path.parent.mkdir(parents=True,exist_ok=True)\n'
            ' path.write_text(f"#!{interpreter}\\nimport os,sys\\nos.execv({interpreter!r},[{interpreter!r},{recorder!r},\'pip\',*sys.argv[1:]])\\n")\n'
            ' path.chmod(0o755)\n'
            'else: os.execv(interpreter,[interpreter,*sys.argv[1:]])\n')
        python_shim.chmod(0o755)
        for tool in ('systemctl', 'omarchy'):
            path = self.stubs / tool
            path.write_text(f'#!{sys.executable}\nimport os,sys\nos.execv({sys.executable!r},'
                            f'[{sys.executable!r},{str(recorder)!r},{tool!r},*sys.argv[1:]])\n')
            path.chmod(0o755)
        self.environment = dict(os.environ)
        self.environment.update({'PATH': str(self.stubs) + os.pathsep + os.environ.get('PATH', ''),
                                 'OMAGATO_TEST_ROOT': str(self.user_root),
                                 'OMAGATO_TEST_LOG': str(self.log),
                                 'XDG_DATA_HOME': str(self.user_root / '.local/share'),
                                 'XDG_CONFIG_HOME': str(self.user_root / '.config')})

    def run_script(self, name, *args, installed=False, fail=None):
        environment = dict(self.environment)
        if fail:
            environment[fail] = '1'
        script = (self.target if installed else self.source) / name
        return subprocess.run(['bash', str(script), *args], env=environment,
                              capture_output=True, text=True, timeout=20)

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def seed_config(self):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_bytes(b'{"user":"configuration stays byte-identical"}\n')
        return self.config.read_bytes()

    def test_install_update_and_uninstall_preserve_configuration(self):
        original = self.seed_config()
        result = self.run_script('install.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.target / 'elgato/http_worker.py').is_file())
        self.assertTrue((self.target / 'scripts/path-guards.sh').is_file())
        self.assertTrue((self.target / 'SECURITY.md').is_file())
        self.assertTrue(self.venv.is_dir())
        unit = self.unit.read_text()
        self.assertIn('MemoryMax=512M', unit)
        self.assertIn('UMask=0077', unit)
        self.assertEqual(self.unit.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.config.read_bytes(), original)
        pip = self.commands()[0]
        self.assertEqual(pip[0], 'pip')
        self.assertIn('--require-hashes', pip)
        self.assertIn('--only-binary=:all:', pip)
        self.assertIn(['systemctl', '--user', 'enable', '--now', 'omagato.service'], self.commands())
        self.assertIn(['omarchy', 'plugin', 'enable', PLUGIN_ID], self.commands())
        # Model Omarchy updating the existing checkout before rerunning install.
        (self.target / '.git').mkdir()
        self.unit.write_text(unit.replace('MemoryMax=512M', 'MemoryMax=256M'))
        result = self.run_script('install.sh', installed=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('MemoryMax=512M', self.unit.read_text())
        self.assertEqual(self.config.read_bytes(), original)
        result = self.run_script('uninstall.sh', installed=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.unit.exists())
        self.assertFalse(self.venv.exists())
        self.assertEqual(self.config.read_bytes(), original)
        self.assertTrue(self.target.exists())
        self.assertIn(['systemctl', '--user', 'disable', '--now', 'omagato.service'], self.commands())

    def test_explicit_purge_removes_only_managed_configuration(self):
        self.seed_config()
        sentinel = self.user_root / '.config/another-app/keep'
        sentinel.parent.mkdir()
        sentinel.write_text('keep')
        result = self.run_script('uninstall.sh', '--purge-config')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.config.parent.exists())
        self.assertEqual(sentinel.read_text(), 'keep')

    def test_unrelated_unit_rejected_before_any_install_changes(self):
        original = self.seed_config()
        self.unit.parent.mkdir(parents=True)
        self.unit.write_text('[Service]\nExecStart=/usr/bin/true\n')
        unit = self.unit.read_bytes()
        result = self.run_script('install.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unrelated', result.stderr)
        self.assertEqual(self.unit.read_bytes(), unit)
        self.assertEqual(self.config.read_bytes(), original)
        self.assertFalse(self.target.exists())
        self.assertFalse(self.venv.exists())
        self.assertEqual(self.commands(), [])

    def test_uninstall_preserves_unrelated_unit(self):
        self.unit.parent.mkdir(parents=True)
        self.unit.write_text('[Service]\nExecStart=/usr/bin/true\n')
        unit = self.unit.read_bytes()
        result = self.run_script('uninstall.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.unit.read_bytes(), unit)
        self.assertFalse(any(command[0] == 'systemctl' for command in self.commands()))

    def test_package_failure_does_not_activate_or_replace_service(self):
        result = self.run_script('install.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        unit = self.unit.read_bytes()
        self.log.unlink()
        result = self.run_script('install.sh', installed=True, fail='OMAGATO_FAIL_PIP')
        self.assertEqual(result.returncode, 9)
        self.assertEqual(self.unit.read_bytes(), unit)
        self.assertEqual([command[0] for command in self.commands()], ['pip'])

    def test_service_failure_does_not_enable_plugin(self):
        result = self.run_script('install.sh', fail='OMAGATO_FAIL_SYSTEMCTL')
        self.assertEqual(result.returncode, 8)
        self.assertFalse(any(command[0] == 'omarchy' for command in self.commands()))
        self.assertEqual(list(self.unit.parent.glob('omagato.service.*')), [])

    def test_other_checkout_is_not_overwritten(self):
        (self.target / '.git').mkdir(parents=True)
        sentinel = self.target / 'keep'
        sentinel.write_text('keep')
        result = self.run_script('install.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Git checkout', result.stderr)
        self.assertEqual(sentinel.read_text(), 'keep')
        self.assertEqual(self.commands(), [])

    def test_symlink_install_target_is_rejected_without_writes(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'keep').write_text('keep')
        self.target.parent.mkdir(parents=True)
        self.target.symlink_to(outside, target_is_directory=True)
        result = self.run_script('install.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sorted(path.name for path in outside.iterdir()), ['keep'])
        self.assertEqual(self.commands(), [])

    def test_invalid_manifest_id_is_rejected_without_writes(self):
        path = self.source / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['id'] = '../../other-app'
        path.write_text(json.dumps(manifest))
        result = self.run_script('install.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Unexpected plugin id', result.stderr)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.commands(), [])

    def test_invalid_uninstall_option_preserves_everything(self):
        original = self.seed_config()
        result = self.run_script('uninstall.sh', '--purge')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.config.read_bytes(), original)
        self.assertEqual(self.commands(), [])


if __name__ == '__main__':
    unittest.main()
