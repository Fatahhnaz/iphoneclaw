"""Screen fingerprint via dHash (difference hash).

Produces a 64-bit perceptual hash from a screenshot. Uses only PyObjC/Quartz
(no Pillow, no OpenCV, no numpy).
"""
from __future__ import annotations

import base64
from typing import Optional

import Quartz  # type: ignore
from Foundation import NSData  # type: ignore


def _cgimage_from_jpeg_b64(b64: str) -> Optional["Quartz.CGImageRef"]:
    """Decode JPEG base64 to CGImageRef."""
    try:
        raw = base64.b64decode(b64)
        data = NSData.dataWithBytes_length_(raw, len(raw))
        src = Quartz.CGImageSourceCreateWithData(data, None)
        if src is None:
            return None
        img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
        return img
    except Exception:
        return None


def _crop_top(image: "Quartz.CGImageRef", frac: float) -> "Quartz.CGImageRef":
    """Crop away the top *frac* fraction of the image (status bar masking).

    CoreGraphics origin is bottom-left, so "top" of the visual image is the
    high-y region.  We keep the rectangle from y=0 up to y = h*(1-frac).
    """
    w = Quartz.CGImageGetWidth(image)
    h = Quartz.CGImageGetHeight(image)
    skip = int(h * frac)
    if skip <= 0 or skip >= h:
        return image
    # Keep bottom (h - skip) rows: rect from (0, 0) with height (h - skip).
    cropped = Quartz.CGImageCreateWithImageInRect(
        image, Quartz.CGRectMake(0, 0, w, h - skip)
    )
    return cropped if cropped is not None else image


def dhash(b64: str, *, status_bar_frac: float = 0.08) -> Optional[int]:
    """Compute 64-bit dHash from JPEG base64 string.

    Returns None if decoding fails.  *status_bar_frac* controls how much of
    the top of the image to mask out (default 8 % for iPhone status bar).
    """
    image = _cgimage_from_jpeg_b64(b64)
    if image is None:
        return None

    if status_bar_frac > 0:
        image = _crop_top(image, status_bar_frac)

    # Draw into 9x8 grayscale bitmap.
    gray_cs = Quartz.CGColorSpaceCreateDeviceGray()
    ctx = Quartz.CGBitmapContextCreate(None, 9, 8, 8, 9, gray_cs, 0)
    if ctx is None:
        return None
    Quartz.CGContextSetInterpolationQuality(ctx, Quartz.kCGInterpolationHigh)
    Quartz.CGContextDrawImage(ctx, Quartz.CGRectMake(0, 0, 9, 8), image)

    data = Quartz.CGBitmapContextGetData(ctx)
    if data is None:
        return None

    # Read 9*8 = 72 grayscale bytes.
    buf = data.as_buffer(72)
    pixels = bytes(buf)
    if len(pixels) < 72:
        return None

    # dHash: for each row compare adjacent pixels -> 8 rows * 8 cols = 64 bits.
    hash_val = 0
    bit = 0
    for row in range(8):
        for col in range(8):
            idx = row * 9 + col
            if pixels[idx] < pixels[idx + 1]:
                hash_val |= 1 << bit
            bit += 1

    return hash_val


def hamming_distance(a: int, b: int) -> int:
    """Count differing bits between two 64-bit hashes."""
    return bin(a ^ b).count("1")
