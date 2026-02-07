"""Screenshot capture using CGWindowListCreateImage."""

from __future__ import annotations

import base64
import logging
from dataclasses import asdict
from typing import Optional, Tuple

import Quartz
from AppKit import NSBitmapImageRep, NSJPEGFileType

from iphoneclaw.macos.window import WindowFinder
from iphoneclaw.types import Rect, ScreenshotOutput

logger = logging.getLogger(__name__)

# NSBitmapImageRep property key
NSImageCompressionFactor = "NSImageCompressionFactor"

def _is_near_white(r: int, g: int, b: int, *, thr: int) -> bool:
    return r >= thr and g >= thr and b >= thr


def _auto_crop_white_border_px_cv2(
    bgr_img,
    *,
    edge_white_frac_threshold: float = 0.995,
    white_min: int = 242,
    white_max_delta: int = 20,
    margin_px: int = 6,
) -> Optional[Tuple[int, int, int, int]]:
    """
    Use OpenCV/numpy to trim pure/near-white borders by scanning from each edge until
    we hit non-white content.

    This is more robust than "largest non-white contour" because the phone UI itself
    may contain large white regions.
    """
    try:
        import numpy as np
    except Exception:
        return None

    img = bgr_img
    if img is None:
        return None
    if not hasattr(img, "shape"):
        return None
    h, w = int(img.shape[0]), int(img.shape[1])
    if h <= 0 or w <= 0:
        return None

    mx = img.max(axis=2)
    mn = img.min(axis=2)
    # "Near-white" means all channels are very bright and close to each other.
    white = (mx >= white_min) & (mn >= white_min) & ((mx - mn) <= white_max_delta)

    row_white = white.mean(axis=1)
    col_white = white.mean(axis=0)

    thr = float(edge_white_frac_threshold)

    y0 = 0
    while y0 < h and float(row_white[y0]) >= thr:
        y0 += 1
    y1 = h - 1
    while y1 > y0 and float(row_white[y1]) >= thr:
        y1 -= 1
    x0 = 0
    while x0 < w and float(col_white[x0]) >= thr:
        x0 += 1
    x1 = w - 1
    while x1 > x0 and float(col_white[x1]) >= thr:
        x1 -= 1

    if x1 <= x0 or y1 <= y0:
        return None

    x0 = max(0, int(x0) - margin_px)
    y0 = max(0, int(y0) - margin_px)
    x1 = min(w - 1, int(x1) + margin_px)
    y1 = min(h - 1, int(y1) + margin_px)

    cw = max(1, (x1 - x0) + 1)
    ch = max(1, (y1 - y0) + 1)

    # Reliability guard: avoid absurdly tiny crops.
    if cw < int(w * 0.35) or ch < int(h * 0.35):
        return None

    return (int(x0), int(y0), int(cw), int(ch))


def _auto_crop_white_border_px(
    image: "Quartz.CGImageRef",
    *,
    white_threshold: int = 250,
    margin_px: int = 6,
) -> Optional[Tuple[int, int, int, int]]:
    """
    Best-effort crop: find bounding box of pixels that are not near-white.

    This is tuned for iPhone Mirroring where the phone content sits on a plain white
    background (large white top border etc). We sample pixels for speed.
    Returns (x, y, w, h) in pixel coordinates relative to the CGImage, or None if
    detection is unreliable.
    """
    try:
        bitmap = NSBitmapImageRep.alloc().initWithCGImage_(image)
        if bitmap is None:
            return None

        w = int(bitmap.pixelsWide())
        h = int(bitmap.pixelsHigh())
        if w <= 0 or h <= 0:
            return None

        bpp = int(bitmap.bitsPerPixel())
        if bpp < 24:
            return None
        bytes_per_pixel = bpp // 8
        bpr = int(bitmap.bytesPerRow())
        data_obj = bitmap.bitmapData()
        if data_obj is None:
            return None

        # PyObjC usually exposes this as a writable buffer.
        data = memoryview(data_obj)

        # Determine channel offsets. Default: RGBA; alpha-first => ARGB.
        try:
            from AppKit import NSBitmapFormatAlphaFirst  # type: ignore

            alpha_first = bool(int(bitmap.bitmapFormat()) & int(NSBitmapFormatAlphaFirst))
        except Exception:
            alpha_first = False

        if bytes_per_pixel >= 4:
            if alpha_first:
                ro, go, bo = 1, 2, 3
            else:
                ro, go, bo = 0, 1, 2
        else:
            ro, go, bo = 0, 1, 2

        # Prefer cv2/numpy edge-scan crop when available.
        try:
            import numpy as np  # type: ignore

            # Create a (h, w, c) view for pixel payload (ignore padding at row end).
            raw = np.frombuffer(data, dtype=np.uint8, count=h * bpr).reshape((h, bpr))
            pix = raw[:, : w * bytes_per_pixel].reshape((h, w, bytes_per_pixel))
            if bytes_per_pixel >= 4:
                if alpha_first:
                    bgr = pix[:, :, (3, 2, 1)]
                else:
                    bgr = pix[:, :, (2, 1, 0)]
            else:
                bgr = pix[:, :, (2, 1, 0)]
            rect = _auto_crop_white_border_px_cv2(bgr, margin_px=margin_px)
            if rect is not None:
                return rect
        except Exception:
            pass

        # Fallback: sampled scan (less robust with mostly-white UIs).
        step = max(1, min(w, h) // 800)  # ~<= 800 samples per axis
        minx, miny = w, h
        maxx, maxy = -1, -1

        for y in range(0, h, step):
            row0 = y * bpr
            row = data[row0 : row0 + w * bytes_per_pixel]
            for x in range(0, w, step):
                i = x * bytes_per_pixel
                try:
                    r = int(row[i + ro])
                    g = int(row[i + go])
                    b = int(row[i + bo])
                except Exception:
                    continue
                if not _is_near_white(r, g, b, thr=white_threshold):
                    if x < minx:
                        minx = x
                    if y < miny:
                        miny = y
                    if x > maxx:
                        maxx = x
                    if y > maxy:
                        maxy = y

        if maxx < 0 or maxy < 0:
            return None

        mx = max(0, minx - margin_px)
        my = max(0, miny - margin_px)
        Mx = min(w - 1, maxx + margin_px)
        My = min(h - 1, maxy + margin_px)
        cw = max(1, (Mx - mx) + 1)
        ch = max(1, (My - my) + 1)

        if cw < int(w * 0.35) or ch < int(h * 0.35):
            return None

        return (int(mx), int(my), int(cw), int(ch))
    except Exception:
        return None


def _bounds_for_crop(bounds: Rect, *, crop_rect_px: Tuple[int, int, int, int], scale_factor: float) -> Rect:
    cx, cy, cw, ch = crop_rect_px
    sf = scale_factor if scale_factor > 0 else 1.0
    return Rect(
        x=float(bounds.x + (cx / sf)),
        y=float(bounds.y + (cy / sf)),
        width=float(cw / sf),
        height=float(ch / sf),
    )


class ScreenCapture:
    """Captures the target window as JPEG base64."""

    def __init__(self, window_finder: WindowFinder):
        self.wf = window_finder
        self._crop_rect_px: Optional[Tuple[int, int, int, int]] = None
        self._last_raw_size: Optional[Tuple[int, int]] = None

    def capture(self) -> ScreenshotOutput:
        """Capture the target window. Returns JPEG base64 + metadata."""
        wid = self.wf.window_id
        bounds = self.wf.refresh()

        # Capture just this window, excluding frame/shadow
        image = Quartz.CGWindowListCreateImage(
            Quartz.CGRectNull,
            Quartz.kCGWindowListOptionIncludingWindow,
            wid,
            Quartz.kCGWindowImageBoundsIgnoreFraming,
        )

        if image is None:
            # Window may have closed/reopened — retry
            logger.warning("Capture returned None, re-finding window...")
            self.wf.find_window()
            wid = self.wf.window_id
            bounds = self.wf.bounds
            image = Quartz.CGWindowListCreateImage(
                Quartz.CGRectNull,
                Quartz.kCGWindowListOptionIncludingWindow,
                wid,
                Quartz.kCGWindowImageBoundsIgnoreFraming,
            )
            if image is None:
                raise RuntimeError("Failed to capture window image")

        # Get pixel dimensions (may differ from bounds on Retina)
        raw_w = int(Quartz.CGImageGetWidth(image))
        raw_h = int(Quartz.CGImageGetHeight(image))

        # Compute scale factor (Retina displays: image pixels > logical bounds)
        scale_factor = raw_w / bounds.width if bounds.width > 0 else 1.0

        crop_rect_px = None
        # Auto-crop white border to the smallest reliable bounding box.
        # We only recompute when the raw capture size changes.
        if self._last_raw_size != (raw_w, raw_h):
            self._crop_rect_px = None
            self._last_raw_size = (raw_w, raw_h)
        if self._crop_rect_px is None:
            self._crop_rect_px = _auto_crop_white_border_px(image)
        if self._crop_rect_px is not None:
            crop_rect_px = self._crop_rect_px
            cx, cy, cw, ch = crop_rect_px
            try:
                image = Quartz.CGImageCreateWithImageInRect(image, ((cx, cy), (cw, ch)))
                bounds = _bounds_for_crop(bounds, crop_rect_px=crop_rect_px, scale_factor=scale_factor)
            except Exception:
                crop_rect_px = None

        img_w = int(Quartz.CGImageGetWidth(image))
        img_h = int(Quartz.CGImageGetHeight(image))

        # Convert CGImage -> JPEG base64 (cropped if crop_rect_px set).
        bitmap = NSBitmapImageRep.alloc().initWithCGImage_(image)
        jpeg_data = bitmap.representationUsingType_properties_(
            NSJPEGFileType,
            {NSImageCompressionFactor: 0.75},
        )

        if jpeg_data is None:
            raise RuntimeError("Failed to encode screenshot as JPEG")

        b64 = base64.b64encode(bytes(jpeg_data)).decode("ascii")

        logger.debug(
            "Captured: %dx%d px (raw %dx%d), bounds=%s, crop=%s, scale=%.2f",
            img_w,
            img_h,
            raw_w,
            raw_h,
            asdict(bounds),
            crop_rect_px,
            scale_factor,
        )

        return ScreenshotOutput(
            base64=b64,
            scale_factor=scale_factor,
            window_bounds=bounds,
            image_width=int(img_w),
            image_height=int(img_h),
            crop_rect_px=crop_rect_px,
            raw_image_width=int(raw_w),
            raw_image_height=int(raw_h),
        )
