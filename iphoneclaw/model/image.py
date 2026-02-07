from __future__ import annotations

import base64
from typing import Tuple

from iphoneclaw.constants import IMAGE_FACTOR, MAX_PIXELS_V1_5, MIN_PIXELS


def smart_resize(width: int, height: int) -> Tuple[int, int]:
    """Match UI-TARS style resizing constraints (multiple of IMAGE_FACTOR)."""
    if width <= 0 or height <= 0:
        return width, height

    pixels = width * height
    if pixels < MIN_PIXELS:
        scale = (MIN_PIXELS / pixels) ** 0.5
        width = int(width * scale)
        height = int(height * scale)
    elif pixels > MAX_PIXELS_V1_5:
        scale = (MAX_PIXELS_V1_5 / pixels) ** 0.5
        width = int(width * scale)
        height = int(height * scale)

    # Round to IMAGE_FACTOR
    width = max(IMAGE_FACTOR, (width // IMAGE_FACTOR) * IMAGE_FACTOR)
    height = max(IMAGE_FACTOR, (height // IMAGE_FACTOR) * IMAGE_FACTOR)
    return width, height


def data_url_from_jpeg_base64(b64: str) -> str:
    # Model servers typically accept data URLs; keep it simple.
    # Input is base64-encoded JPEG bytes already.
    return "data:image/jpeg;base64," + b64


def resize_jpeg_base64(b64: str, out_w: int, out_h: int, *, quality: float = 0.8) -> str:
    """
    Resize JPEG(base64) to (out_w,out_h) using AppKit.
    Returns base64 JPEG bytes.
    """
    if out_w <= 0 or out_h <= 0:
        return b64
    try:
        from AppKit import NSBitmapImageRep, NSDeviceRGBColorSpace, NSImage, NSJPEGFileType  # type: ignore
        from Foundation import NSData  # type: ignore
    except Exception:
        # If AppKit isn't available, do not resize.
        return b64

    try:
        raw = base64.b64decode(b64)
        data = NSData.dataWithBytes_length_(raw, len(raw))
        img = NSImage.alloc().initWithData_(data)
        if img is None:
            return b64

        # Draw into a new bitmap at target size.
        rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
            None,
            int(out_w),
            int(out_h),
            8,
            4,
            True,
            False,
            NSDeviceRGBColorSpace,
            0,
            0,
        )
        if rep is None:
            return b64

        from AppKit import NSGraphicsContext  # type: ignore

        ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.setCurrentContext_(ctx)
        try:
            img.drawInRect_fromRect_operation_fraction_(((0, 0), (out_w, out_h)), ((0, 0), img.size()), 2, 1.0)
        finally:
            NSGraphicsContext.restoreGraphicsState()

        jpeg = rep.representationUsingType_properties_(NSJPEGFileType, {"NSImageCompressionFactor": float(quality)})
        if jpeg is None:
            return b64
        return base64.b64encode(bytes(jpeg)).decode("ascii")
    except Exception:
        return b64
