"""Explicit clipboard reads outside the shell, bounded before text is decoded."""
from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time

LIMIT = 60 * 1024
DEADLINE = 2.0


def read_text(command=None, *, limit=LIMIT, deadline=DEADLINE):
    """Never ask Qt for clipboard data. Stop a producer at limit+1 or deadline."""
    command = command or ['wl-paste', '--no-newline', '--type', 'text/plain']
    proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    content = bytearray()
    end = time.monotonic() + deadline
    try:
        os.set_blocking(proc.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            while True:
                remaining = end - time.monotonic()
                if remaining <= 0:
                    raise ValueError('clipboard_timeout')
                if not selector.select(remaining):
                    raise ValueError('clipboard_timeout')
                data = os.read(proc.stdout.fileno(), min(4096, limit + 1 - len(content)))
                if not data:
                    break
                content.extend(data)
                if len(content) > limit:
                    raise ValueError('clipboard_too_large')
        try:
            result = proc.wait(timeout=max(0.001, end - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise ValueError('clipboard_timeout') from None
        if result:
            raise ValueError('clipboard_unavailable')
        try:
            text = content.decode('utf-8', errors='strict')
        except UnicodeDecodeError:
            raise ValueError('clipboard_invalid_text') from None
        # The native fields show plain text only; reject embedded NULs.
        if '\0' in text:
            raise ValueError('clipboard_invalid_text')
        return text
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        proc.stdout.close()
