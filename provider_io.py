"""Observe assembled provider requests without replacing kerness retry policy."""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

import kerness
import kerness.provider

from progress import emit

RETRIES = 2
RETRY_INTERVAL_SECONDS = 3
# Classification is best effort; never parse or echo an unbounded error page.
MAX_ERROR_CHARS = 16_384
_PANEL = ContextVar("provider_panel", default=None)
_REQUEST = ContextVar("provider_request", default=None)
_TRANSPORT_LOCK = threading.RLock()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _prompt_size(payload: dict) -> str:
    messages = payload.get("messages", [])
    tools = payload.get("tools", [])
    message_json = _json(messages)
    tool_json = _json(tools) if tools else ""
    chars = len(message_json) + len(tool_json)
    roles = {role: 0 for role in ("system", "user", "assistant", "tool", "other")}
    for message in messages:
        role = message.get("role")
        roles[role if role in roles else "other"] += len(_json(message).encode("utf-8"))
    breakdown = ", ".join(f"{role}={size}" for role, size in roles.items() if size)
    return (
        f"{len(messages)} messages; {chars} prompt JSON chars "
        f"(~{chars // 4} tokens, chars/4 estimate); "
        f"messages JSON={len(message_json.encode('utf-8'))} B; "
        f"{len(tools)} tool schemas JSON={len(tool_json.encode('utf-8'))} B; "
        f"payload JSON={len(_json(payload).encode('utf-8'))} B; role JSON B: {breakdown}"
    )


def _rejection_hint(error: kerness.ProviderHTTPError) -> str:
    """Translate recognized refusals to fixed text without exposing their body."""
    if error.status_code not in (400, 413, 422):
        return ""
    unknown = (
        "unrecognized provider rejection; check the gateway's request/error logs for the exact reason. "
        "Increasing timeout limits does not resolve a rejected request"
    )
    if len(error.body) > MAX_ERROR_CHARS:
        return unknown
    if error.is_context_overflow:
        return (
            "provider reports a context/input limit; reduce review input or use a model "
            "with a larger context window"
        )
    body = error.body.lower()
    invalid = any(word in body for word in ("exceed", "too large", "range", "must", "limit", "maximum"))
    if invalid and any(name in body for name in ("max_tokens", "max_completion_tokens")):
        return "provider reports an output token limit. Check the gateway's output-token settings"
    invalid = any(word in body for word in ("missing", "must", "invalid", "expect", "preced", "follow", "without"))
    if invalid and "reasoning_content" in body:
        return "provider rejects reasoning-message format; check the gateway's reasoning-message compatibility"
    if invalid and any(name in body for name in ("tool_call_id", "tool_calls", "tool response", "tool message")):
        return "provider rejects tool-message format; check the gateway's tool-call compatibility"
    if any(word in body for word in ("unsupported", "not supported", "does not support", "unknown", "unrecognized")):
        for name in ("reasoning_effort", "tool_choice", "tools", "temperature", "top_p", "max_tokens", "max_completion_tokens"):
            if name in body:
                return f"provider rejects {name}; check the gateway's parameter compatibility"
    return unknown


class ProviderProgress:
    """Panel-local request IDs and trusted attribution, including compaction."""

    def __init__(self, update, models: dict[str, str], summarizer: str):
        self.update = update
        self.models = models
        self.summarizer = summarizer
        self.number = 0
        self.actor = summarizer
        self.phase = "prepare"
        self.last_attempt = ""

    def started(self, actor: str, phase: str) -> None:
        self.number += 1
        self.actor, self.phase = actor, phase
        self.last_attempt = ""
        self.update(f"waiting for model response (request {self.number})",
                    model=self.models[actor], agent=actor, phase=phase)

    def failure_context(self) -> str:
        if not self.number:
            return ""
        attempt = self.last_attempt or f"request {self.number}; no HTTP attempt observed"
        return f"Last model request: [{self.models[self.actor]}] [{self.actor}] [{self.phase}] {attempt}."


@contextmanager
def observe_requests(update, models: dict[str, str], summarizer: str):
    observation = ProviderProgress(update, models, summarizer)
    token = _PANEL.set(observation)
    try:
        yield observation
    finally:
        _PANEL.reset(token)


@dataclass
class _Request:
    provider: object
    panel: ProviderProgress
    number: int
    context: dict
    attempt: int = 0
    fallback: int = 0
    output_error: Exception | None = None

    def write(self, output, message: str) -> None:
        # A broken stderr must not turn a successful POST into a model retry.
        # Stop the panel after the native retry operation has returned.
        if self.output_error is None:
            try:
                output(message, **self.context)
            except (OSError, ValueError) as exc:
                self.output_error = exc

    def label(self) -> str:
        fallback = f", fallback {self.fallback}" if self.fallback else ""
        attempt = "initial" if self.attempt == 1 else f"retry {self.attempt - 1}/{RETRIES}"
        return f"request {self.number}{fallback}, attempt {self.attempt}/{RETRIES + 1} ({attempt})"

    def post(self, transport, url, payload, headers=None, *, timeout):
        self.attempt += 1
        label = self.label()
        self.panel.last_attempt = f"{label}: awaiting HTTP response (--timeout={timeout:g}s)"
        self.write(self.panel.update, f"waiting for model response ({label})")
        self.write(emit, f"{label}: {_prompt_size(payload)}")
        started = time.monotonic()
        try:
            response = transport(url, payload, headers, timeout=timeout)
        except Exception as exc:
            detail = "transport error"
            hint = ""
            if isinstance(exc, kerness.ProviderHTTPError):
                detail = f"HTTP {int(exc.status_code)}"
                hint = _rejection_hint(exc)
            elif isinstance(exc, kerness.ProviderNetworkError):
                detail = "request timed out" if "timed out" in str(exc.cause).lower() else "network error"
            self.panel.last_attempt = (
                f"{label}: {detail} after {time.monotonic() - started:.1f}s (--timeout={timeout:g}s)"
                + (f"; {hint}" if hint else "")
            )
            self.write(emit, self.panel.last_attempt)
            if self.attempt <= RETRIES:
                self.write(self.panel.update,
                    f"request {self.number}: retry {self.attempt}/{RETRIES} in {RETRY_INTERVAL_SECONDS}s",
                )
            raise
        usage = (response.get("usage") or {}) if isinstance(response, dict) else {}
        tokens = usage.get("prompt_tokens", usage.get("input_tokens")) if isinstance(usage, dict) else None
        reported = f"; provider input tokens={tokens}" if type(tokens) is int and tokens >= 0 else ""
        self.panel.last_attempt = (
            f"{label}: HTTP response received in {time.monotonic() - started:.1f}s (--timeout={timeout:g}s)"
        )
        self.write(emit, self.panel.last_attempt + reported)
        return response


class ObservedProvider(kerness.CustomProvider):
    """Keep native retries/fallbacks; temporarily observe the public HTTP seam."""

    def chat_with_retries(self, model, messages, purpose="", tools=None, reasoning_effort="high"):
        panel = _PANEL.get()
        if panel is None:
            return super().chat_with_retries(model, messages, purpose, tools, reasoning_effort)
        active = _REQUEST.get()
        if active is not None and active.provider is self:
            # Native compatibility fallback recursively starts a new sequence.
            active.fallback += 1
            active.attempt = 0
            return super().chat_with_retries(model, messages, purpose, tools, reasoning_effort)
        if purpose == "compaction":
            # Kerness emits no provider_started event for its summarizer.
            panel.started(panel.summarizer, "compact")
        request = _Request(self, panel, panel.number,
                           {"model": panel.models[panel.actor], "agent": panel.actor, "phase": panel.phase})
        # The transport hook is process-global. Serialize our scoped installs;
        # ContextVar filtering lets unrelated threads use it without observation.
        with _TRANSPORT_LOCK:
            transport = kerness.provider.http_post_json

            def post(url, payload, headers=None, *, timeout):
                if _REQUEST.get() is request:
                    return request.post(transport, url, payload, headers, timeout=timeout)
                return transport(url, payload, headers, timeout=timeout)

            token = _REQUEST.set(request)
            kerness.provider.http_post_json = post
            try:
                response = super().chat_with_retries(model, messages, purpose, tools, reasoning_effort)
            finally:
                kerness.provider.http_post_json = transport
                _REQUEST.reset(token)
        if request.output_error is not None:
            raise request.output_error
        return response
