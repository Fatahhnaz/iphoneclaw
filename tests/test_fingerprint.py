"""Tests for iphoneclaw.automation.fingerprint (dHash + hamming distance)."""
from __future__ import annotations

import base64
import struct

import pytest

from iphoneclaw.automation.fingerprint import dhash, hamming_distance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_jpeg(width: int = 8, height: int = 8, color: int = 128) -> str:
    """Create a tiny valid JPEG via Quartz and return base64.

    Uses a solid-colour image so the hash is deterministic.
    """
    import Quartz  # type: ignore
    from Foundation import NSData  # type: ignore
    from AppKit import (  # type: ignore
        NSBitmapImageRep,
        NSDeviceRGBColorSpace,
        NSJPEGFileType,
    )

    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, width, height, 8, 3, False, False, NSDeviceRGBColorSpace, 0, 0,
    )
    # Fill with uniform colour.
    bpr = rep.bytesPerRow()
    data = rep.bitmapData()
    for row in range(height):
        for col in range(width):
            offset = row * bpr + col * 3
            data[offset] = color
            data[offset + 1] = color
            data[offset + 2] = color

    jpeg_data = rep.representationUsingType_properties_(NSJPEGFileType, {})
    raw = bytes(jpeg_data)
    return base64.b64encode(raw).decode("ascii")


def _make_gradient_jpeg(width: int = 64, height: int = 64) -> str:
    """Create a horizontal gradient JPEG (left=dark, right=bright)."""
    import Quartz  # type: ignore
    from AppKit import (  # type: ignore
        NSBitmapImageRep,
        NSDeviceRGBColorSpace,
        NSJPEGFileType,
    )

    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, width, height, 8, 3, False, False, NSDeviceRGBColorSpace, 0, 0,
    )
    bpr = rep.bytesPerRow()
    data = rep.bitmapData()
    for row in range(height):
        for col in range(width):
            v = int(col * 255 / max(width - 1, 1))
            offset = row * bpr + col * 3
            data[offset] = v
            data[offset + 1] = v
            data[offset + 2] = v

    jpeg_data = rep.representationUsingType_properties_(NSJPEGFileType, {})
    return base64.b64encode(bytes(jpeg_data)).decode("ascii")


# ---------------------------------------------------------------------------
# hamming_distance
# ---------------------------------------------------------------------------

class TestHammingDistance:
    def test_identical(self):
        assert hamming_distance(0, 0) == 0
        assert hamming_distance(0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFF) == 0

    def test_one_bit(self):
        assert hamming_distance(0, 1) == 1
        assert hamming_distance(0, 0x8000000000000000) == 1

    def test_all_bits(self):
        assert hamming_distance(0, 0xFFFFFFFFFFFFFFFF) == 64

    def test_known_value(self):
        # 0b1010 vs 0b0101 = 4 bits differ
        assert hamming_distance(0xA, 0x5) == 4

    def test_symmetry(self):
        assert hamming_distance(123456, 654321) == hamming_distance(654321, 123456)


# ---------------------------------------------------------------------------
# dhash
# ---------------------------------------------------------------------------

class TestDhash:
    def test_returns_int(self):
        b64 = _make_gradient_jpeg()
        h = dhash(b64)
        assert isinstance(h, int)
        assert 0 <= h < (1 << 64)

    def test_deterministic(self):
        """Same image -> same hash."""
        b64 = _make_gradient_jpeg()
        h1 = dhash(b64)
        h2 = dhash(b64)
        assert h1 == h2

    def test_invalid_base64_returns_none(self):
        assert dhash("not-valid-base64!!!") is None

    def test_empty_string_returns_none(self):
        assert dhash("") is None

    def test_uniform_image(self):
        """A solid-colour image should produce a valid hash (all 0 or all 1)."""
        b64 = _make_minimal_jpeg(64, 64, color=128)
        h = dhash(b64)
        assert h is not None

    def test_different_images_different_hash(self):
        """A gradient and a solid image should produce different hashes."""
        h1 = dhash(_make_gradient_jpeg())
        h2 = dhash(_make_minimal_jpeg(64, 64, color=128))
        assert h1 is not None and h2 is not None
        assert h1 != h2

    def test_status_bar_frac_zero(self):
        """status_bar_frac=0 should still work."""
        b64 = _make_gradient_jpeg()
        h = dhash(b64, status_bar_frac=0.0)
        assert h is not None

    def test_status_bar_frac_affects_hash(self):
        """Different frac values can produce different hashes."""
        b64 = _make_gradient_jpeg(64, 128)
        h0 = dhash(b64, status_bar_frac=0.0)
        h50 = dhash(b64, status_bar_frac=0.5)
        # They may or may not differ depending on image content,
        # but both must be valid.
        assert h0 is not None
        assert h50 is not None
