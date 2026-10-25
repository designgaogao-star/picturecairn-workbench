"""Bounded, durable background jobs and a shared foreground-first disk budget."""

import contextlib
import json
import queue
import threading
import time
from collections import defaultdict
from pathlib import Path

from gallery.catalog import new_id


class Cancelled(Exception):
    pass


class Busy(Exception):
    pass


class Resources:
    def __init__(self, decode_bytes=512 * 1024**2):
        self.condition = threading.Condition()
        self.active = set()
        self.waiters = defaultdict(int)
        self.decode_limit = decode_bytes
        self.decode_used = 0
        self.decode_count = 0
        self.decode_waiters = 0

    @contextlib.contextmanager
    def io(self, path, foreground=False, checkpoint=lambda: None):
        volume = Path(path).anchor.lower()
        with self.condition:
            if foreground:
                self.waiters[volume] += 1
        try:
            while True:
                checkpoint()
                with self.condition:
                    if volume not in self.active and (foreground or not self.waiters[volume]):
                        self.active.add(volume)
                        break
                    self.condition.wait(.05)
        finally:
            if foreground:
                with self.condition:
                    self.waiters[volume] -= 1
        try:
            yield
        finally:
            with self.condition:
                self.active.discard(volume)
                self.condition.notify_all()

    @contextlib.contextmanager
    def decode(self, estimate, checkpoint=lambda: None, *, foreground=False):
        if estimate > self.decode_limit:
            raise ValueError('Image exceeds the 512 MiB decode budget; original remains available')
        with self.condition:
            if foreground:
                self.decode_waiters += 1
        try:
            while True:
                checkpoint()
                with self.condition:
                    if (self.decode_count < 2 and self.decode_used + estimate <= self.decode_limit
                            and (foreground or not self.decode_waiters)):
                        self.decode_used += estimate
                        self.decode_count += 1
                        break
                    self.condition.wait(.05)
        finally:
            if foreground:
                with self.condition:
                    self.decode_waiters -= 1
                    self.condition.notify_all()
        try:
            yield
        finally:
            with self.condition:
                self.decode_used -= estimate
                self.decode_count -= 1
                self.condition.notify_all()


class Context:
    def __init__(self, manager, task_id):
        self.manager, self.id = manager, task_id
        self.cancel = threading.Event()
        self.paused = threading.Event()
        self.last_update = 0
        self.progress = 0
        self.total = None
        self.current = ''
        self.partial_result = None
        self.started = False

    def check(self):
        while self.paused.is_set():
            self.check_cancelled()
            self.cancel.wait(.05)
        self.check_cancelled()

    def check_cancelled(self):
        if self.cancel.is_set() or self.manager.stopping.is_set():
            raise Cancelled()

    def update(self, progress=None, total=None, current=None, force=False):
        if progress is not None:
            self.progress = progress
        if total is not None:
            self.total = total
        if current is not None:
            self.current = current
        self.check()
        now = time.monotonic()
        if not force and now - self.last_update < .25:
            return
        self.last_update = now
        self.manager.catalog.execute('UPDATE tasks SET progress=?,total=?,current=?,updated=? WHERE id=?',
                                     (self.progress, self.total, self.current, time.time(), self.id))
        self.manager.events.publish('task', {'id': self.id})

    def io(self, path):
        return self.manager.resources.io(path, checkpoint=self.check)


class Tasks:
    def __init__(self, catalog, events, resources):
        self.catalog, self.events, self.resources = catalog, events, resources
        self.queue = queue.Queue(maxsize=128)
        self.contexts = {}
        self.lock = threading.RLock()
        self.handlers = {}
        self.stopping = threading.Event()
        self.workers = []

    def start(self):
        for _ in range(2):
            worker = threading.Thread(target=self._worker, daemon=True, name='gallery-job')
            self.workers.append(worker)
            worker.start()

    def ensure_capacity(self):
        if self.stopping.is_set() or self.queue.full():
            raise Busy('Background queue is full or stopping')

    def submit(self, kind, payload, deduplicate=True, trigger='user'):
        with self.lock:
            if self.stopping.is_set():
                raise Busy('Background queue is full or stopping')
            targets, _scope = self.catalog.describe_targets(payload)
            for library_id in {target['library_id'] for target in targets if target['library_id']}:
                library = self.catalog.entity('libraries', library_id)
                if library and not library['managed']:
                    raise Busy('Library is no longer managed')
            encoded = json.dumps(payload, sort_keys=True)
            if deduplicate and kind == 'scan':
                pending = self.catalog.rows("SELECT id,payload FROM tasks WHERE kind='scan' "
                                            "AND state IN ('queued','paused') ORDER BY created")
                for old in pending:
                    if self.contexts.get(old['id']) and self.contexts[old['id']].started:
                        continue
                    previous = json.loads(old['payload'])
                    if previous.get('library_id') != payload.get('library_id'):
                        continue
                    merged = {**previous, 'force': previous.get('force', False) or payload.get('force', False)}
                    if previous.get('directory_id') != payload.get('directory_id'):
                        merged.pop('directory_id', None)
                    self.catalog.execute('UPDATE tasks SET payload=?,updated=? WHERE id=?',
                                         (json.dumps(merged, sort_keys=True), time.time(), old['id']))
                    self.events.publish('task', {'id': old['id']})
                    return self.catalog.task(old['id'])
            if deduplicate:
                old = self.catalog.one("SELECT id FROM tasks WHERE kind=? AND payload=? "
                                       "AND state IN ('queued','running','paused')", (kind, encoded)) if kind != 'scan' else None
                if old:
                    return self.catalog.task(old['id'])
            self.ensure_capacity()
            task_id, now = new_id(), time.time()
            self.catalog.execute('INSERT INTO tasks(id,kind,state,payload,created,updated,trigger) VALUES(?,?,?,?,?,?,?)',
                                 (task_id, kind, 'queued', encoded, now, now, trigger))
            self.contexts[task_id] = Context(self, task_id)
            self.queue.put_nowait(task_id)
        self.events.publish('task', {'id': task_id})
        return self.catalog.task(task_id)

    def control(self, task_id, action):
        with self.lock:
            context = self.contexts.get(task_id)
            job = self.catalog.task(task_id)
            allowed = {'pause': ('queued', 'running'), 'resume': ('paused',), 'cancel': ('queued', 'running', 'paused')}
            if not context or action not in allowed or job['state'] not in allowed[action]:
                raise ValueError('Task cannot perform this action in its current state')
            if action == 'cancel':
                context.cancel.set()
                context.paused.clear()
                state = 'cancelling' if context.started else 'cancelled'
            elif action == 'pause':
                if job['kind'] == 'delete':
                    raise ValueError('Delete operations can be cancelled between items but cannot be paused')
                context.paused.set()
                state = 'paused'
            else:
                context.paused.clear()
                state = 'running' if context.started else 'queued'
            self.catalog.execute('UPDATE tasks SET state=?,updated=? WHERE id=?', (state, time.time(), task_id))
            self.events.publish('task', {'id': task_id})
            return self.catalog.task(task_id)

    def _worker(self):
        while not self.stopping.is_set():
            try:
                task_id = self.queue.get(timeout=.1)
            except queue.Empty:
                continue
            with self.lock:
                context = self.contexts[task_id]
                context.started = True
                job = self.catalog.task(task_id)
                if not context.paused.is_set() and not context.cancel.is_set():
                    self.catalog.execute("UPDATE tasks SET state='running',updated=? WHERE id=?", (time.time(), task_id))
            state, result, error = 'completed', None, None
            try:
                context.check()
                result = self.handlers[job['kind']](context, job['payload'])
                context.update(force=True)
            except Cancelled:
                state = 'cancelled'
            except Exception as exc:
                import logging
                logging.getLogger(__name__).exception('Job %s failed', task_id)
                state, error = 'failed', str(exc)
            finally:
                if context.partial_result is not None:
                    result = context.partial_result
                with self.lock:
                    self.catalog.execute('UPDATE tasks SET state=?,result=?,error=?,updated=?,progress=?,total=?,current=? '
                                         'WHERE id=?', (state, json.dumps(result, ensure_ascii=False), error, time.time(),
                                                       context.progress, context.total, context.current, task_id))
                    self.contexts.pop(task_id, None)
                self.queue.task_done()
                self.events.publish('task', {'id': task_id})

    def stop(self):
        self.stopping.set()
        with self.lock:
            for context in self.contexts.values():
                context.cancel.set()
                context.paused.clear()
        for worker in self.workers:
            worker.join(timeout=15)
        self.catalog.execute("UPDATE tasks SET state='interrupted',updated=? "
                             "WHERE state IN ('queued','running','paused','cancelling')", (time.time(),))
