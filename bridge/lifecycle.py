"""Pipe-bound receiver lifetime; no detached process or persistent receipt queue."""
import os
import threading


class ParentLifetime:
    def __init__(self, stream, terminate=os._exit):
        self.dead = threading.Event()
        def watch():
            try:
                while stream.read(1):
                    pass
            finally:
                self.dead.set()
                # Do not wait for a blocked REST/Socket.IO/SQLite worker on parent death.
                terminate(0)
        self.thread = threading.Thread(target=watch, name='paper-parent-watch', daemon=True)
        self.thread.start()

    def alive(self):
        return not self.dead.is_set()
