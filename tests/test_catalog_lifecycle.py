"""WAL stays available between requests without pinning a transaction or leaking on shutdown."""

import contextlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from gallery.app import create_app
from gallery.paths import Settings


def test_idle_service_retains_wal_allows_checkpoint_and_closes_on_lifespan_exit(tmp_path):
    data = tmp_path / 'data'
    database = data / 'catalog.sqlite'
    wal = data / 'catalog.sqlite-wal'
    app = create_app(Settings(data, watch=False, scan_on_start=False))
    with TestClient(app) as client:
        catalog = app.state.service.catalog
        catalog.execute('CREATE TABLE wal_lifecycle(value TEXT NOT NULL)')
        catalog.execute("INSERT INTO wal_lifecycle VALUES('initial')")
        for _ in range(4):
            response = client.post('/api/v1/libraries', json={'path': str(tmp_path / 'missing')})
            assert response.status_code == 404
            catalog.execute("UPDATE wal_lifecycle SET value='retained'")
            assert catalog.one('SELECT value FROM wal_lifecycle')['value'] == 'retained'
            assert wal.exists(), 'An idle request gap must not close/recover the WAL again'
        with contextlib.closing(catalog.connect()) as connection:
            checkpoint = connection.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            assert tuple(checkpoint) == (0, 0, 0), 'The lifetime connection must not pin a read transaction'
        assert wal.exists()
    assert not wal.exists(), 'Lifespan shutdown must release the final WAL handle'
    with contextlib.closing(sqlite3.connect(database)) as connection:
        assert connection.execute('SELECT value FROM wal_lifecycle').fetchone()[0] == 'retained'
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(catalog.close).result()


def test_connection_configuration_failure_closes_the_opened_handle(tmp_path, monkeypatch):
    app = create_app(Settings(tmp_path / 'data', watch=False, scan_on_start=False))
    catalog = app.state.service.catalog
    original_connect = sqlite3.connect
    opened = []

    class FailConfiguration(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if sql == 'PRAGMA synchronous=NORMAL':
                raise sqlite3.OperationalError('synthetic busy during connection configuration')
            return super().execute(sql, *args, **kwargs)

    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs, factory=FailConfiguration)
        opened.append(connection)
        return connection

    try:
        with monkeypatch.context() as patch:
            patch.setattr(sqlite3, 'connect', connect)
            with pytest.raises(sqlite3.OperationalError, match='configuration'):
                catalog.connect()
        assert len(opened) == 1
        with pytest.raises(sqlite3.ProgrammingError, match='closed'):
            opened[0].execute('SELECT 1')
    finally:
        for connection in opened:
            connection.close()
        app.state.service.stop()
