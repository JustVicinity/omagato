"""Clipboard limits are enforced while reading, not after collection by Qt."""
import json
from pathlib import Path
import re
import sys
import time
import unittest
from unittest.mock import patch

from elgato import clipboard
from elgato.cli import main


class ClipboardTests(unittest.TestCase):
    def producer(self, code):
        return [sys.executable, '-c', code]

    def test_normal_unicode_and_newlines_are_preserved(self):
        result = clipboard.read_text(self.producer("import os; os.write(1, 'Grüße\\n世界'.encode())"))
        self.assertEqual(result, 'Grüße\n世界')

    def test_exact_limit_is_accepted_and_limit_plus_one_is_rejected(self):
        self.assertEqual(len(clipboard.read_text(self.producer("import os; os.write(1,b'a'*1024)"), limit=1024)), 1024)
        with self.assertRaisesRegex(ValueError, 'clipboard_too_large'):
            clipboard.read_text(self.producer("import os; os.write(1,b'a'*1025)"), limit=1024)

    def test_endless_stream_is_stopped_before_collection(self):
        start = time.monotonic()
        with self.assertRaisesRegex(ValueError, 'clipboard_too_large'):
            clipboard.read_text(self.producer("import os\nwhile True: os.write(1,b'x'*4096)"), limit=8192)
        self.assertLess(time.monotonic() - start, 1.5)

    def test_silent_provider_and_slow_trickle_have_total_deadlines(self):
        for code in ("import time; time.sleep(60)",
                     "import os,time\nwhile True: os.write(1,b'a'); time.sleep(.03)"):
            start = time.monotonic()
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, 'clipboard_timeout'):
                clipboard.read_text(self.producer(code), deadline=.15)
            self.assertLess(time.monotonic() - start, 1.5)

    def test_open_pipe_after_parent_exits_is_also_bounded(self):
        start = time.monotonic()
        with self.assertRaisesRegex(ValueError, 'clipboard_timeout'):
            clipboard.read_text(self.producer("import os,time\nif os.fork()==0: time.sleep(60)"), deadline=.15)
        self.assertLess(time.monotonic() - start, 1.5)

    def test_invalid_utf8_nul_and_failed_providers_are_rejected(self):
        for code in ("import os; os.write(1,b'\\xff')", "import os; os.write(1,b'a\\0b')"):
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, 'clipboard_invalid_text'):
                clipboard.read_text(self.producer(code))
        with self.assertRaisesRegex(ValueError, 'clipboard_unavailable'):
            clipboard.read_text(self.producer('raise SystemExit(1)'))

    def test_cli_never_echoes_provider_errors_or_loads_device_config(self):
        with patch('elgato.clipboard.read_text', side_effect=OSError('private data')), \
             patch('elgato.cli.core.load_config') as config, patch('builtins.print') as output:
            self.assertEqual(main(['clipboard']), 1)
        self.assertEqual(json.loads(output.call_args.args[0]), {'error': 'clipboard_unavailable'})
        config.assert_not_called()


class EditorInventoryTests(unittest.TestCase):
    def test_all_plugin_owned_native_editors_use_guarded_components(self):
        root = Path(__file__).resolve().parents[1]
        for path in root.glob('*.qml'):
            source = path.read_text()
            if path.name not in ('UiField.qml', 'UiTextArea.qml'):
                self.assertIsNone(re.search(r'\b(?:TextField|TextArea|TextInput|TextEdit)\s*\{', source), path.name)
            else:
                self.assertIn('readOnly: true', source)
                self.assertNotRegex(source, r'readOnly\s*=|readOnly:\s*false')
