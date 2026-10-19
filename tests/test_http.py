"""独立临时图库上的 HTTP 回归，不读取或改动真实图库。"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    directory = tmp_path_factory.mktemp("gallery-http")
    library, data = directory / "library", directory / "data"
    album = library / "作者" / "图包"
    album.mkdir(parents=True)
    Image.new("RGB", (2000, 2400), "#b64c62").save(album / "01.jpg")
    Image.new("RGB", (1200, 800), "#265746").save(album / "02.png")
    (album / "clip.mp4").write_bytes(b"video must not be served")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "GALLERY_ROOT": str(library), "GALLERY_DATA": str(data), "PYTHONIOENCODING": "utf-8"}
    project = Path(__file__).resolve().parents[1]
    backend = os.environ.get("GALLERY_TEST_BACKEND")
    command = [backend] if backend else [sys.executable, str(project / "gallery_server.py")]
    with (directory / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command + ["--no-open", "--port", str(port)],
            cwd=project,
            env=env,
            stdout=log,
            stderr=log,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(300):
                if process.poll() is not None:
                    pytest.fail((directory / "server.log").read_text(encoding="utf-8"))
                try:
                    with urllib.request.urlopen(base + "/api/ping", timeout=0.2) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.05)
            else:
                pytest.fail("临时服务未能启动")
            yield base, data
        finally:
            process.terminate()
            process.wait(timeout=10)


def request(server, path, body=None, headers=None):
    base, _data = server
    payload = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        base + path, data=payload, headers={"Content-Type": "application/json", **(headers or {})}
    )
    try:
        response = urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, dict(response.headers), response.read()


def media_path(endpoint, filename):
    return endpoint + "?" + urllib.parse.urlencode({"folder": "作者", "file": "图包/" + filename})


def test_image_listing_and_capabilities(server):
    status, _headers, body = request(server, "/api/state")
    state = json.loads(body)
    assert status == 200 and state["thumb"] is True
    assert state["folders"][0]["media_count"] == 2
    status, _headers, body = request(server, "/api/files?" + urllib.parse.urlencode({"folder": "作者"}))
    files = json.loads(body)["files"]
    assert status == 200 and len(files) == 2
    assert all(item["kind"] == "image" for item in files)


@pytest.mark.parametrize("endpoint", ["/media", "/thumb"])
def test_video_is_not_served(server, endpoint):
    status, _headers, body = request(server, media_path(endpoint, "clip.mp4"))
    assert status == 415
    assert json.loads(body)["error"] == "image only"


def test_image_bytes_range_and_etag(server):
    path = media_path("/media", "01.jpg")
    status, headers, original = request(server, path)
    assert status == 200 and original[:2] == b"\xff\xd8"
    assert int(headers["Content-Length"]) == len(original)
    status, headers, tail = request(server, path, headers={"Range": "bytes=-100"})
    assert status == 206 and tail == original[-100:]
    assert int(headers["Content-Length"]) == 100
    status, _headers, body = request(server, path, headers={"If-None-Match": headers["ETag"]})
    assert status == 304 and body == b""


def test_thumbnail_and_dimensions(server):
    status, headers, body = request(server, media_path("/thumb", "01.jpg"))
    assert status == 200 and body[:2] == b"\xff\xd8"
    assert headers["Content-Type"] == "image/jpeg"
    status, _headers, body = request(server, media_path("/api/dim", "01.jpg"))
    assert status == 200
    assert json.loads(body)["w"] == 2000


@pytest.mark.parametrize("endpoint", ["/api/delete", "/api/delete/pkg", "/api/delete/file"])
def test_permanent_delete_requires_confirmation(server, endpoint):
    status, _headers, _body = request(
        server, endpoint, body={"names": ["作者"], "folder": "作者", "pkg": "图包", "rel": "图包/01.jpg"}
    )
    assert status == 400
    assert request(server, media_path("/media", "01.jpg"))[0] == 200


@pytest.mark.parametrize("folder", ["", "..", "C:/Windows", "_gallery_tool"])
def test_invalid_groups_are_rejected(server, folder):
    status, _headers, _body = request(server, "/api/files?" + urllib.parse.urlencode({"folder": folder}))
    assert status == 400


def test_data_is_written_to_selected_data_directory(server):
    _base, data = server
    assert (data / "cache" / "gallery.db").is_file()
    assert (data / "thumbs").is_dir()


def test_review_updates_share_the_running_server_state(server):
    assert request(server, "/api/review/state", body={"name": "作者", "state": "kept"})[0] == 200
    assert request(server, "/api/review/progress", body={"name": "作者", "index": 1})[0] == 200
    status, _headers, body = request(server, "/api/state")
    assert status == 200
    review = json.loads(body)["review"]["作者"]
    assert review["state"] == "kept"
    assert review["index"] == 1
