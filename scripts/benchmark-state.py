#!/usr/bin/env python3
"""Compare state paths with a reproducible 16-page layout and no hardware probes."""
import contextlib
import io
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from elgato import core, visuals  # noqa: E402
from elgato.cli import main  # noqa: E402

config = core.default_config()
config['pages'] = [{'name': f'Page {index + 1}', 'keys': {}} for index in range(16)]
with tempfile.TemporaryDirectory() as directory, \
        patch.object(core, 'load_config', return_value=config), \
        patch.object(visuals, 'CACHE_DIR', Path(directory)), \
        patch('elgato.cli.status', return_value={'running': False, 'decks': [], 'errors': []}), \
        patch('elgato.devices.usb_devices', return_value=[]), \
        patch.object(core, 'cameras', return_value=[]), \
        patch.object(core, 'audio_nodes', return_value=[]), \
        patch('elgato.openxlr.state', return_value={}), \
        patch('elgato.prompter.state', return_value={}):
    results = {}
    for name, args in [('all-pages', ['state']),
                       ('selected-page', ['--local', '--page', '0', 'state']),
                       ('quick-status', ['--quick', 'state'])]:
        times = []
        for _ in range(6):
            output = io.StringIO()
            start = time.perf_counter()
            with contextlib.redirect_stdout(output):
                if main(args):
                    raise SystemExit(output.getvalue())
            times.append(time.perf_counter() - start)
        results[name] = {'median_ms': round(statistics.median(times[1:]) * 1000, 2),
                         'response_bytes': len(output.getvalue().encode())}
    print(json.dumps(results, indent=2))
