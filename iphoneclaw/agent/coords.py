from __future__ import annotations

from typing import Optional, Tuple

from iphoneclaw.types import Rect, ScreenshotOutput


def model_point_to_screen(
    x: int,
    y: int,
    *,
    bounds: Rect,
    coord_factor: int = 1000,
) -> Tuple[float, float]:
    """
    Map model coordinates in [0..coord_factor] into global screen coordinates.
    We use window bounds (in Quartz global coordinates).
    """
    fx = float(x) / float(coord_factor) if coord_factor else 0.0
    fy = float(y) / float(coord_factor) if coord_factor else 0.0
    sx = bounds.x + fx * bounds.width
    sy = bounds.y + fy * bounds.height
    return sx, sy


def point_from_boxes(
    start_box: Optional[str],
    *,
    bounds: Rect,
    coord_factor: int = 1000,
) -> Optional[Tuple[float, float]]:
    from iphoneclaw.parse.action_parser import parse_box_point

    pt = parse_box_point(start_box)
    if not pt:
        return None
    return model_point_to_screen(pt[0], pt[1], bounds=bounds, coord_factor=coord_factor)

