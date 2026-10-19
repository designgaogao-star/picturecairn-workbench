# -*- coding: utf-8 -*-
"""路径穿越防护的单元测试 ——**零依赖：不需要真实图库，也不需要服务在跑**。

为什么先迁这一组：`_pkg_dir` 是全项目最后一道删除前的路径闸门。
曾经它用 `abspath`（字符串归一化）而不是 `realpath`，结果 `pkg="..."`
在 Windows 上被解析成"组目录本身"—— 一个"删图包"的请求能把整个组删掉。
这类漏洞必须有一条**任何人 clone 下来都能跑**的测试守着。

跑法：
    pytest tests/test_guard.py -v
"""

import os
import sys

import pytest

TOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOL not in sys.path:
    sys.path.insert(0, TOOL)

from gallery import guard, paths  # noqa: E402


@pytest.fixture()
def fake_lib(tmp_path, monkeypatch):
    """造一个最小图库：ROOT 指向 tmp_path，里面有一个组、组里有一个图包。

    注意 monkeypatch 的是 `gallery.paths.ROOT`，不是 `gallery_server.ROOT` ——
    路径校验已经搬进 `gallery.guard`，它动态读 `paths.ROOT`。
    改 server 里的同名变量不会影响 guard（那样会让"校验通过但删错地方"）。
    """
    root = tmp_path / "lib"
    group = root / "[TEST]某作者"
    pkg = group / "某图包"
    pkg.mkdir(parents=True)
    (pkg / "a.jpg").write_bytes(b"x" * 128)

    monkeypatch.setattr(paths, "ROOT", str(root))
    # 组名有 0.5s 缓存，换 ROOT 之后必须强制刷新，否则读到的是上一个用例的目录
    guard.invalidate_names()
    return root, group, pkg


# ---------------------------------------------------------------- _pkg_dir
BAD_PKGS = [
    "...",  # ★ 曾经的真实漏洞：Windows 把 ... 当"上上级"
    ".. ",
    " .",
    ".hidden",
    "..",
    "../..",
    "x/../.. ",
    "C:/Windows",  # 绝对路径
    "",  # 空
]


@pytest.mark.parametrize("bad", BAD_PKGS)
def test_pkg_dir_rejects_traversal(fake_lib, bad):
    """任何越界形态都必须返回 None，绝不能落到组目录本身或 ROOT。"""
    _root, _group, _pkg = fake_lib
    assert guard._pkg_dir("[TEST]某作者", bad) is None


def test_pkg_dir_accepts_real_pkg(fake_lib):
    """正常图包必须能解析出真实目录。"""
    _root, _group, pkg = fake_lib
    got = guard._pkg_dir("[TEST]某作者", "某图包")
    assert got is not None
    assert os.path.realpath(got) == os.path.realpath(str(pkg))


def test_pkg_dir_rejects_nonexistent_pkg(fake_lib):
    """不存在的图包返回 None（isdir 校验）。"""
    assert guard._pkg_dir("[TEST]某作者", "不存在的包") is None


def test_pkg_dir_rejects_unknown_group(fake_lib):
    """组名不在 ROOT 下真实存在时一律拒绝。"""
    assert guard._pkg_dir("不存在的组", "某图包") is None


# ---------------------------------------------------------- safe_media_path
@pytest.mark.parametrize(
    "bad",
    [
        "../外面.jpg",
        "../../review_state.json",
        "子目录/../../外面.jpg",
        "C:/Windows/notepad.exe",
        "",
    ],
)
def test_safe_media_path_rejects(fake_lib, bad):
    assert guard.safe_media_path("[TEST]某作者", bad) is None


def test_safe_media_path_accepts(fake_lib):
    _root, _group, pkg = fake_lib
    got = guard.safe_media_path("[TEST]某作者", os.path.join("某图包", "a.jpg"))
    assert got is not None and os.path.isfile(got)


# ------------------------------------------------------------ 组名校验
@pytest.mark.parametrize("bad", ["", None, 123, "..", ".", "带/斜杠", "带\\反斜杠"])
def test_valid_group_name_rejects(bad):
    assert guard._valid_group_name(bad) is False


def test_valid_group_name_accepts(fake_lib):
    assert guard._valid_group_name("[TEST]某作者") is True
