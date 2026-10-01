"""Bounded parsing and private, atomic local storage."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import stat
import tempfile

CONFIG_LIMIT = 512 * 1024
SCRIPT_LIMIT = 60 * 1024


def parse_json(data):
    def invalid_constant(value):
        raise ValueError('Invalid JSON number')
    try:
        result = json.loads(data, parse_constant=invalid_constant)
    except (ValueError, RecursionError) as exc:
        raise ValueError('Invalid JSON response or file') from exc
    pending = [(result, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 32:
            raise ValueError('JSON nesting is too deep')
        if isinstance(item, dict):
            pending.extend((value, depth + 1) for value in item.values())
        elif isinstance(item, list):
            pending.extend((value, depth + 1) for value in item)
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError('Invalid JSON number')
    return result


def object_value(value):
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    return value


def text_value(value, limit=240, *, field='text'):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f'Invalid {field}: expected text of at most {limit} characters')
    return value


def number_value(value, minimum, maximum):
    if type(value) not in (int, float) or not minimum <= value <= maximum or (isinstance(value, float) and not math.isfinite(value)):
        raise ValueError('Invalid numeric value')
    return value


def read_bytes(path, limit, *, secret=False, nofollow=True):
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC
    if nofollow:
        reject_symlink_ancestors(path)
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Expected a regular file')
        if secret and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError('Secret file must be owned by you with private permissions')
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError('File is too large')
        return data


def private_dir(path):
    path = Path(path)
    reject_symlink_ancestors(path)
    if path.is_symlink():
        raise ValueError('Managed directory must not be a symlink')
    missing = []
    parent = path
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        if os.fstat(fd).st_uid != os.getuid():
            raise ValueError('Storage directory must be owned by you')
        os.fchmod(fd, 0o700)
    finally:
        os.close(fd)


def reject_symlink_ancestors(path):
    if any(parent.is_symlink() for parent in Path(path).absolute().parents):
        raise ValueError('Managed path must not have symlink ancestors')


def atomic_write(path, data):
    path = Path(path)
    private_dir(path.parent)
    fd, name = tempfile.mkstemp(prefix='.omagato-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
