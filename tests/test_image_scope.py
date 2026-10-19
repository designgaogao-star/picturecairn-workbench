"""纯图片范围，以及整包清理对其他文件的保护。"""

import shutil

import pytest
from PIL import Image

import dedup_build
import dedup_husk
import dedup_verify
from gallery import scan, store


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "library"
    album = root / "作者" / "图包"
    album.mkdir(parents=True)
    Image.new("RGB", (80, 120), "red").save(album / "b.JPG")
    Image.new("RGB", (120, 80), "blue").save(album / "a.png")
    (album / "clip.mp4").write_bytes(b"not an image")
    (album / "readme.txt").write_text("keep this file", encoding="utf-8")
    monkeypatch.setattr(scan, "ROOT", str(root))
    scan.invalidate_file_caches()
    store.close()
    store.init(str(tmp_path / "data" / "gallery.db"))
    yield root, album
    store.close()
    scan.invalidate_file_caches()


def test_disk_listing_contains_only_images(library):
    _root, album = library
    files = scan.build_media_list("作者")
    assert [item["rel"] for item in files] == ["图包/a.png", "图包/b.JPG"]
    assert {item["kind"] for item in files} == {"image"}
    assert (album / "clip.mp4").exists()


def test_index_scan_does_not_require_the_tool_to_share_a_drive(library, monkeypatch):
    root, _album = library
    monkeypatch.setattr(dedup_build, "TOOL_DIR", "Z:\\unrelated\\tool")
    assert len(dedup_build.scan_images(str(root))) == 2


def test_index_scan_prunes_only_the_tool_directory(tmp_path, monkeypatch):
    tool, sibling = tmp_path / "tool", tmp_path / "tool-images"
    tool.mkdir()
    sibling.mkdir()
    (tool / "cache.jpg").write_bytes(b"cache")
    (sibling / "photo.jpg").write_bytes(b"photo")
    monkeypatch.setattr(dedup_build, "TOOL_DIR", str(tool))
    assert dedup_build.scan_images(str(tmp_path)) == [str(sibling / "photo.jpg")]


def test_existing_database_does_not_restore_video_entries(library):
    files = scan.build_media_list("作者")
    files.append({"rel": "图包/clip.mp4", "album": "图包", "kind": "video", "size": 12})
    fingerprint = scan.folder_fingerprint("作者")
    store.upsert_folder(
        {
            "name": "作者",
            "category": "其他",
            "size": 100,
            "file_count": 4,
            "media_count": 3,
            "fp": fingerprint,
        }
    )
    store.replace_media("作者", files, fingerprint, len(files))

    assert store.media_count("作者") == 2
    assert len(scan.list_media("作者")) == 2
    assert all(item["kind"] == "image" for item in scan.list_media("作者"))
    assert store.conn().execute("SELECT COUNT(*) FROM media").fetchone()[0] == 3


def test_cached_image_label_does_not_allow_non_image_extensions(library):
    store.replace_media("作者", [{"rel": "clip.mp4", "kind": "image", "size": 12}], "fp", 1)
    assert store.all_media("作者") == []


def test_package_comparison_includes_unique_non_image_files(tmp_path, monkeypatch):
    root = tmp_path / "library"
    left, right = root / "作者" / "left", root / "作者" / "right"
    left.mkdir(parents=True)
    right.mkdir()
    Image.new("RGB", (64, 64), "green").save(left / "a.jpg")
    shutil.copy2(left / "a.jpg", right / "a.jpg")
    (left / "notes.txt").write_bytes(b"unique content")
    monkeypatch.setattr(dedup_verify, "ROOT", str(root))
    monkeypatch.setattr(dedup_verify, "_PH_DB", {})
    monkeypatch.setattr(dedup_verify, "_MD5", {})
    monkeypatch.setattr(dedup_verify, "folder_hashes", lambda _folder: {})

    result = dedup_verify.compare_pkgs("作者", "left", "right")
    assert result["drop"]["unique_n"] == 1
    assert result["drop"]["unique"][0]["rel"] == "left/notes.txt"
    verified = dedup_verify.verify(
        [{"folder": "作者", "pkg_drops": [{"pkg": "left", "peer": "right"}]}], log=lambda _message: None
    )
    assert verified[0]["ok"] is False
    assert verified[0]["unmatched"] == ["notes.txt"]


def test_husk_detection_preserves_packages_with_other_content(tmp_path, monkeypatch):
    root = tmp_path / "library"
    album = root / "作者" / "album [100P-100MB]"
    album.mkdir(parents=True)
    (album / "222.jpg").write_bytes(b"ad")
    (album / "clip.mp4").write_bytes(b"unique other content")
    monkeypatch.setattr(dedup_husk, "ROOT", str(root))

    husks, ads, shrunk = dedup_husk.find_husks({"222"}, ["作者"])
    assert husks == []
    assert shrunk == []
    assert ads[0]["drop"] == ["album [100P-100MB]/222.jpg"]
