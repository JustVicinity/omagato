"""A fixed worker and bounded queue; dial movements are coalesced."""
from collections import OrderedDict
import threading


class ActionQueue:
    def __init__(self, on_error, capacity=32):
        self.capacity = capacity
        self.pending = OrderedDict()
        self.condition = threading.Condition()
        self.on_error = on_error
        self.thread = None
        self.closed = False

    def submit(self, key, callback, amount=None, *, coalesce=False):
        with self.condition:
            if self.closed:
                return False
            # Buttons always get distinct FIFO entries. Only dial turns opt in.
            key = ('dial', key) if coalesce else object()
            if key in self.pending and amount is not None:
                _, previous = self.pending[key]
                if previous is not None:
                    amount = max(-100, min(100, previous + amount))
            elif key not in self.pending and len(self.pending) >= self.capacity:
                return False
            self.pending[key] = (callback, amount)
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, daemon=True, name='omagato-actions')
                self.thread.start()
            self.condition.notify()
            return True

    def _run(self):
        while True:
            with self.condition:
                while not self.pending and not self.closed:
                    self.condition.wait()
                if self.closed:
                    return
                _, (callback, amount) = self.pending.popitem(last=False)
            try:
                callback() if amount is None else callback(amount)
            except Exception as exc:
                self.on_error(str(exc))

    def close(self):
        with self.condition:
            self.closed = True
            self.pending.clear()
            self.condition.notify_all()
