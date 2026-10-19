"""后台索引必须使用当前运行时和当前数据目录。"""

import os
import sys
from types import SimpleNamespace

import pytest

from gallery.api import dedup


@pytest.mark.parametrize("frozen", [False, True])
def test_index_worker_command(tmp_path, monkeypatch, frozen):
    calls = []
    monkeypatch.setattr(dedup, "CACHE", str(tmp_path / "data" / "cache"))
    monkeypatch.setattr(dedup, "_dedup_mod", lambda: SimpleNamespace(_dedup_build_running=lambda: False))
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(
        dedup.subprocess, "Popen", lambda command, **options: calls.append((command, options))
    )

    payload, status = dedup.build_index({"folder": ""})
    assert status == 200 and payload["ok"] is True
    command, options = calls[0]
    assert command[0] == sys.executable
    assert command[1] == ("--build-index" if frozen else os.path.join(dedup.TOOL_DIR, "dedup_build.py"))
    assert command[-1] == str(tmp_path / "data" / "cache" / "dedup_full.log")
    assert command[2:4] == ["--scope", "gap"]
    assert options["stderr"] == dedup.subprocess.STDOUT


def test_index_worker_spawn_failure_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(dedup, "CACHE", str(tmp_path))
    monkeypatch.setattr(dedup, "_dedup_mod", lambda: SimpleNamespace(_dedup_build_running=lambda: False))

    def fail(*args, **options):
        raise OSError("missing runtime")

    monkeypatch.setattr(dedup.subprocess, "Popen", fail)
    payload, status = dedup.build_index({"folder": ""})
    assert status == 500
    assert "missing runtime" in payload["error"]
