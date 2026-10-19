# -*- coding: utf-8 -*-
"""pHash 与汉明距离的单元测试 —— 零依赖，自己造图，不需要任何真实素材。

为什么要守这条：整套去重都建立在"**缩放不改变 pHash**"这个假设上 ——
`get_thumb_bytes()` 会拿缩略图算的哈希当原图的哈希存进索引。
假设一旦破了，去重建议就会指向错误的图，而且完全无声。

注意 `dedup_build.phash()` 收的是**文件路径**（内部会先找缩略图缓存、
没命中才读原图），不是 PIL.Image 对象 —— 传 Image 它会静默返回 None。
"""

import io
import os
import sys

import numpy as np
import pytest
from PIL import Image

TOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOL not in sys.path:
    sys.path.insert(0, TOOL)

import dedup_build as db  # noqa: E402


def hamming(a, b):
    assert a is not None and b is not None, "phash 返回 None，说明路径或图片打不开"
    return int(np.unpackbits(np.frombuffer(a, dtype=np.uint8) ^ np.frombuffer(b, dtype=np.uint8)).sum())


def make_gradient(w=512, h=512, seed=0):
    """造一张有结构的图：横向渐变 + 几个随机色块。

    纯色图 / 噪声图的 pHash 会退化（DCT 系数全接近 0），测不出东西，
    所以必须造"有低频结构"的图。
    """
    rng = np.random.default_rng(seed)
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for x in range(w):
        arr[:, x, 0] = int(255 * x / w)
        arr[:, x, 1] = int(255 * (1 - x / w))
        arr[:, x, 2] = 80
    for _ in range(4):
        x0, y0 = int(rng.integers(0, w // 2)), int(rng.integers(0, h // 2))
        arr[y0 : y0 + h // 4, x0 : x0 + w // 4] = rng.integers(0, 256, 3)
    return Image.fromarray(arr)


@pytest.fixture()
def imgs(tmp_path):
    """把若干张合成图落盘，返回路径。"""
    out = {}

    def _save(key, im, fmt="PNG", **kw):
        p = tmp_path / ("%s.%s" % (key, fmt.lower()))
        im.save(p, fmt, **kw)
        out[key] = str(p)
        return str(p)

    _save("a", make_gradient(seed=1))
    _save("b", make_gradient(seed=99))
    _save("s25", make_gradient(seed=2).resize((128, 128), Image.LANCZOS))
    _save("s50", make_gradient(seed=2).resize((256, 256), Image.LANCZOS))
    _save("orig2", make_gradient(seed=2))
    buf = io.BytesIO()
    make_gradient(seed=3).save(buf, "JPEG", quality=55)
    buf.seek(0)
    _save("q55", Image.open(buf), "JPEG", quality=55)
    _save("orig3", make_gradient(seed=3))
    return out


def test_phash_is_64bit(imgs):
    h = db.phash(imgs["a"])
    assert isinstance(h, (bytes, bytearray)) and len(h) * 8 == 64


def test_same_file_same_hash(imgs):
    assert db.phash(imgs["a"]) == db.phash(imgs["a"])


@pytest.mark.parametrize("key,scale", [("s25", 0.25), ("s50", 0.5)])
def test_scaling_does_not_change_hash(imgs, key, scale):
    """缩放后哈希必须几乎不变 —— 这是"缩略图代原图"能成立的前提。"""
    d = hamming(db.phash(imgs["orig2"]), db.phash(imgs[key]))
    assert d <= 4, "缩到 %.0f%% 后偏差 %d，超过阈值 4（去重会因此看错图）" % (scale * 100, d)


def test_jpeg_recompression_stays_close(imgs):
    """重压缩（quality=55）也要保持在近重复区间内。"""
    d = hamming(db.phash(imgs["orig3"]), db.phash(imgs["q55"]))
    assert d <= 8, "quality=55 重压缩后偏差 %d" % d


def test_different_images_are_far(imgs):
    """内容明显不同的两张图，距离必须远大于阈值 —— 否则会误判成重复。"""
    assert hamming(db.phash(imgs["a"]), db.phash(imgs["b"])) > 8


def test_phash_returns_none_for_missing_file(tmp_path):
    """打不开的路径必须返回 None，不能抛异常（扫描时随时会遇到被删的文件）。"""
    assert db.phash(str(tmp_path / "不存在.jpg")) is None
