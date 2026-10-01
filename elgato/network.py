"""Bounded direct device requests with a hard wall-clock deadline."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import threading

from .safety import object_value, parse_json

LIGHT_LIMIT = 64 * 1024
OPENXLR_LIMIT = 1024 * 1024
REQUEST_DEADLINE = 3.0
_SLOTS = threading.BoundedSemaphore(4)
_WORKER = Path(__file__).with_name('http_worker.py')


def request(host, port, path, *, method='GET', payload=None, headers=None,
            limit=LIGHT_LIMIT, mode='light'):
    data = None if payload is None else json.dumps(payload, allow_nan=False).encode()
    spec = {'host': host, 'port': port, 'path': path, 'method': method,
            'data': None if data is None else base64.b64encode(data).decode('ascii'),
            'headers': headers or {}, 'limit': limit, 'mode': mode}
    encoded = json.dumps(spec).encode()
    if len(encoded) > 16 * 1024:
        raise ValueError('Device request is too large')
    if not _SLOTS.acquire(blocking=False):
        raise ValueError('Device request queue is busy')
    try:
        try:
            proc = subprocess.run([sys.executable, '-I', str(_WORKER)],
                                  input=encoded, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  timeout=REQUEST_DEADLINE, check=True)
        except subprocess.TimeoutExpired:
            # subprocess.run kills and reaps the child, including stalled DNS.
            raise ValueError('Device request exceeded its deadline') from None
        except (OSError, subprocess.CalledProcessError):
            raise ValueError('Device request failed') from None
        result = object_value(parse_json(proc.stdout))
        if 'error' in result:
            raise ValueError(result['error'])
        return base64.b64decode(result['body'], validate=True)
    finally:
        _SLOTS.release()
