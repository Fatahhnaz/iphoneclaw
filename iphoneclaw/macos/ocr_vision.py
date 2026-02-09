from __future__ import annotations

import base64
from dataclasses import asdict
from typing import Any, Dict, List, Optional

import Quartz

from iphoneclaw.types import Rect, ScreenshotOutput


def _clamp01(v: float) -> float:
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _decode_screenshot_to_cgimage(image_b64: str):
    try:
        raw = base64.b64decode(image_b64)
    except Exception as e:
        raise RuntimeError("invalid screenshot base64: %s" % str(e)) from e

    cf_data = Quartz.CFDataCreate(None, raw, len(raw))
    if cf_data is None:
        raise RuntimeError("failed to create CFData from screenshot bytes")

    src = Quartz.CGImageSourceCreateWithData(cf_data, None)
    if src is None:
        raise RuntimeError("failed to decode screenshot bytes as image")

    cg = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    if cg is None:
        raise RuntimeError("failed to build CGImage from screenshot data")
    return cg


def _rect_from_vision_bbox_top_left(
    bbox_bottom_left: Any,
    *,
    image_width: int,
    image_height: int,
    window_bounds: Rect,
    coord_factor: int,
) -> Dict[str, Any]:
    # Vision bbox is normalized [0,1], origin at bottom-left.
    vx = float(bbox_bottom_left.origin.x)
    vy = float(bbox_bottom_left.origin.y)
    vw = float(bbox_bottom_left.size.width)
    vh = float(bbox_bottom_left.size.height)

    nx = _clamp01(vx)
    ny = _clamp01(1.0 - (vy + vh))
    nw = _clamp01(vw)
    nh = _clamp01(vh)

    px = int(round(nx * float(image_width)))
    py = int(round(ny * float(image_height)))
    pw = int(round(nw * float(image_width)))
    ph = int(round(nh * float(image_height)))

    sx = float(window_bounds.x + nx * window_bounds.width)
    sy = float(window_bounds.y + ny * window_bounds.height)
    sw = float(nw * window_bounds.width)
    sh = float(nh * window_bounds.height)

    mx = int(round(nx * float(coord_factor)))
    my = int(round(ny * float(coord_factor)))
    mw = int(round(nw * float(coord_factor)))
    mh = int(round(nh * float(coord_factor)))

    return {
        "normalized_box": {
            "x": round(nx, 6),
            "y": round(ny, 6),
            "width": round(nw, 6),
            "height": round(nh, 6),
        },
        "pixel_box": {
            "x": px,
            "y": py,
            "width": pw,
            "height": ph,
        },
        "screen_box": {
            "x": round(sx, 3),
            "y": round(sy, 3),
            "width": round(sw, 3),
            "height": round(sh, 3),
        },
        "model_box": {
            "x": mx,
            "y": my,
            "width": mw,
            "height": mh,
        },
    }


def recognize_screenshot_text(
    shot: ScreenshotOutput,
    *,
    coord_factor: int = 1000,
    min_confidence: float = 0.0,
    max_items: Optional[int] = None,
) -> Dict[str, Any]:
    try:
        import Vision  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Apple Vision framework is unavailable. Install pyobjc-framework-Vision on macOS."
        ) from e

    cg = _decode_screenshot_to_cgimage(shot.base64)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    # Accurate mode gives better OCR quality on UI text.
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(False)

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, None)
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        raise RuntimeError("Vision OCR request failed: %s" % (str(err) if err is not None else "unknown error"))

    obs = req.results() or []
    items: List[Dict[str, Any]] = []
    for o in obs:
        cands = o.topCandidates_(1) or []
        if not cands:
            continue
        best = cands[0]
        text = str(best.string() or "").strip()
        if not text:
            continue
        conf = float(best.confidence())
        if conf < float(min_confidence):
            continue

        rects = _rect_from_vision_bbox_top_left(
            o.boundingBox(),
            image_width=int(shot.image_width),
            image_height=int(shot.image_height),
            window_bounds=shot.window_bounds,
            coord_factor=int(coord_factor),
        )
        items.append(
            {
                "text": text,
                "confidence": round(conf, 4),
                **rects,
            }
        )

    # Reading order: top-to-bottom, then left-to-right.
    items.sort(key=lambda x: (float(x["normalized_box"]["y"]), float(x["normalized_box"]["x"])))
    if max_items is not None and int(max_items) > 0:
        items = items[: int(max_items)]

    return {
        "engine": "apple-vision",
        "coord_factor": int(coord_factor),
        "count": len(items),
        "items": items,
        "screenshot": {
            "scale_factor": float(shot.scale_factor),
            "window_bounds": asdict(shot.window_bounds),
            "image_width": int(shot.image_width),
            "image_height": int(shot.image_height),
            "crop_rect_px": list(shot.crop_rect_px) if shot.crop_rect_px else None,
            "raw_image_width": int(shot.raw_image_width),
            "raw_image_height": int(shot.raw_image_height),
        },
    }
