"""Small, revision-keyed display caches; never used by live rule execution."""
from collections import OrderedDict
import json
import threading


class ReadCache:
    def __init__(self, entries=12, byte_limit=16*1024*1024):
        self.entries, self.byte_limit = entries, byte_limit
        self.values = OrderedDict()
        self.bytes = 0
        self.lock = threading.RLock()

    def get(self, key, produce):
        with self.lock:
            if key in self.values:
                self.values.move_to_end(key)
                return self.values[key][0]
            value = produce()
            size = len(json.dumps(value, ensure_ascii=False).encode())
            if size <= self.byte_limit:
                self.values[key] = (value, size)
                self.bytes += size
                while len(self.values) > self.entries or self.bytes > self.byte_limit:
                    _, (_, removed) = self.values.popitem(last=False)
                    self.bytes -= removed
            return value
