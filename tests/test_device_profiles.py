"""Multi-device behavior, legacy compatibility, touch and fast state paths."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from elgato import core, devices, health, profiles, visuals
from elgato.cli import main
from elgato.daemon import Worker

A = 'deck-' + 'a' * 24
B = 'deck-' + 'b' * 24


class DeviceProfilesTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.file = root / 'config.json'
        for name, value in (('CONFIG_FILE', self.file), ('CONFIG_DIR', root)):
            helper = patch.object(core, name, value)
            helper.start()
            self.addCleanup(helper.stop)

    def call(self, *args):
        with patch('builtins.print') as output:
            code = main(list(args))
        result = json.loads(output.call_args.args[0])
        self.assertEqual(code, 0, result)
        return result

    def worker(self, config):
        with patch.object(core, 'load_config', return_value=config):
            worker = Worker()
        self.addCleanup(worker.actions.close)
        for ident, profile in (('usb-a', A), ('usb-b', B)):
            deck = Mock()
            deck.id.return_value = ident
            deck.is_visual.return_value = False
            worker.decks[ident] = deck
            worker.device_ids[ident] = profile
        return worker

    def test_first_edit_copies_legacy_layout_and_keeps_devices_independent(self):
        config = core.default_config()
        config['pages'][0]['keys']['0'] = {'type': 'volume', 'value': 'mute'}
        config['unknown_legacy_extension'] = {'keep': True}
        core.save_config(config)
        self.call('--device', A, 'assign', '0', '1', '{"type":"media","value":"play-pause"}')
        self.call('--device', B, 'brightness', '31')
        saved = core.load_config()
        self.assertEqual(saved['pages'], config['pages'])
        self.assertEqual(profiles.effective(saved, A)['pages'][0]['keys']['0'], config['pages'][0]['keys']['0'])
        self.assertIn('1', profiles.effective(saved, A)['pages'][0]['keys'])
        self.assertNotIn('1', profiles.effective(saved, B)['pages'][0]['keys'])
        self.assertEqual(profiles.effective(saved, B)['brightness'], 31)
        self.assertEqual(profiles.effective(saved, A)['brightness'], 70)
        self.assertEqual(saved['unknown_legacy_extension'], {'keep': True})

    def test_global_language_does_not_create_or_modify_a_device_profile(self):
        self.call('--device', A, 'set-language', 'de')
        saved = core.load_config()
        self.assertEqual(saved['language'], 'de')
        self.assertNotIn('device_profiles', saved)

    def test_page_key_only_switches_its_own_deck(self):
        config = core.default_config()
        config['pages'][0]['keys']['0'] = {'type': 'page', 'value': '1'}
        config['pages'].append({'name': 'Other', 'keys': {}})
        worker = self.worker(config)
        worker.on_key(worker.decks['usb-a'], 0, False)
        self.assertEqual(worker.device_pages['usb-a'], 1)
        self.assertEqual(worker.device_pages.get('usb-b', 0), 0)

    def test_focus_rules_leave_unconfigured_decks_alone(self):
        config = core.default_config()
        config['pages'].append({'name': 'Other', 'keys': {}})
        settings = profiles.editable(config, A)
        settings['app_pages'] = {'steam': 1}
        profiles.store(config, A, settings)
        worker = self.worker(config)
        worker.device_pages['usb-b'] = 1
        with patch('subprocess.run', return_value=Mock(stdout='{"class":"steam"}')):
            worker.follow_app()
        self.assertEqual(worker.device_pages, {'usb-a': 1, 'usb-b': 1})
        with patch('subprocess.run', return_value=Mock(stdout='{"class":"other"}')):
            worker.follow_app()
        self.assertEqual(worker.device_pages, {'usb-a': 0, 'usb-b': 1})

    def test_delete_page_reindexes_rules_and_touch_page_actions(self):
        self.call('--device', A, 'new-page', 'One')
        self.call('--device', A, 'new-page', 'Two')
        self.call('--device', A, 'app-page', 'steam', '2')
        self.call('--device', A, '--surface', 'touch', 'assign', '0', '0', '{"type":"page","value":"2"}')
        self.call('--device', A, 'delete-page', '1')
        settings = profiles.effective(core.load_config(), A)
        self.assertEqual(settings['app_pages'], {'steam': 1})
        self.assertEqual(settings['pages'][0]['touch']['0']['value'], '1')
        self.call('--device', A, 'app-page', 'steam', '-1')
        self.assertEqual(profiles.effective(core.load_config(), A)['app_pages'], {})

    def test_invalid_profile_or_touch_region_is_rejected_without_writing(self):
        self.call('brightness', '51')
        original = self.file.read_bytes()
        for args in (['--device', '../escape', 'brightness', '20'],
                     ['--device', A, '--surface', 'touch', 'assign', '0', '8', '{"type":"volume","value":"mute"}'],
                     ['--device', A, 'app-page', 'steam', '8'],
                     ['--device', A, 'delete-page', '-1']):
            with self.subTest(args=args), patch('builtins.print'):
                self.assertEqual(main(args), 1)
            self.assertEqual(self.file.read_bytes(), original)

    def test_profile_count_and_recursive_unknown_fields_are_bounded(self):
        config = core.default_config()
        config['device_profiles'] = {'deck-' + f'{index:024x}': {} for index in range(9)}
        with self.assertRaises(ValueError):
            core.validate_config(config)
        config['device_profiles'] = {A: {'device_profiles': {}}}
        with self.assertRaises(ValueError):
            core.validate_config(config)

    def test_serial_identity_survives_usb_port_change_without_exposing_serial(self):
        a, b = Mock(), Mock()
        a.get_serial_number.return_value = b.get_serial_number.return_value = 'private-serial'
        a.id.return_value, b.id.return_value = 'usb1', 'usb2'
        self.assertEqual(profiles.identity(a), profiles.identity(b))
        self.assertNotIn('private-serial', profiles.identity(a))

    def test_inventory_preserves_two_identical_models_and_gates_detected_only(self):
        usb = [{'name': 'Stream Deck MK.2', 'id': '0080', 'path': 'usb-a', 'profile': A},
               {'name': 'Stream Deck MK.2', 'id': '0080', 'path': 'usb-b', 'profile': B},
               {'name': 'Wave:3', 'id': '0001', 'path': 'usb-c'}]
        worker = {'decks': [{'name': 'Stream Deck MK.2', 'id': 'usb-a', 'profile': A, 'keys': 15}]}
        result = {item['id']: item for item in devices.inventory(worker, [], [], usb=usb)}
        self.assertEqual(len(result['deck']['devices']), 2)
        self.assertEqual([item['controllable'] for item in result['deck']['devices']], [True, False])
        self.assertTrue(result['audio']['connected'])
        self.assertFalse(result['audio']['controllable'])

    def test_quick_state_never_probes_hardware_or_renders_previews(self):
        with patch('elgato.cli.status', return_value={'running': False, 'decks': []}), \
             patch.object(core, 'cameras') as cameras, patch.object(visuals, 'preview_data') as preview, \
             patch.object(core, 'light_state') as lights:
            result = self.call('--quick', 'state')
        cameras.assert_not_called()
        lights.assert_not_called()
        preview.assert_not_called()
        self.assertNotIn('visuals', result)

    def test_local_state_renders_only_requested_page_without_hardware_probes(self):
        config = core.default_config()
        config['pages'].append({'name': 'Other', 'keys': {}})
        core.save_config(config)
        with patch('elgato.cli.status', return_value={'running': False, 'decks': []}), \
             patch.object(core, 'cameras') as cameras, \
             patch.object(visuals, 'empty_image', return_value=None) as image:
            result = self.call('--local', '--page', '1', 'state')
        cameras.assert_not_called()
        self.assertEqual(image.call_count, 15)
        self.assertEqual(result['visuals']['pages'][0], {})
        self.assertEqual(len(result['visuals']['pages'][1]), 15)

    def test_touch_tap_hold_and_swipe_are_isolated_and_queued(self):
        from StreamDeck.Devices.StreamDeck import TouchscreenEventType as Event
        config = core.default_config()
        config['pages'][0]['touch'] = {'0': {'type': 'volume', 'value': 'mute'}}
        config['pages'][0]['touch_long'] = {'0': {'type': 'media', 'value': 'stop'}}
        config['pages'].append({'name': 'Other', 'keys': {}})
        worker = self.worker(config)
        deck = worker.decks['usb-a']
        deck.dial_count.return_value = 4
        deck.touchscreen_image_format.return_value = {'size': (800, 100)}
        with patch.object(worker.actions, 'submit', return_value=True) as submit:
            worker.on_touch(deck, Event.SHORT, {'x': 40})
            self.assertEqual(submit.call_args.args[0][-1], 'touch')
            worker.on_touch(deck, Event.LONG, {'x': 40})
            self.assertEqual(submit.call_args.args[0][-1], 'touch_long')
        worker.on_touch(deck, Event.DRAG, {'x': 600, 'x_out': 100})
        self.assertEqual(worker.device_pages['usb-a'], 1)
        self.assertEqual(worker.device_pages.get('usb-b', 0), 0)

    def test_reset_device_restores_template_without_touching_other_decks(self):
        self.call('--device', A, 'brightness', '20')
        self.call('--device', B, 'brightness', '30')
        self.call('--device', A, 'reset-device')
        saved = core.load_config()
        self.assertNotIn(A, saved['device_profiles'])
        self.assertEqual(profiles.effective(saved, A)['brightness'], 70)
        self.assertEqual(profiles.effective(saved, B)['brightness'], 30)

    def test_setup_detects_controller_code_updates(self):
        revision = health.runtime_revision()
        with patch.object(health.importlib.metadata, 'version', side_effect=lambda name: '0.10.0' if name == 'streamdeck' else '12.3.0'):
            current = health.check({'running': True, 'revision': revision}, [])
            stale = health.check({'running': True, 'revision': 'old'}, [])
        self.assertFalse(current['needs_restart'])
        self.assertTrue(stale['needs_restart'])
        self.assertFalse(current['needs_install'])

    def test_touch_render_produces_native_image_and_keeps_long_only_assignment_visible(self):
        config = core.default_config()
        config['pages'][0]['touch_long'] = {'0': {'type': 'volume', 'value': 'mute', 'label': 'Mute'}}
        worker = self.worker(config)
        deck = worker.decks['usb-a']
        deck.dial_count.return_value = 4
        deck.touchscreen_image_format.return_value = {'size': (800, 100), 'format': 'JPEG', 'flip': (False, False), 'rotation': 0}
        worker.paint_touch(deck, config, 0, core.palette())
        image = deck.set_touchscreen_image.call_args.args[0]
        self.assertTrue(image.startswith(bytes([0xff, 0xd8])))
        self.assertLess(len(image), 100000)

    def test_invalid_touch_page_target_does_not_escape_reader_callback(self):
        from StreamDeck.Devices.StreamDeck import TouchscreenEventType as Event
        config = core.default_config()
        config['pages'][0]['touch'] = {'0': {'type': 'page', 'value': 'invalid'}}
        worker = self.worker(config)
        deck = worker.decks['usb-a']
        deck.dial_count.return_value = 4
        deck.touchscreen_image_format.return_value = {'size': (800, 100)}
        worker.on_touch(deck, Event.SHORT, {'x': 1})
        self.assertEqual(worker.device_pages.get('usb-a', 0), 0)

    def test_diagnostics_exclude_serials_paths_assignments_and_errors(self):
        worker = {'running': True, 'decks': [{'name': 'Stream Deck', 'keys': 15,
                  'profile': A, 'id': 'private-port', 'serial': 'private-serial'}],
                  'errors': ['secret-token']}
        usb = [{'name': 'Stream Deck', 'id': '0080', 'path': 'private-port', 'profile': A}]
        with patch.object(health, 'check', return_value={'needs_install': False}):
            result = json.dumps(health.diagnostics(worker, usb))
        for secret in ('private-port', 'private-serial', A, 'secret-token'):
            self.assertNotIn(secret, result)


if __name__ == '__main__':
    unittest.main()
