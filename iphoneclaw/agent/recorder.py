from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import asdict
from typing import Any, Dict, Optional

from iphoneclaw.config import Config
from iphoneclaw.types import ScreenshotOutput


def _redact_config(cfg: Config) -> Dict[str, Any]:
    d = asdict(cfg)
    # Never write secrets to disk.
    if d.get("model_api_key"):
        d["model_api_key"] = "***REDACTED***"
    if d.get("supervisor_token"):
        d["supervisor_token"] = "***REDACTED***"
    return d


def _json_dump(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _jsonl_append(path: str, obj: Any) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


class RunRecorder:
    def __init__(self, cfg: Config, run_id: Optional[str] = None) -> None:
        ts = time.strftime("%Y%m%d_%H%M%S")
        self.run_id = run_id or ts
        self.root = os.path.abspath(os.path.join(cfg.record_dir, self.run_id))
        self.steps_dir = os.path.join(self.root, "steps")

        os.makedirs(self.steps_dir, exist_ok=True)
        _json_dump(
            os.path.join(self.root, "meta.json"),
            {
                "run_id": self.run_id,
                "ts": ts,
                "config": _redact_config(cfg),
            },
        )

        self.conversation_path = os.path.join(self.root, "conversation.jsonl")
        self.events_path = os.path.join(self.root, "events.jsonl")

    def log_conversation(self, role: str, text: str, **meta: Any) -> None:
        _jsonl_append(
            self.conversation_path,
            {"role": role, "text": text, "ts": time.time(), "meta": meta},
        )

    def log_event(self, type_: str, data: Dict[str, Any]) -> None:
        _jsonl_append(
            self.events_path, {"type": type_, "data": data, "ts": time.time()}
        )

    def write_step(
        self,
        step: int,
        *,
        screenshot: Optional[ScreenshotOutput] = None,
        raw_model_text: Optional[str] = None,
        action: Optional[Dict[str, Any]] = None,
        exec_result: Optional[Dict[str, Any]] = None,
    ) -> str:
        d = os.path.join(self.steps_dir, "%04d" % step)
        os.makedirs(d, exist_ok=True)

        if screenshot is not None:
            jpg = base64.b64decode(screenshot.base64)
            with open(os.path.join(d, "screenshot.jpg"), "wb") as f:
                f.write(jpg)
            _json_dump(
                os.path.join(d, "screenshot.json"),
                {
                    "scale_factor": screenshot.scale_factor,
                    "window_bounds": asdict(screenshot.window_bounds),
                    "image_width": screenshot.image_width,
                    "image_height": screenshot.image_height,
                    "raw_image_width": screenshot.raw_image_width,
                    "raw_image_height": screenshot.raw_image_height,
                    "crop_rect_px": screenshot.crop_rect_px,
                },
            )

        if raw_model_text is not None:
            with open(os.path.join(d, "model.txt"), "w", encoding="utf-8") as f:
                f.write(raw_model_text)

        if action is not None:
            _json_dump(os.path.join(d, "action.json"), action)

        if exec_result is not None:
            _json_dump(os.path.join(d, "exec.json"), exec_result)

        return d
