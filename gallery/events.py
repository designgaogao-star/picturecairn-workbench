"""SSE is an invalidation channel; reconnecting clients reload catalog and task snapshots."""

import threading
from collections import deque


class Events:
    def __init__(self):
        self.lock = threading.Lock()
        self.items = deque(maxlen=256)
        self.sequence = 0

    def publish(self, kind, data):
        with self.lock:
            self.sequence += 1
            self.items.append({'id': self.sequence, 'event': kind, 'data': data})

    def since(self, sequence):
        with self.lock:
            if self.items and sequence < self.items[0]['id'] - 1:
                return [{'id': self.sequence, 'event': 'reset', 'data': {}}]
            return [item for item in self.items if item['id'] > sequence]
