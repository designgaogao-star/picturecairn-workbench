"""Frozen legacy pHash; display derivatives must never change this algorithm."""

import numpy as np
from PIL import Image
from scipy.fftpack import dct

HASH_VERSION = 'pillow-draft64-lanczos32-dct64-v1'
LEGACY_HASH_VERSION = 'legacy-pillow-thumbnail-or-original-v1'


def phash(path):
    try:
        with Image.open(path) as image:
            image.draft('RGB', (64, 64))
            pixels = np.asarray(image.convert('L').resize((32, 32), Image.Resampling.LANCZOS), dtype=np.float32)
        low = dct(dct(pixels, axis=0), axis=1)[:8, :8]
        return np.packbits((low > np.median(low)).flatten()).tobytes()
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def neighbors(hashes, threshold=8, block=128, checkpoint=lambda: None):
    """Exact Hamming neighborhoods, at most block x N distance values at a time."""
    hashes = np.asarray(hashes, dtype=np.uint8)
    if not len(hashes):
        return
    bits = np.unpackbits(hashes, axis=1).astype(np.float32)
    sums = bits.sum(axis=1)
    for start in range(0, len(bits), block):
        checkpoint()
        end = min(len(bits), start + block)
        distance = sums[start:end, None] + sums[None, :] - 2 * (bits[start:end] @ bits.T)
        for local, row in enumerate(distance):
            i = start + local
            yield i, np.flatnonzero(row[i + 1:] <= threshold) + i + 1
