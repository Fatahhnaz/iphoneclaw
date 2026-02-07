from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from iphoneclaw.agent.conversation import ConversationStore
from iphoneclaw.agent.executor import execute_action
from iphoneclaw.agent.recorder import RunRecorder
from iphoneclaw.config import Config
from iphoneclaw.macos.capture import ScreenCapture
from iphoneclaw.macos.user_input_monitor import UserInputMonitor
from iphoneclaw.macos.window import WindowFinder
from iphoneclaw.model.client import OpenAICompatClient, invoke_model
from iphoneclaw.model.image import data_url_from_jpeg_base64, resize_jpeg_base64, smart_resize
from iphoneclaw.model.prompt_v15 import system_prompt_v15
from iphoneclaw.parse.action_parser import parse_predictions
from iphoneclaw.supervisor.hub import SupervisorHub
from iphoneclaw.supervisor.state import WorkerControl
from iphoneclaw.types import StatusEnum


class Worker:
    def __init__(
        self,
        cfg: Config,
        *,
        hub: Optional[SupervisorHub] = None,
        control: Optional[WorkerControl] = None,
        recorder: Optional[RunRecorder] = None,
        conversation: Optional[ConversationStore] = None,
    ) -> None:
        self.cfg = cfg
        self.hub = hub or SupervisorHub()
        self.control = control or WorkerControl()
        self.recorder = recorder or RunRecorder(cfg)
        self.conversation = conversation or ConversationStore()

        self.wf = WindowFinder(app_name=cfg.target_app, window_contains=cfg.window_contains)
        self.cap = ScreenCapture(self.wf)
        self._monitor: Optional[UserInputMonitor] = None

        self.client = OpenAICompatClient(cfg.model_base_url, cfg.model_api_key, cfg.model_name)
        self.system = system_prompt_v15(cfg.language)
        self._vision_image_url_as_string = ("volces.com" in cfg.model_base_url.lower()) or (
            "doubao" in cfg.model_name.lower()
        )

    def _publish_conv(self, role: str, text: str) -> None:
        self.hub.publish("conversation", {"role": role, "text": text})

    def _vision_msg(self, instruction: str, image_b64: str) -> Dict[str, Any]:
        img_url = data_url_from_jpeg_base64(image_b64)
        if self._vision_image_url_as_string:
            return {
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {"type": "image_url", "image_url": img_url},
                ],
            }
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": instruction},
                {"type": "image_url", "image_url": {"url": img_url}},
            ],
        }

    def run(self, instruction: str) -> None:
        self.control.set_status(StatusEnum.RUNNING)
        self.hub.set_status(self.control.snapshot()["status"])

        if getattr(self.cfg, "auto_pause_on_user_input", True):
            def _on_act(a) -> None:
                snap = self.control.snapshot()
                if snap.get("paused") or snap.get("stopped"):
                    return
                if snap.get("status") != StatusEnum.RUNNING.value:
                    return
                self.control.pause()
                self.hub.set_status(self.control.snapshot()["status"])
                self.hub.publish(
                    "auto_pause",
                    {"reason": "user_input", "kind": getattr(a, "kind", ""), "pos": getattr(a, "pos", None)},
                )

            self._monitor = UserInputMonitor(on_activity=_on_act)
            self._monitor.start()

        # Top-level guard: never crash silently.
        try:
            self.wf.launch_app()
        except Exception as e:
            self.control.set_status(StatusEnum.ERROR)
            self.hub.set_status(self.control.snapshot()["status"], error=str(e))
            self.hub.publish("error", {"where": "launch_app", "error": str(e)})
            if self._monitor:
                self._monitor.stop()
            return

        self.conversation.add("system", self.system)
        self.recorder.log_conversation("system", self.system)

        self.conversation.add("user", instruction)
        self.recorder.log_conversation("user", instruction)
        self._publish_conv("user", instruction)

        step = 0
        parse_err_streak = 0
        while True:
            try:
                if self.control.snapshot()["stopped"]:
                    self.control.set_status(StatusEnum.USER_STOPPED)
                    self.hub.set_status(self.control.snapshot()["status"])
                    if self._monitor:
                        self._monitor.stop()
                    return

                # Pause / Hang gate at step boundaries
                while self.control.snapshot()["paused"]:
                    time.sleep(0.2)
                    if self.control.snapshot()["stopped"]:
                        self.control.set_status(StatusEnum.USER_STOPPED)
                        self.hub.set_status(self.control.snapshot()["status"])
                        if self._monitor:
                            self._monitor.stop()
                        return

                injected = self.control.pop_injected()
                if injected:
                    txt = "[Supervisor Guidance]\n" + injected
                    self.conversation.add("user", txt, injected=True)
                    self.recorder.log_conversation("user", txt, injected=True)
                    self._publish_conv("user", txt)

                step += 1
                if step > int(self.cfg.max_loop_count):
                    self.control.set_status(StatusEnum.ERROR)
                    self.hub.set_status(self.control.snapshot()["status"], error="max_loop_count")
                    if self._monitor:
                        self._monitor.stop()
                    return

                shot = self.cap.capture()
                self.recorder.write_step(step, screenshot=shot)

                # Resize image to match pixel budget before sending to model.
                send_b64 = shot.base64
                tw, th = smart_resize(int(shot.image_width), int(shot.image_height))
                if tw and th and (tw != shot.image_width or th != shot.image_height):
                    send_b64 = resize_jpeg_base64(shot.base64, tw, th)

                # Build messages
                messages: List[Dict[str, Any]] = [{"role": "system", "content": self.system}]
                tail = self.conversation.to_openai_messages(include_system=False, tail_rounds=8)
                messages.extend(tail)
                messages.append(self._vision_msg("Current screen. Decide next action.", send_b64))

                extra_body = None
                if "volces.com" in self.cfg.model_base_url.lower():
                    extra_body = {"thinking": {"type": self.cfg.volc_thinking_type}}

                inv = invoke_model(
                    self.client,
                    messages,
                    max_tokens=self.cfg.max_tokens,
                    temperature=self.cfg.temperature,
                    top_p=self.cfg.top_p,
                    parse_fn=parse_predictions,
                    extra_body=extra_body,
                )

                self.recorder.write_step(step, raw_model_text=inv.prediction)
                self.recorder.log_event(
                    "model",
                    {"tokens": inv.cost_tokens, "dt": inv.cost_time},
                )

                # Log assistant text
                self.conversation.add("assistant", inv.prediction)
                self.recorder.log_conversation("assistant", inv.prediction)
                self._publish_conv("assistant", inv.prediction)

                pred = inv.parsed_predictions[0]
                act = {
                    "action_type": pred.action_type,
                    "raw_action": pred.raw_action,
                    "thought": pred.thought,
                    "inputs": pred.action_inputs.__dict__,
                }
                self.recorder.write_step(step, action=act)

                if pred.action_type == "error_env":
                    parse_err_streak += 1
                    self.hub.publish("error", {"where": "parse", "streak": parse_err_streak, "raw": pred.raw_action})
                    if parse_err_streak >= 3:
                        # Hang for supervision instead of burning tokens.
                        self.control.set_status(StatusEnum.HANG)
                        self.control.pause()
                        self.hub.set_status(self.control.snapshot()["status"], reason="parse_error_streak")
                        self.hub.publish("hang", {"reason": "parse_error_streak"})
                        continue
                else:
                    parse_err_streak = 0

                # Terminal actions with hang semantics
                if pred.action_type == "finished":
                    if self.cfg.hang_on_finished:
                        self.control.set_status(StatusEnum.HANG)
                        self.control.pause()
                        self.hub.set_status(self.control.snapshot()["status"])
                        self.hub.publish("hang", {"reason": "finished"})
                        continue
                    self.control.set_status(StatusEnum.END)
                    self.hub.set_status(self.control.snapshot()["status"])
                    if self._monitor:
                        self._monitor.stop()
                    return

                if pred.action_type == "call_user":
                    if self.cfg.hang_on_call_user:
                        self.control.set_status(StatusEnum.HANG)
                        self.control.pause()
                        self.hub.set_status(self.control.snapshot()["status"])
                        self.hub.publish("hang", {"reason": "call_user"})
                        continue
                    self.control.set_status(StatusEnum.CALL_USER)
                    self.hub.set_status(self.control.snapshot()["status"])
                    if self._monitor:
                        self._monitor.stop()
                    return

                self.wf.activate_app()
                res = execute_action(self.cfg, pred, shot)
                self.recorder.write_step(step, exec_result=res)
                self.recorder.log_event("exec", res)

                # Update status each loop
                self.control.set_status(StatusEnum.RUNNING)
                self.hub.set_status(self.control.snapshot()["status"], step=step)

                time.sleep(float(self.cfg.loop_interval_ms) / 1000.0)
            except Exception as e:
                self.control.set_status(StatusEnum.ERROR)
                self.hub.set_status(self.control.snapshot()["status"], error=str(e), step=step)
                self.hub.publish("error", {"where": "loop", "error": str(e), "step": step})
                self.recorder.log_event("error", {"error": str(e), "step": step})
                if self._monitor:
                    self._monitor.stop()
                return
