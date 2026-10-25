"""The public-release check catches private paths without blocking examples."""

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts import public_release_check as release


def make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for name in release.REQUIRED_FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("public\n", encoding="utf-8")
    (root / "package.json").write_text(
        json.dumps(
            {
                "version": "0.0.0-dev",
                "releaseChannel": "development",
                "releaseLabel": "开发预览（未发布）",
            }
        ),
        encoding="utf-8",
    )
    return root


def fake_git(monkeypatch, names, remote=""):
    def run(command, **kwargs):
        if command[:2] == ["git", "ls-files"]:
            return subprocess.CompletedProcess(command, 0, ("\0".join(names) + "\0").encode(), b"")
        if command[:2] == ["git", "remote"]:
            return subprocess.CompletedProcess(command, 0, remote, "")
        raise AssertionError(command)

    monkeypatch.setattr(release.subprocess, "run", run)


def test_public_check_rejects_private_paths(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    secret = root / "docs/history.md"
    secret.parent.mkdir(exist_ok=True)
    secret.write_text("原目录：F:\\图库\\private\n", encoding="utf-8")
    names = [*release.REQUIRED_FILES, "package.json", "docs/history.md"]
    fake_git(monkeypatch, names)

    report = release.check(root)

    assert not report["passed"]
    assert not report["publish_ready"]
    assert report["personal_paths"]["findings"] == [{"path": "docs/history.md", "line": "1"}]


def test_public_check_allows_generic_development_examples(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    example = root / "README.md"
    example.write_text("Use C:\\Temp\\stillmark-dev and D:\\Pictures\\sample.\n", encoding="utf-8")
    fake_git(monkeypatch, [*release.REQUIRED_FILES, "package.json"])

    report = release.check(root)

    assert report["personal_paths"]["passed"]
    assert report["development_metadata"]["passed"]
    assert not report["publish_ready"]


def test_public_check_does_not_infer_remote_acceptance(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    fake_git(monkeypatch, [*release.REQUIRED_FILES, "package.json"], remote="origin\n")

    report = release.check(root)

    assert report["passed"]
    assert report["external"]["git_remote_configured"]
    assert report["external"]["github_repository_created"] is None
    assert report["publish_ready"] is None


def test_public_check_cli_prints_valid_utf8_under_cp1252(tmp_path):
    root = make_repo(tmp_path)
    subprocess.run(["git", "init", "--quiet", str(root)], check=True, capture_output=True)

    result = subprocess.run(
        [sys.executable, str(Path(release.__file__).resolve()), "--root", str(root), "--json"],
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        capture_output=True,
        encoding="utf-8",
        check=True,
    )

    report = json.loads(result.stdout)
    assert report["passed"]
    assert report["development_metadata"]["release_label"] == "开发预览（未发布）"
