"""Representative pre-hardening configurations and non-destructive failures."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from elgato import core
from elgato.cli import main

FIXTURES = Path(__file__).with_name('fixtures')


class ConfigurationCompatibilityTests(unittest.TestCase):
    def test_all_action_types_and_existing_settings_survive_round_trip(self):
        original = json.loads((FIXTURES / 'config-v1-full.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(original))
            with patch.object(core, 'CONFIG_FILE', path):
                self.assertEqual(core.load_config(), original)
                core.save_config(core.load_config())
                self.assertEqual(core.load_config(), original)

    def test_legacy_minimal_file_gets_defaults_without_changing_actions(self):
        original = {'version': 1, 'pages': [{'name': 'Start', 'keys': {
            '0': {'type': 'command', 'value': 'echo hello'}}}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(original))
            with patch.object(core, 'CONFIG_FILE', path):
                result = core.load_config()
                self.assertEqual(result['pages'], original['pages'])
                self.assertEqual(result['lights'], [])
                self.assertEqual(result['dials'], {})
                core.save_config(result)
                self.assertEqual(core.load_config(), result)

    def test_cli_update_preserves_all_unrelated_configuration_fields(self):
        original = json.loads((FIXTURES / 'config-v1-full.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(original))
            with patch.object(core, 'CONFIG_FILE', path), patch('builtins.print'):
                self.assertEqual(main(['brightness', '71']), 0)
                expected = {**original, 'brightness': 71}
                self.assertEqual(core.load_config(), expected)

    def test_invalid_existing_files_return_json_errors_and_remain_identical(self):
        samples = [
            (b'{"version":1,"pages":[{"name":"Start","keys":{}}],"lights":[{"host":"lamp.example.com"}]}', 'IP'),
            (b'{"version":1,"pages":[{"name":"Start","keys":{"0":{"type":"command","value":"echo x","label":123}}}]}', 'action.label'),
            (b'{"version":1,"pages":[]}', 'Konfiguration'),
            (b'{"version":1,', 'JSON'),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            with patch.object(core, 'CONFIG_FILE', path):
                for data, message in samples:
                    with self.subTest(data=data):
                        path.write_bytes(data)
                        with patch('builtins.print') as output:
                            self.assertEqual(main(['brightness', '71']), 1)
                        error = json.loads(output.call_args.args[0])['error']
                        self.assertIn(message, error)
                        self.assertEqual(path.read_bytes(), data)

    def test_existing_long_label_is_rejected_with_field_and_limit(self):
        config = core.default_config()
        config['pages'][0]['keys']['0'] = {'type': 'command', 'value': 'echo hello', 'label': 'x' * 81}
        with self.assertRaisesRegex(ValueError, r'action.label.*80'):
            core.validate_config(config)


if __name__ == '__main__':
    unittest.main()
