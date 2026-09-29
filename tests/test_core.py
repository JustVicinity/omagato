import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from elgato import core, devices, i18n, openxlr, prompter, visuals
from elgato.cli import main


class ConfigTests(unittest.TestCase):
    def test_openxlr_uses_capabilities_and_rejects_unsupported_controls(self):
        raw = {'type': 'state', 'connected': True, 'device': {'model': 'Wave XLR Pro'},
               'capabilities': {'gain': True, 'mute': True, 'phantom': True,
                                'xlrInputs': 2},
               'state': {'gainDb': 30, 'gain2Db': 32, 'mute': False,
                         'phantom': False},
               'mixer': {'mixes': [{'id': 'monitor', 'name': 'Monitor',
                                    'kind': 'monitor', 'volume': .7, 'muted': False}]}}
        with patch.object(openxlr, 'raw_state', return_value=raw), \
             patch.object(openxlr, '_call', return_value={'ok': True}) as call:
            state = openxlr.state()
            self.assertEqual(state['device'], 'Wave XLR Pro')
            self.assertIn('gain2', [item['id'] for item in state['controls']])
            self.assertNotIn('compressor', [item['id'] for item in state['controls']])
            openxlr.set_control('gain2', '42')
            self.assertEqual(call.call_args.args[1],
                             {'cmd': 'set', 'control': 'gain2', 'value': 42.0})
            with self.assertRaises(ValueError):
                openxlr.set_control('compressor', '1')
            with self.assertRaises(ValueError):
                openxlr.set_control('gain', '90')
            openxlr.set_mix('monitor', 'volume', '1.2')
            self.assertEqual(call.call_args.args[1]['cmd'], 'setMixVolume')

    def test_inventory_marks_attached_deck_controllable_and_other_families_inactive(self):
        worker = {'decks': [{'id': '1-5.3:0fd9:0080', 'name': 'Stream Deck MK.2',
                              'keys': 15, 'dials': 0}]}
        usb = [{'name': 'Stream Deck MK.2', 'id': '0080', 'path': '1-5.3'},
               {'name': 'Wave:3', 'id': '0001', 'path': '1-2'}]
        result = {family['id']: family for family in devices.inventory(worker, [], [], usb=usb)}
        self.assertEqual(result['deck']['devices'][0]['level'], 'control')
        self.assertNotIn('Stream Deck MK.2', result['deck']['variants'])
        self.assertEqual(result['audio']['devices'][0]['level'], 'detected')
        self.assertFalse(result['light']['connected'])

    def test_audio_controls_only_current_elgato_pipewire_nodes(self):
        node = {'type': 'PipeWire:Interface:Node', 'id': 42, 'info': {'props': {
            'media.class': 'Audio/Source', 'device.vendor.name': 'Elgato',
            'node.description': 'Wave:3'}}}
        from subprocess import CompletedProcess
        with patch.object(core.subprocess, 'run', side_effect=[
            CompletedProcess([], 0, json.dumps([node])),
            CompletedProcess([], 0, 'Volume: 0.73 [MUTED]')]):
            audio = core.audio_nodes()
        self.assertEqual((audio[0]['id'], audio[0]['volume'], audio[0]['muted']),
                         (42, .73, True))
        with patch.object(core, 'audio_nodes', return_value=audio), \
             patch.object(core.subprocess, 'run') as run:
            core.set_audio('42', 'mute', '0')
            self.assertEqual(run.call_args.args[0], ['wpctl', 'set-mute', '42', '0'])
            with self.assertRaises(ValueError):
                core.set_audio('43', 'mute', '0')

    def test_media_action_uses_mpris_when_playerctl_is_absent(self):
        from subprocess import CompletedProcess
        listing = 'org.mpris.MediaPlayer2.first 1 app user\norg.mpris.MediaPlayer2.second 2 app user\n'
        responses = [CompletedProcess([], 0, listing),
                     CompletedProcess([], 0, 's "Paused"'),
                     CompletedProcess([], 0, 's "Playing"'),
                     CompletedProcess([], 0, '')]
        with patch.object(core, 'shutil_which', side_effect=lambda name: name == 'busctl'), \
             patch.object(core.subprocess, 'run', side_effect=responses) as run:
            core.media_action('play-pause')
            self.assertEqual(run.call_args.args[0],
                             ['busctl', '--user', 'call', 'org.mpris.MediaPlayer2.second',
                              '/org/mpris/MediaPlayer2', 'org.mpris.MediaPlayer2.Player', 'PlayPause'])

    def test_camera_controls_include_menus_toggles_and_driver_defaults(self):
        from subprocess import CompletedProcess
        output = '''brightness 0x00980900 (int) : min=0 max=255 step=1 default=128 value=130
auto_exposure 0x009a0901 (menu) : min=0 max=3 default=3 value=1
    1: Manual Mode
    3: Aperture Priority Mode
focus_automatic_continuous 0x009a090c (bool) : default=1 value=1
exposure_absolute 0x009a0902 (int) : min=1 max=5000 step=1 default=250 value=250 flags=inactive
'''
        with patch.object(core, 'cameras', return_value=[{'node': '/dev/video2', 'name': 'Facecam'}]), \
             patch.object(core.subprocess, 'run', return_value=CompletedProcess([], 0, output)) as run:
            controls = core.camera_controls('/dev/video2')
            self.assertEqual([x['type'] for x in controls], ['int', 'menu', 'bool', 'int'])
            self.assertEqual(controls[1]['options'][1], {'value': 3, 'label': 'Aperture Priority Mode'})
            self.assertFalse(controls[3]['writable'])
            core.set_camera('/dev/video2', 'auto_exposure', '3')
            self.assertEqual(run.call_args.args[0], ['v4l2-ctl', '-d', '/dev/video2', '--set-ctrl', 'auto_exposure=3'])
            with self.assertRaises(ValueError):
                core.set_camera('/dev/video2', 'auto_exposure', '2')
            with self.assertRaises(ValueError):
                core.set_camera('/dev/video2', 'exposure_absolute', '250')

    def test_native_prompter_script_and_monitor_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            screen = {'name': 'DP-3', 'description': 'Elgato Prompter', 'prompter': True,
                      'width': 1024, 'height': 600}
            with patch.object(core, 'CONFIG_DIR', Path(directory)), \
                 patch.object(core, 'CONFIG_FILE', Path(directory) / 'config.json'), \
                 patch.object(prompter, 'SCRIPTS_DIR', Path(directory) / 'scripts'), \
                 patch.object(prompter, 'monitors', return_value=[screen]):
                prompter.save_script('Demo', '# Hello\nThis is a test')
                state = prompter.state(core.load_config())
                self.assertTrue(state['connected'])
                self.assertEqual(state['screen'], 'DP-3')
                self.assertEqual(state['text'], '# Hello\nThis is a test')
                self.assertEqual(state['scripts'], ['Demo'])
                prompter.set_setting('speed', '111')
                self.assertEqual(prompter.state(core.load_config())['speed'], 111)
                with self.assertRaises(ValueError):
                    prompter.save_script('../outside', 'bad')
                families = {item['id']: item for item in devices.inventory(
                    {'decks': []}, [], [], usb=[], prompter=state)}
                self.assertEqual(families['camera']['devices'][0]['name'], 'Prompter')

    def test_old_configuration_gets_new_defaults_without_losing_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            original = {'version': 1, 'brightness': 70, 'pages': [
                {'name': 'Start', 'keys': {'4': {'type': 'app', 'value': 'steam.desktop'}}}]}
            path.write_text(json.dumps(original))
            with patch.object(core, 'CONFIG_FILE', path):
                result = core.load_config()
            self.assertEqual(result['pages'], original['pages'])
            self.assertEqual(result['language'], 'auto')
            self.assertEqual(result['empty_default']['style'], 'theme')

    def test_language_follows_locale_and_explicit_override(self):
        with patch.dict('os.environ', {'LC_ALL': 'C.UTF-8', 'LANG': 'de_DE.UTF-8'}):
            self.assertEqual(i18n.system_language(), 'en')
        with patch.dict('os.environ', {'LC_ALL': 'fr_FR.UTF-8', 'LANG': 'de_DE.UTF-8'}):
            self.assertEqual(i18n.language({'language': 'auto'}), 'fr')
            self.assertEqual(i18n.language({'language': 'es'}), 'es')

    def test_empty_key_override_and_icon_theme(self):
        config = core.default_config()
        config['pages'][0]['empty'] = {'3': visuals.normalize_empty({'style': 'black', 'label': 'Pause'})}
        self.assertEqual(visuals.empty_for(config, 0, 3)['style'], 'black')
        self.assertEqual(visuals.empty_for(config, 0, 4)['style'], 'theme')
        config['icon_theme'] = 'nord'
        self.assertEqual(visuals.resolve_theme(config), 'nord')

    def test_user_image_import_is_copied_into_managed_store(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'my icon.png'
            Image.new('RGB', (10, 10), '#123456').save(source)
            with patch.object(core, 'CONFIG_DIR', Path(directory) / 'config'):
                stored = visuals.import_icon(source)
                self.assertEqual(visuals.imported_icon(stored), Path(stored))
                self.assertEqual(visuals.normalize_empty({'style': 'image', 'image': stored})['image'], stored)
                self.assertTrue(Path(stored).exists())

    def test_every_app_gets_four_distinct_theme_tiles_with_its_logo(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            logo = Path(directory) / 'my-app.png'
            Image.new('RGBA', (48, 48), '#ea241b').save(logo)
            action = {'type': 'app', 'value': 'my-app.desktop', 'label': 'My App', 'system_icon': str(logo)}
            with patch.object(visuals, 'CACHE_DIR', Path(directory) / 'cache'):
                paths = [visuals.action_image(action, theme, force_theme=True) for theme in visuals.THEMES]
                self.assertEqual(len(set(paths)), 4)
                self.assertTrue(all(path.is_file() for path in paths))
                self.assertEqual([Image.open(path).getpixel((72, 72)) for path in paths],
                                 [(234, 36, 27, 255)] * 4)
                action['icon_theme'] = 'nord'
                self.assertEqual(visuals.action_image(action, 'tokyo-night'), paths[-1])

    def test_empty_theme_uses_background_art(self):
        spec = visuals.normalize_empty({'style': 'theme', 'icon': 'blank'})
        self.assertEqual(visuals.empty_image(spec, 'nord').name, 'background.png')
        self.assertEqual(visuals.normalize_empty({'style': 'wallpaper'})['style'], 'wallpaper')

    def test_state_preview_works_without_connected_deck(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(core, 'CONFIG_DIR', Path(directory)), \
                 patch.object(core, 'CONFIG_FILE', Path(directory) / 'config.json'), \
                 patch('elgato.cli.status', return_value={'running': False, 'decks': [], 'page': 0, 'errors': []}), \
                 patch('elgato.cli.core.cameras', return_value=[]), \
                 patch('builtins.print') as output:
                self.assertEqual(main(['state']), 0)
                data = json.loads(output.call_args.args[0])
                self.assertEqual(len(data['visuals']['pages'][0]), 15)

    def test_assign_and_clear_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(core, 'CONFIG_DIR', Path(directory)), patch.object(core, 'CONFIG_FILE', Path(directory) / 'config.json'):
                action = {'type': 'command', 'label': 'Beispiel', 'value': 'echo hello'}
                with patch('builtins.print'):
                    self.assertEqual(main(['assign', '0', '2', json.dumps(action)]), 0)
                self.assertEqual(core.load_config()['pages'][0]['keys']['2'], action)
                with patch('builtins.print'):
                    self.assertEqual(main(['clear', '0', '2']), 0)
                self.assertEqual(core.load_config()['pages'][0]['keys'], {})

    def test_multi_runs_each_step_without_shell(self):
        action = {'type': 'multi', 'steps': [
            {'type': 'command', 'value': 'echo hello'},
            {'type': 'volume', 'value': 'mute'}]}
        with patch.object(core.subprocess, 'Popen') as popen, patch.object(core.subprocess, 'run') as run:
            core.run_action(action)
        self.assertEqual(run.call_args.args[0], ['echo', 'hello'])
        self.assertEqual(popen.call_args.args[0][0], 'wpctl')

    def test_light_values_are_clamped(self):
        with patch.object(core, 'light_state', return_value={'on': 0, 'brightness': 50, 'temperature': 200}), \
             patch.object(core, 'light_request', return_value={}) as request:
            core.set_light('192.168.1.2', brightness=150, temperature=100)
        self.assertEqual(request.call_args.args[2]['lights'][0]['brightness'], 100)
        self.assertEqual(request.call_args.args[2]['lights'][0]['temperature'], 143)

    def test_nested_macro_is_rejected(self):
        with self.assertRaises(ValueError):
            core.run_action({'type': 'multi', 'steps': [{'type': 'multi', 'steps': []}]})


if __name__ == '__main__':
    unittest.main()
