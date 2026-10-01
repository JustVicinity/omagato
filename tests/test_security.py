"""Regression tests for malicious devices, files and excessive input events."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import http.client
import hashlib

from elgato import core, http_worker, network, openxlr, prompter, safety, visuals
from elgato.actions import ActionQueue
from elgato.cli import main, poll_light
from elgato.daemon import Worker


@contextmanager
def endpoint(status=200, body=b'{}', headers=None, *, chunked=False, slow=False, port=0):
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            seen.append(dict(self.headers))
            self.send_response(status)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            if chunked:
                self.send_header('Transfer-Encoding', 'chunked')
            self.end_headers()
            try:
                if chunked:
                    self.wfile.write(f'{len(body):X}\r\n'.encode() + body + b'\r\n0\r\n\r\n')
                elif slow:
                    for byte in body:
                        time.sleep(.15)
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                else:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
        do_POST = do_GET
        do_PUT = do_GET
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def exchange_at(server, *, limit=64, method='GET', mode='light'):
    connection_class = http.client.HTTPConnection
    def connection(host, port, timeout):
        return connection_class('127.0.0.1', server.server_port, timeout=timeout)
    spec = {'host': '192.168.1.2' if mode == 'light' else '127.0.0.1',
            'port': 9123 if mode == 'light' else 37890, 'mode': mode,
            'method': method, 'path': '/elgato/lights', 'data': None,
            'headers': {'Authorization': 'Bearer audit-dummy-token'} if mode == 'loopback' else {},
            'limit': limit}
    with patch.object(http_worker.http.client, 'HTTPConnection', side_effect=connection):
        return http_worker.exchange(spec)


class HttpSecurityTests(unittest.TestCase):
    def test_exact_limit_and_no_length_header(self):
        with endpoint(body=b'x' * 64) as (server, _):
            self.assertEqual(exchange_at(server), b'x' * 64)

    def test_oversized_normal_and_chunked_responses(self):
        for chunked in (False, True):
            with self.subTest(chunked=chunked), endpoint(body=b'x' * 65, chunked=chunked) as (server, _):
                with self.assertRaisesRegex(ValueError, 'too large'):
                    exchange_at(server)

    def test_invalid_oversized_and_incomplete_content_length(self):
        for length, message in [('not-a-number', 'Invalid'), ('1000000', 'too large'), ('12', 'Incomplete')]:
            with self.subTest(length=length), endpoint(headers={'Content-Length': length}) as (server, _):
                with self.assertRaisesRegex(ValueError, message):
                    exchange_at(server)

    def test_redirects_never_contact_target_or_forward_token(self):
        for mode in ('light', 'loopback'):
            for status in (301, 302, 303, 307, 308):
                with self.subTest(mode=mode, status=status), endpoint() as (target, target_seen):
                    headers = {'Location': f'http://127.0.0.1:{target.server_port}/capture'}
                    with endpoint(status, b'x' * 1024, headers) as (origin, _):
                        with self.assertRaisesRegex(ValueError, 'redirects'):
                            exchange_at(origin, mode=mode)
                    self.assertEqual(target_seen, [])

    def test_reject_error_bodies_and_compression(self):
        for status, headers in ((500, {}), (200, {'Content-Encoding': 'gzip'})):
            with endpoint(status, b'x' * 1024, headers) as (server, _):
                with self.assertRaises(ValueError):
                    exchange_at(server)

    def test_empty_acknowledgements(self):
        for method in ('PUT', 'POST'):
            with endpoint(204, b'') as (server, _):
                self.assertEqual(exchange_at(server, method=method), b'')

    def test_hard_deadline_kills_and_reaps_slow_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = Path(directory) / 'slow_worker.py'
            pidfile = Path(directory) / 'pid'
            worker.write_text(f'import os,time\nopen({str(pidfile)!r}, "w").write(str(os.getpid()))\ntime.sleep(30)\n')
            started = time.monotonic()
            with patch.object(network, '_WORKER', worker), patch.object(network, 'REQUEST_DEADLINE', .25):
                with self.assertRaisesRegex(ValueError, 'deadline'):
                    network.request('192.168.1.2', 9123, '/')
            self.assertLess(time.monotonic() - started, 2)
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pidfile.read_text()), 0)

    def test_slow_trickle_response_hits_overall_deadline(self):
        with endpoint(body=b'x' * 20, slow=True) as (server, _), tempfile.TemporaryDirectory() as directory:
            worker = Path(directory) / 'fixture_worker.py'
            worker.write_text(
                'import runpy,http.client\n'
                'original = http.client.HTTPConnection\n'
                f'http.client.HTTPConnection = lambda host,port,timeout: original("127.0.0.1",{server.server_port},timeout=timeout)\n'
                f'runpy.run_path({str(network._WORKER)!r},run_name="__main__")\n')
            with patch.object(network, '_WORKER', worker), patch.object(network, 'REQUEST_DEADLINE', .5):
                started = time.monotonic()
                with self.assertRaisesRegex(ValueError, 'deadline'):
                    network.request('192.168.1.2', 9123, '/')
                self.assertLess(time.monotonic() - started, 2)

    def test_redirect_body_is_never_read(self):
        with endpoint(302, b'x' * 1024, {'Location': 'http://127.0.0.1:1/'}) as (server, _), \
             patch.object(http.client.HTTPResponse, 'read', side_effect=AssertionError('body consumed')) as read:
            with self.assertRaisesRegex(ValueError, 'redirects'):
                exchange_at(server)
            read.assert_not_called()

    def test_environment_proxies_are_ignored(self):
        with endpoint() as (server, _), patch.dict(os.environ, {'http_proxy': 'http://127.0.0.1:1',
                                                               'HTTP_PROXY': 'http://127.0.0.1:1'}):
            self.assertEqual(exchange_at(server), b'{}')

    def test_dns_stall_is_terminated(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = Path(directory) / 'dns_fixture.py'
            worker.write_text('import runpy,socket,time\n'
                              'socket.getaddrinfo=lambda *a,**k: time.sleep(30)\n'
                              f'runpy.run_path({str(network._WORKER)!r},run_name="__main__")\n')
            with patch.object(network, '_WORKER', worker), patch.object(network, 'REQUEST_DEADLINE', .25):
                with self.assertRaisesRegex(ValueError, 'deadline'):
                    network.request('lamp.local', 9123, '/')

    def test_openxlr_round_trip_through_actual_worker(self):
        fixture = endpoint(body=b'{"type":"state","connected":false}', port=37890)
        try:
            server, seen = fixture.__enter__()
        except OSError as exc:
            self.skipTest(f'local OpenXLR test port is unavailable: {exc}')
        try:
            with tempfile.TemporaryDirectory() as directory:
                token = Path(directory) / 'token'
                safety.atomic_write(token, b'audit-dummy-token')
                with patch.object(openxlr, 'token_path', return_value=token):
                    self.assertTrue(openxlr.state()['available'])
                self.assertEqual(seen[0].get('Authorization'), 'Bearer audit-dummy-token')
        finally:
            fixture.__exit__(None, None, None)

    def test_token_uses_pipe_not_arguments_and_output(self):
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / 'token'
            safety.atomic_write(token, b'audit-private-token')
            result = subprocess.CompletedProcess([], 0, b'{"body":"e30="}')
            with patch.object(openxlr, 'token_path', return_value=token), \
                 patch.object(network.subprocess, 'run', return_value=result) as run:
                self.assertEqual(openxlr._call('/state'), {})
                self.assertNotIn('audit-private-token', repr(run.call_args.args))
                self.assertIn(b'audit-private-token', run.call_args.kwargs['input'])

    def test_echoed_token_is_redacted_from_state_and_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / 'token'
            safety.atomic_write(token, b'audit-private-token')
            body = b'{"type":"state","warning":"echo audit-private-token"}'
            with patch.object(openxlr, 'token_path', return_value=token), \
                 patch.object(network, 'request', return_value=body):
                result = openxlr.state()
                self.assertNotIn('audit-private-token', repr(result))
                self.assertEqual(result['warning'], 'echo [redacted]')

    def test_foreign_user_peer_is_rejected_before_authentication(self):
        sock = Mock()
        sock.getsockname.return_value = ('127.0.0.1', 12345)
        sock.getpeername.return_value = ('127.0.0.1', 37890)
        row = '0: 0100007F:9402 0100007F:3039 01 0 0 0 999999\n'
        from io import StringIO
        with patch('builtins.open', return_value=StringIO(row)):
            with self.assertRaisesRegex(ValueError, 'peer'):
                http_worker.verify_local_peer(sock)

    def test_host_policy(self):
        for host in ('192.168.1.2', 'key-light.local', 'fd00::2', '203.0.113.2'):
            self.assertEqual(core.validate_light(host), host)
        for host in ('127.0.0.1', 'localhost', 'example.com', '0177.0.0.1', '0.0.0.0',
                     '224.0.0.1', 'http://192.168.1.2', 'lamp.local:99', '-lamp.local'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                core.validate_light(host)

    def test_local_dns_is_pinned_and_public_answers_rejected(self):
        spec = {'host': 'lamp.local', 'port': 9123, 'mode': 'light'}
        answer = [(2, 1, 6, '', ('8.8.8.8', 9123))]
        with patch.object(http_worker.socket, 'getaddrinfo', return_value=answer), \
             patch.object(http_worker.http.client, 'HTTPConnection') as connection:
            with self.assertRaisesRegex(ValueError, 'outside'):
                http_worker.exchange(spec)
            connection.assert_not_called()


class SchemaSecurityTests(unittest.TestCase):
    def test_all_four_light_paths_use_same_bounded_transport(self):
        response = b'{"lights":[{"on":1,"brightness":50,"temperature":200,"extra":"ignored"}]}'
        with patch.object(network, 'request', return_value=response) as request:
            self.assertNotIn('extra', core.light_state('192.168.1.2'))
            core.light_info('192.168.1.2')
            core.rename_light('192.168.1.2', 'New name')
            core.identify_light('192.168.1.2')
            self.assertEqual(request.call_count, 4)
        for call in (core.light_state, core.light_info,
                     lambda host: core.rename_light(host, 'New name'), core.identify_light):
            with patch.object(network, 'request', side_effect=ValueError('too large')):
                with self.assertRaisesRegex(ValueError, 'too large'):
                    call('192.168.1.2')

    def test_invalid_light_state_produces_json_cli_error(self):
        for body in (b'[]', b'{"lights":[1]}', b'{"lights":[{"on":2}]}', b'{"lights":{}}'):
            with self.subTest(body=body), patch.object(network, 'request', return_value=body), \
                 patch.object(core, 'load_config', return_value=core.default_config()), patch('builtins.print') as output:
                self.assertEqual(main(['add-light', '192.168.1.2']), 1)
                self.assertIn('error', json.loads(output.call_args.args[0]))

    def test_invalid_openxlr_shapes_always_return_unavailable(self):
        for raw in ({'capabilities': [1]}, {'capabilities': {'xlrInputs': 'many'}},
                    {'mixer': {'mixes': [1]}}, {'device': []}, {'state': {'gainDb': float('nan')}}):
            with self.subTest(raw=raw), patch.object(openxlr, 'raw_state', return_value=raw):
                self.assertFalse(openxlr.state()['available'])

    def test_json_rejects_depth_and_nonfinite_numbers(self):
        for body in ('[' * 40 + '0' + ']' * 40, '[' * 1200 + '0' + ']' * 1200, '{"n":NaN}', '{"n":1e999}'):
            with self.subTest(body=body[:40]), self.assertRaises(ValueError):
                safety.parse_json(body)
        with self.assertRaises(ValueError):
            safety.number_value(10 ** 1000, 0, 100)

    def test_offline_poll_backoff(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'CONFIG_DIR', Path(directory)), \
             patch.object(core, 'light_state', side_effect=ValueError('Offline')) as probe:
            light = {'host': '192.168.1.2', 'name': 'Lamp'}
            self.assertEqual(poll_light(light)['error'], 'Offline')
            self.assertEqual(poll_light(light)['error'], 'Offline')
            probe.assert_called_once()


class FileSecurityTests(unittest.TestCase):
    def test_bounded_reads_and_private_atomic_symlink_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory) / 'outside'
            outside.write_bytes(b'original')
            path = Path(directory) / 'storage' / 'data'
            path.parent.mkdir()
            path.symlink_to(outside)
            with self.assertRaises(OSError):
                safety.read_bytes(path, 20)
            safety.atomic_write(path, b'new')
            self.assertEqual(outside.read_bytes(), b'original')
            self.assertEqual(path.read_bytes(), b'new')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            with self.assertRaises(ValueError):
                safety.read_bytes(path, 2)

    def test_new_managed_parent_directories_are_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config' / 'scripts' / 'Demo.md'
            safety.atomic_write(path, b'private')
            for parent in (path.parent, path.parent.parent):
                self.assertEqual(parent.stat().st_mode & 0o777, 0o700)

    def test_unsafe_secret_permissions_and_symlink_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / 'token'
            token.write_bytes(b'example')
            token.chmod(0o644)
            with self.assertRaises(ValueError):
                safety.read_bytes(token, 512, secret=True)
            link = Path(directory) / 'link'
            link.symlink_to(directory, target_is_directory=True)
            with self.assertRaises((OSError, ValueError)):
                safety.atomic_write(link / 'new', b'unsafe')

    def test_image_pixel_limit_before_decoding(self):
        from PIL import Image
        # Highly compressed file below 10 MiB, above the plugin's pixel budget.
        image = Image.new('1', (5000, 4000))
        data = BytesIO()
        image.save(data, 'PNG')
        with patch('PIL.ImageOps.exif_transpose') as decode:
            with self.assertRaisesRegex(ValueError, 'dimensions'):
                visuals.decode_image(data.getvalue())
            decode.assert_not_called()

    def test_image_import_hash_and_pixels_use_same_snapshot(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'CONFIG_DIR', Path(directory) / 'config'):
            source = Path(directory) / 'icon.png'
            Image.new('RGB', (10, 10), '#123456').save(source)
            snapshot = source.read_bytes()
            decoder = visuals.decode_image
            def swap(data):
                Image.new('RGB', (10, 10), '#ffffff').save(source)
                return decoder(data)
            with patch.object(visuals, 'decode_image', side_effect=swap):
                stored = Path(visuals.import_icon(source))
            self.assertEqual(stored.stem, hashlib.sha256(snapshot).hexdigest()[:20])
            with Image.open(stored) as image:
                self.assertEqual(image.getpixel((0, 0)), (18, 52, 86, 255))

    def test_prompter_write_does_not_follow_existing_file_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / 'outside'
            outside.write_text('keep')
            scripts = root / 'scripts'
            scripts.mkdir()
            (scripts / 'Demo.md').symlink_to(outside)
            with patch.object(prompter, 'SCRIPTS_DIR', scripts), \
                 patch.object(core, 'CONFIG_FILE', root / 'config' / 'config.json'):
                prompter.save_script('Demo', 'new')
            self.assertEqual(outside.read_text(), 'keep')
            self.assertEqual((scripts / 'Demo.md').read_text(), 'new')

    def test_installer_guards_reject_unsafe_paths(self):
        guard = Path(__file__).resolve().parents[1] / 'scripts/path-guards.sh'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'link').symlink_to(root, target_is_directory=True)
            for path in ('relative/venv', '/venv', str(root / 'link' / 'venv'), str(root) + '/../venv'):
                with self.subTest(path=path):
                    result = subprocess.run(['bash', '-c', 'source "$1"; guard_managed_path "$2" venv',
                                             'audit', str(guard), path], capture_output=True)
                    self.assertNotEqual(result.returncode, 0)
            result = subprocess.run(['bash', '-c', 'source "$1"; guard_managed_path "$2" venv',
                                     'audit', str(guard), str(root / 'venv')], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_svg_rendering_in_resource_limited_worker(self):
        renderer = core.shutil_which('rsvg-convert')
        if renderer is None:
            self.skipTest('optional SVG renderer is not installed')
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="red"/></svg>'
        result = subprocess.run([os.sys.executable, '-I', str(Path(visuals.__file__).with_name('svg_worker.py')), renderer],
                                input=svg, capture_output=True, timeout=5, check=True)
        with visuals.decode_image(result.stdout) as image:
            self.assertEqual(image.size, (256, 256))

    def test_configuration_resource_limits_preserve_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            safety.atomic_write(path, b'original')
            config = core.default_config()
            config['pages'] *= 17
            with patch.object(core, 'CONFIG_FILE', path), self.assertRaises(ValueError):
                core.save_config(config)
            self.assertEqual(path.read_bytes(), b'original')

    def test_config_and_prompter_read_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_bytes(b'x' * (safety.CONFIG_LIMIT + 1))
            with patch.object(core, 'CONFIG_FILE', path), self.assertRaises(ValueError):
                core.load_config()
            path = Path(directory) / 'Demo.md'
            path.write_bytes(b'x' * (safety.SCRIPT_LIMIT + 1))
            with patch.object(prompter, 'SCRIPTS_DIR', Path(directory)), patch.object(prompter, 'monitors', return_value=[]):
                self.assertEqual(prompter.state({'prompter': {'script': 'Demo'}})['text'], '')

    def test_macro_prevalidation_prevents_partial_execution(self):
        action = {'type': 'multi', 'steps': [{'type': 'command', 'value': 'echo harmless'}, {'type': 'multi', 'steps': []}]}
        with patch.object(core.subprocess, 'run') as run, self.assertRaises(ValueError):
            core.run_action(action)
        run.assert_not_called()


class ResourceSecurityTests(unittest.TestCase):
    def test_repeated_buttons_keep_fifo_when_worker_is_busy(self):
        for amount in (None, 0):
            with self.subTest(amount=amount):
                active, release, completed = threading.Event(), threading.Event(), threading.Event()
                errors, values = [], []
                queue = ActionQueue(errors.append, capacity=2)
                def block():
                    active.set()
                    release.wait(3)
                def first(value=None):
                    values.append('first')
                def second(value=None):
                    values.append('second')
                    completed.set()
                try:
                    self.assertTrue(queue.submit('busy', block))
                    self.assertTrue(active.wait(1))
                    self.assertTrue(queue.submit('same-button', first, amount))
                    self.assertTrue(queue.submit('same-button', second, amount))
                    self.assertEqual(len(queue.pending), 2)
                    self.assertFalse(queue.submit('same-button', first, amount))
                    release.set()
                    self.assertTrue(completed.wait(1))
                    self.assertEqual(values, ['first', 'second'])
                    self.assertEqual(errors, [])
                finally:
                    release.set()
                    queue.close()
                    queue.thread.join(2)

    def test_controller_preserves_repeated_keys_and_dial_pushes(self):
        from StreamDeck.Devices.StreamDeck import DialEventType
        config = core.default_config()
        config['pages'][0]['keys']['0'] = {'type': 'volume', 'value': 'mute'}
        config['dials']['0'] = {'mode': 'volume'}
        with patch.object(core, 'load_config', return_value=config):
            worker = Worker()
        deck = Mock()
        deck.id.return_value = 'test-deck'
        active, release, completed = threading.Event(), threading.Event(), threading.Event()
        def block():
            active.set()
            release.wait(3)
        try:
            worker.actions.submit('busy', block)
            self.assertTrue(active.wait(1))
            with patch('elgato.daemon.time.monotonic', side_effect=[1, 1.2]):
                worker.on_key(deck, 0, False)
                worker.on_key(deck, 0, False)
            worker.on_dial(deck, 0, DialEventType.PUSH, False)
            worker.on_dial(deck, 0, DialEventType.PUSH, False)
            self.assertEqual(len(worker.actions.pending), 4)
            worker.actions.submit('done', completed.set)
            with patch.object(core, 'run_action') as action:
                release.set()
                self.assertTrue(completed.wait(1))
                self.assertEqual(action.call_count, 4)
        finally:
            release.set()
            worker.actions.close()
            worker.actions.thread.join(2)

    def test_bounded_queue_and_dial_coalescing(self):
        active = threading.Event()
        release = threading.Event()
        completed = threading.Event()
        errors = []
        queue = ActionQueue(errors.append, capacity=2)
        def block():
            active.set()
            release.wait(2)
        values = []
        def dial(amount):
            values.append(amount)
            completed.set()
        try:
            self.assertTrue(queue.submit('block', block))
            self.assertTrue(active.wait(1))
            self.assertTrue(queue.submit('dial', dial, 1, coalesce=True))
            self.assertTrue(queue.submit('dial', dial, 3, coalesce=True))
            self.assertTrue(queue.submit('key', lambda: None))
            self.assertFalse(queue.submit('overflow', lambda: None))
            self.assertEqual(len(queue.pending), 2)
            release.set()
            self.assertTrue(completed.wait(1))
            self.assertEqual(values, [4])
            self.assertEqual(errors, [])
        finally:
            release.set()
            queue.close()
            queue.thread.join(2)

    def test_bounded_error_history_and_log_rate(self):
        with patch.object(core, 'load_config', return_value=core.default_config()):
            worker = Worker()
        with patch('elgato.daemon.LOG.warning') as log:
            for _ in range(100):
                worker.record_error('x' * 1000)
            self.assertEqual(len(worker.errors), 32)
            self.assertTrue(all(len(error) == 240 for error in worker.errors))
            self.assertLessEqual(log.call_count, 1)

    def test_process_launch_limit(self):
        running = Mock()
        running.poll.return_value = None
        with patch.object(core, '_CHILDREN', [running] * 32), patch.object(core.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ValueError, 'Too many'):
                core.run_action({'type': 'command', 'value': 'echo hello'})
            popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
