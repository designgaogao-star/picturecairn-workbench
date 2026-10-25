"""Application ownership and lifecycle. No module-global catalog or worker instances."""

import contextlib
import threading
from pathlib import Path

from gallery.access import Access
from gallery.catalog import Catalog
from gallery.events import Events
from gallery.images import Images
from gallery.indexer import Indexer
from gallery.instance import Instance
from gallery.jobs import Busy, Resources, Tasks
from gallery.libraries import Libraries
from gallery.organize import Organize
from gallery.watcher import Watcher


class Service:
    def __init__(self, settings):
        self.settings = settings
        settings.data.mkdir(parents=True, exist_ok=True)
        self.instance = Instance(settings.data / '.gallery.lock')
        self.instance.acquire()
        try:
            self.catalog = Catalog(settings.data / 'catalog.sqlite')
        except Exception:
            self.instance.release()
            raise
        self.events = Events()
        self.resources = Resources()
        self.access = Access(self.catalog)
        self.indexer = Indexer(self.catalog, self.events, [settings.data, settings.resources, settings.application])
        for imported in self.catalog.rows('SELECT source FROM imports'):
            self._exclude_legacy(imported['source'])
        self.tasks = Tasks(self.catalog, self.events, self.resources)
        self.images = Images(self.catalog, self.access, self.resources, settings)
        self.organize = Organize(self.catalog, self.access, self.events, settings.data)
        self.tasks.handlers.update(scan=self.indexer.scan, prewarm=self.images.prewarm,
                                   collect=self.images.collect, delete=self._delete,
                                   build=self._build, analyze=self._analyze, compare=self._compare,
                                   migrate=self._migrate, audit=self._audit)
        self.images.cache_pressure = self._cache_pressure
        self.watcher = Watcher(self.catalog, self.tasks, settings.watch, self.indexer.excluded)
        self.libraries = Libraries(self.catalog, self.tasks, self.watcher, self.events)
        self.stop_event = threading.Event()
        self.maintenance = None
        self.shutdown_callback = lambda: None

    def _dedup(self):
        from gallery.dedup import Dedup
        return Dedup(self.catalog, self.access, self.resources, self.indexer)

    def _build(self, context, payload):
        return self._dedup().build(context, payload)

    def _analyze(self, context, payload):
        return self._dedup().analyze(context, payload)

    def _compare(self, context, payload):
        return self._dedup().compare(context, payload)

    def _audit(self, context, payload):
        from gallery.audit import Audit
        return Audit(self.catalog).run(context, payload)

    def _delete(self, context, payload):
        libraries = set()
        for target in payload['targets']:
            table = {'image': 'files', 'package': 'packages', 'group': 'directories'}[target['kind']]
            row = self.catalog.entity(table, target['id'])
            if row:
                libraries.add(row['library_id'])
        with contextlib.ExitStack() as stack:
            for library_id in sorted(libraries):
                stack.enter_context(self.indexer.exclusive(context, library_id))
            return self.organize.delete(context, payload)

    def _migrate(self, context, payload):
        from gallery.migration import import_legacy
        report = import_legacy(self.catalog, payload['source'], payload['root'], self.indexer, context)
        self._exclude_legacy(payload['source'])
        self.watcher.add(self.catalog.entity('libraries', report['library_id']))
        self.tasks.submit('scan', {'library_id': report['library_id'], 'force': True})
        return report

    def _exclude_legacy(self, source):
        source = Path(source).resolve()
        roots = {Path(library['path']) for library in self.catalog.rows('SELECT path FROM libraries')}
        excluded = [source / 'cache', source / 'thumbs'] if source in roots else [source]
        self.indexer.excluded.update(excluded)

    def start(self):
        from gallery.migration import restore_pending_positions
        restore_pending_positions(self.catalog)
        self.catalog.execute("UPDATE tasks SET state='interrupted',error='Application stopped' "
                             "WHERE state IN ('queued','running','paused','cancelling')")
        self.catalog.execute("UPDATE libraries SET scan_status=CASE WHEN scan_status='scanning' "
                             "THEN 'interrupted' ELSE 'unscanned' END WHERE scan_status IN ('scanning','pending')")
        existing_libraries = self.catalog.libraries()
        self.tasks.start()
        if self.settings.legacy and self.settings.root:
            self.tasks.submit('migrate', {'source': str(self.settings.legacy), 'root': str(self.settings.root)})
        elif self.settings.root:
            self.catalog.add_library(self.settings.root)
            existing_libraries = self.catalog.libraries()
        for library in existing_libraries:
            if self.settings.legacy and self.settings.root and library['path'] == str(self.settings.root):
                continue
            self.watcher.add(library)
            if self.settings.scan_on_start:
                self.tasks.submit('scan', {'library_id': library['id'], 'force': True}, trigger='startup')
        self.maintenance = threading.Thread(target=self._maintain, daemon=True, name='gallery-maintenance')
        self.maintenance.start()

    def _cache_pressure(self):
        total = self.catalog.one('SELECT COALESCE(SUM(size),0) n FROM cache_entries')['n']
        if total > self.settings.cache_limit:
            try:
                self.tasks.submit('collect', {})
            except Busy:
                pass

    def _maintain(self):
        cycles = 0
        while not self.stop_event.wait(self.settings.maintenance_interval):
            cycles += 1
            try:
                self.tasks.submit('collect', {}, trigger='maintenance')
                if self.settings.scan_on_start:
                    for library in self.catalog.libraries():
                        self.watcher.add(library)
                        self.tasks.submit('scan', {'library_id': library['id'], 'force': cycles % 6 == 0},
                                          trigger='maintenance')
            except Busy:
                continue

    def stop(self):
        self.stop_event.set()
        self.watcher.stop()
        self.tasks.stop()
        self.images.stop()
        if self.maintenance:
            self.maintenance.join(timeout=2)
        self.instance.release()
