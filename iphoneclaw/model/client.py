from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from iphoneclaw.types import InvokeResult, PredictionParsed


class OpenAICompatClient:
    """Tiny OpenAI-compatible chat.completions client (no external deps)."""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def chat_completions(
        self,
        messages: List[Dict[str, Any]],
        *,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        top_p: float = 0.7,
        retries: int = 3,
        retry_backoff_s: float = 0.8,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, int]:
        url = self.base_url + "/chat/completions"
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        if extra_body:
            body.update(extra_body)
        data = json.dumps(body).encode("utf-8")
        last_err = None
        last_http_body = None
        last_http_code = None
        for attempt in range(max(1, int(retries))):
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            if self.api_key:
                req.add_header("Authorization", f"Bearer {self.api_key}")
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    payload = json.loads(raw)
                last_err = None
                break
            except urllib.error.HTTPError as e:
                last_err = e
                last_http_code = getattr(e, "code", None)
                try:
                    last_http_body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    last_http_body = None
                # Do not retry on 4xx except 408/429.
                if last_http_code and 400 <= int(last_http_code) < 500 and int(last_http_code) not in (408, 429):
                    break
                if attempt >= retries - 1:
                    break
                time.sleep(retry_backoff_s * (2 ** attempt))
            except Exception as e:
                last_err = e
                # Retry on transient-ish failures (network / 5xx / timeouts).
                if attempt >= retries - 1:
                    break
                time.sleep(retry_backoff_s * (2 ** attempt))
        if last_err is not None:
            if last_http_code is not None:
                raise RuntimeError(
                    "Model HTTP error %s: %s"
                    % (last_http_code, (last_http_body or str(last_err))[:2000])
                )
            raise last_err

        text = payload["choices"][0]["message"]["content"]
        usage = payload.get("usage") or {}
        total_tokens = int(usage.get("total_tokens") or 0)
        return text, total_tokens


def invoke_model(
    client: OpenAICompatClient,
    messages: List[Dict[str, Any]],
    *,
    max_tokens: int,
    temperature: float,
    top_p: float,
    parse_fn,
    extra_body: Optional[Dict[str, Any]] = None,
) -> InvokeResult:
    start = time.time()
    pred, tokens = client.chat_completions(
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        extra_body=extra_body,
    )
    parsed: List[PredictionParsed] = parse_fn(pred)
    end = time.time()
    return InvokeResult(
        prediction=pred,
        parsed_predictions=parsed,
        cost_tokens=tokens,
        cost_time=float(end - start),
    )
