"""Application ownership and lifecycle. No module-global catalog or worker instances."""

import threading

from gallery.access import Access
from gallery.catalog import Catalog
from gallery.events import Events
from gallery.images import Images
from gallery.indexer import Indexer
from gallery.instance import Instance
from gallery.jobs import Busy, Resources, Tasks
from gallery.organize import Organize
from gallery.watcher import Watcher


class Service:
    def __init__(self, settings):
        self.settings = settings
        self.catalog = Catalog(settings.data / 'catalog.sqlite')
        self.events = Events()
        self.resources = Resources()
        self.access = Access(self.catalog)
        self.indexer = Indexer(self.catalog, self.events, [settings.data, settings.resources])
        self.tasks = Tasks(self.catalog, self.events, self.resources)
        self.images = Images(self.catalog, self.access, self.resources, settings)
        self.organize = Organize(self.catalog, self.access, self.events, settings.data)
        self.tasks.handlers.update(scan=self.indexer.scan, prewarm=self.images.prewarm,
                                   collect=self.images.collect, delete=self.organize.delete,
                                   build=self._build, analyze=self._analyze, compare=self._compare,
                                   migrate=self._migrate, audit=self._audit)
        self.images.cache_pressure = self._cache_pressure
        self.watcher = Watcher(self.catalog, self.tasks, settings.watch, self.indexer.excluded)
        self.stop_event = threading.Event()
        self.maintenance = None
        self.shutdown_callback = lambda: None
        self.instance = Instance(settings.data / '.gallery.lock')

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

    def _migrate(self, context, payload):
        from gallery.migration import import_legacy
        report = import_legacy(self.catalog, payload['source'], payload['root'], self.indexer, context)
        self.watcher.add(self.catalog.entity('libraries', report['library_id']))
        self.tasks.submit('scan', {'library_id': report['library_id']})
        return report

    def start(self):
        self.instance.acquire()
        self.catalog.execute("UPDATE tasks SET state='interrupted',error='Application stopped' "
                             "WHERE state IN ('queued','running','paused','cancelling')")
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
                self.tasks.submit('scan', {'library_id': library['id']})
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
        while not self.stop_event.wait(600):
            try:
                self.tasks.submit('collect', {})
                for library in self.catalog.libraries():
                    self.watcher.add(library)
                    self.tasks.submit('scan', {'library_id': library['id']})
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
