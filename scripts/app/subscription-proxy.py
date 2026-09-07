#!/usr/bin/env python3
"""
Subscription proxy for the OpenMAIC sidecar (Open Notebook's Learn feature).

Lets OpenMAIC — which only speaks API keys — use *subscription* models:

  * ``POST /v1/chat/completions``  OpenAI-compatible  -> ChatGPT/Codex OAuth (Hermes `openai-codex`)
  * ``POST /v1/messages``          Anthropic Messages -> Claude Code / Hermes OAuth (Bearer + CC betas)
  * ``GET  /v1/models``            lists the models below so OpenMAIC's probe works

Both credential paths reuse Hermes' own credential layer (``~/.hermes/hermes-agent``), so
tokens refresh exactly as they do for Hermes itself; nothing is stored by this proxy.

Failover: ``FALLBACK_CHAIN`` (env, comma-separated ``provider:model``) is tried in order when
the requested model fails with a retryable status (401/402/403/429/5xx or transport error).
The response carries ``x-proxy-served-by: provider:model`` so you can see what answered.

Usage: subscription-proxy.py [--port 3101]
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERMES_AGENT = Path(os.environ.get("HERMES_AGENT_DIR", Path.home() / ".hermes" / "hermes-agent"))
sys.path.insert(0, str(HERMES_AGENT))

# ---------------------------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------------------------
CODEX_MODELS = [m for m in os.environ.get("CODEX_MODELS", "gpt-5.5,gpt-5.6,gpt-6-astra").split(",") if m]
ANTHROPIC_MODELS = [
    m
    for m in os.environ.get(
        "ANTHROPIC_SUB_MODELS", "claude-haiku-4-5-20251001,claude-sonnet-5,claude-fable-5-1"
    ).split(",")
    if m
]
# Tried in order after the requested model fails. provider is "codex" or "anthropic".
FALLBACK_CHAIN: List[Tuple[str, str]] = []
for item in os.environ.get("FALLBACK_CHAIN", "codex:gpt-5.5,anthropic:claude-haiku-4-5-20251001").split(","):
    if ":" in item:
        prov, mdl = item.split(":", 1)
        FALLBACK_CHAIN.append((prov.strip(), mdl.strip()))

RETRYABLE_STATUS = {401, 402, 403, 408, 409, 425, 429, 500, 502, 503, 504, 529}
ANTHROPIC_HOST = "api.anthropic.com"
CC_BETAS = ["claude-code-20250219", "oauth-2025-04-20"]
CC_SYSTEM_PREFIX = "You are Claude Code, Anthropic's official CLI for Claude."


def _claude_code_version() -> str:
    try:
        out = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=5).stdout.strip()
        if out:
            return out.split()[0]
    except Exception:  # noqa: BLE001
        pass
    return "2.1.74"


CC_VERSION = _claude_code_version()


class UpstreamError(Exception):
    def __init__(self, status: int, message: str, body: Optional[bytes] = None):
        super().__init__(message)
        self.status, self.body = status, body


# ---------------------------------------------------------------------------------------------
# Anthropic (Claude subscription)
# ---------------------------------------------------------------------------------------------
def anthropic_token() -> str:
    from agent.anthropic_credentials import resolve_anthropic_token

    token = resolve_anthropic_token()
    if not token:
        raise UpstreamError(401, "No Anthropic OAuth token (run `claude` login or `hermes auth`)")
    return token


def _inject_cc_prefix(data: Dict[str, Any]) -> Dict[str, Any]:
    system = data.get("system")
    prefix = {"type": "text", "text": CC_SYSTEM_PREFIX}
    if system is None:
        data["system"] = [prefix]
    elif isinstance(system, str):
        data["system"] = [prefix, {"type": "text", "text": system}] if system else [prefix]
    elif isinstance(system, list):
        first = system[0] if system else None
        if not (isinstance(first, dict) and str(first.get("text", "")).startswith(CC_SYSTEM_PREFIX)):
            data["system"] = [prefix] + system
    return data


def anthropic_request(path: str, data: Dict[str, Any], req_headers: Dict[str, str]):
    """Returns an open (conn, response) pair for the caller to stream from."""
    body = json.dumps(_inject_cc_prefix(data)).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {anthropic_token()}",
        "anthropic-version": req_headers.get("anthropic-version", "2023-06-01"),
        "anthropic-beta": ",".join([b for b in req_headers.get("anthropic-beta", "").split(",") if b] + CC_BETAS),
        "user-agent": f"claude-code/{CC_VERSION} (external, cli)",
        "x-app": "cli",
        "Accept": "text/event-stream" if data.get("stream") else "application/json",
    }
    conn = http.client.HTTPSConnection(ANTHROPIC_HOST, timeout=600)
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    if resp.status >= 400:
        payload = resp.read()
        conn.close()
        raise UpstreamError(resp.status, f"anthropic {resp.status}: {payload[:300].decode(errors='replace')}", payload)
    return conn, resp


# ---------------------------------------------------------------------------------------------
# Codex (ChatGPT subscription) — via Hermes' Chat->Responses adapter
# ---------------------------------------------------------------------------------------------
_codex_lock = threading.Lock()
_codex_clients: Dict[str, Any] = {}


def codex_client(model: str):
    from agent.auxiliary_client import _build_codex_client

    with _codex_lock:
        client = _codex_clients.get(model)
        if client is None:
            client, _ = _build_codex_client(model)
            if client is None:
                raise UpstreamError(401, "No Codex OAuth token (run `hermes auth` / `codex login`)")
            _codex_clients[model] = client
        return client


def codex_chat(model: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Non-streaming chat completion through Codex; returns an OpenAI chat.completion dict."""
    kwargs: Dict[str, Any] = {"model": model, "messages": data.get("messages") or []}
    if data.get("tools"):
        kwargs["tools"] = data["tools"]
    reasoning: Dict[str, Any] = data.get("reasoning") if isinstance(data.get("reasoning"), dict) else {}
    effort = data.get("reasoning_effort") or reasoning.get("effort")
    if effort:
        kwargs["extra_body"] = {"reasoning": {"effort": effort}}
    try:
        r = codex_client(model).chat.completions.create(**kwargs)
    except Exception as e:  # noqa: BLE001
        status = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
        raise UpstreamError(int(status) if status else 502, f"codex: {e}") from e
    choice = r.choices[0]
    msg: Dict[str, Any] = {"role": "assistant", "content": choice.message.content}
    tool_calls = getattr(choice.message, "tool_calls", None)
    if tool_calls:
        msg["tool_calls"] = [
            tc if isinstance(tc, dict) else {
                "id": getattr(tc, "id", None),
                "type": "function",
                "function": {
                    "name": getattr(getattr(tc, "function", None), "name", None),
                    "arguments": getattr(getattr(tc, "function", None), "arguments", ""),
                },
            }
            for tc in tool_calls
        ]
    usage = getattr(r, "usage", None)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": msg, "finish_reason": choice.finish_reason or "stop"}],
        "usage": {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage, "total_tokens", 0) or 0,
        },
    }


def _chat_to_sse(completion: Dict[str, Any]) -> List[bytes]:
    """Synthesize OpenAI streaming chunks from a completed response (Codex assembles server-side)."""
    cid, model, created = completion["id"], completion["model"], completion["created"]
    msg = completion["choices"][0]["message"]

    def chunk(delta: Dict[str, Any], finish: Optional[str] = None) -> bytes:
        payload = {
            "id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return f"data: {json.dumps(payload)}\n\n".encode()

    frames = [chunk({"role": "assistant", "content": ""})]
    text = msg.get("content") or ""
    for i in range(0, len(text), 64):
        frames.append(chunk({"content": text[i:i + 64]}))
    for idx, tc in enumerate(msg.get("tool_calls") or []):
        frames.append(chunk({"tool_calls": [{"index": idx, **tc}]}))
    frames.append(chunk({}, completion["choices"][0]["finish_reason"]))
    frames.append(b"data: [DONE]\n\n")
    return frames


# ---------------------------------------------------------------------------------------------
# Anthropic Messages -> OpenAI chat (so Claude can back /v1/chat/completions in the failover chain)
# ---------------------------------------------------------------------------------------------
def _openai_messages_to_anthropic(messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    system_parts, out = [], []
    for m in messages:
        role, content = m.get("role"), m.get("content")
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
        content = content or ""
        if role == "system":
            system_parts.append(content)
        elif role in ("user", "assistant"):
            if out and out[-1]["role"] == role:
                out[-1]["content"] += "\n\n" + content
            else:
                out.append({"role": role, "content": content})
        elif role == "tool":
            out.append({"role": "user", "content": f"[tool result]\n{content}"})
    if not out or out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": "(start)"})
    return "\n\n".join(system_parts), out


def anthropic_chat(model: str, data: Dict[str, Any]) -> Dict[str, Any]:
    system, messages = _openai_messages_to_anthropic(data.get("messages") or [])
    payload: Dict[str, Any] = {
        "model": model, "max_tokens": int(data.get("max_tokens") or data.get("max_completion_tokens") or 8192),
        "messages": messages,
    }
    if system:
        payload["system"] = system
    if data.get("temperature") is not None:
        payload["temperature"] = data["temperature"]
    conn, resp = anthropic_request("/v1/messages", payload, {})
    try:
        body = json.loads(resp.read())
    finally:
        conn.close()
    text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
    usage = body.get("usage", {})
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                     "finish_reason": "length" if body.get("stop_reason") == "max_tokens" else "stop"}],
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0), "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        },
    }


# ---------------------------------------------------------------------------------------------
# Routing + failover
# ---------------------------------------------------------------------------------------------
def provider_for(model: str) -> str:
    if model in ANTHROPIC_MODELS or model.startswith("claude"):
        return "anthropic"
    return "codex"


def chat_with_failover(data: Dict[str, Any]) -> Tuple[Dict[str, Any], str, List[str]]:
    requested = data.get("model") or (CODEX_MODELS[0] if CODEX_MODELS else "gpt-5.5")
    attempts: List[Tuple[str, str]] = [(provider_for(requested), requested)]
    attempts += [a for a in FALLBACK_CHAIN if a not in attempts]
    errors: List[str] = []
    for prov, mdl in attempts:
        try:
            result = anthropic_chat(mdl, data) if prov == "anthropic" else codex_chat(mdl, data)
            return result, f"{prov}:{mdl}", errors
        except UpstreamError as e:
            errors.append(f"{prov}:{mdl} -> {e.status}: {e}")
            # 400 = our request is malformed; retrying it elsewhere won't help — unless the
            # complaint is about the model itself (unsupported/not found), which is a routing problem.
            if e.status == 400 and "model" not in str(e).lower():
                raise
            continue
        except Exception as e:  # noqa: BLE001
            errors.append(f"{prov}:{mdl} -> {e}")
            continue
    raise UpstreamError(502, "all providers failed: " + " | ".join(errors))


# ---------------------------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), format % args))

    # -- helpers --
    def _json(self, status: int, obj: Any, extra: Optional[Dict[str, str]] = None):
        payload = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, status: int, message: str, openai_style: bool = True):
        body = {"error": {"message": message, "type": "proxy_error", "code": status}} if openai_style else {
            "type": "error", "error": {"type": "proxy_error", "message": message}}
        self._json(status, body)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw or b"{}")

    def _sse(self, frames: List[bytes], extra: Optional[Dict[str, str]] = None):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        for f in frames:
            self.wfile.write(b"%x\r\n%s\r\n" % (len(f), f))
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    # -- routes --
    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path in ("", "/health"):
            self._json(200, {"ok": True, "proxy": "subscription", "codex_models": CODEX_MODELS,
                             "anthropic_models": ANTHROPIC_MODELS, "fallback_chain": FALLBACK_CHAIN})
        elif path.endswith("/models"):
            now = int(time.time())
            self._json(200, {"object": "list", "data": [
                {"id": m, "object": "model", "created": now, "owned_by": "openai-subscription"} for m in CODEX_MODELS
            ] + [
                {"id": m, "object": "model", "created": now, "owned_by": "anthropic-subscription"} for m in ANTHROPIC_MODELS
            ]})
        else:
            self._error(404, f"unknown path {path}")

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        try:
            data = self._read_json()
        except Exception as e:  # noqa: BLE001
            self._error(400, f"invalid JSON: {e}")
            return
        if path.endswith("/chat/completions"):
            self._chat(data)
        elif path.endswith("/messages"):
            self._messages(data)
        else:
            self._error(404, f"unknown path {path}")

    def _chat(self, data: Dict[str, Any]):
        try:
            result, served_by, errors = chat_with_failover(data)
        except UpstreamError as e:
            self._error(e.status if e.status >= 400 else 502, str(e))
            return
        extra = {"x-proxy-served-by": served_by}
        if errors:
            extra["x-proxy-failover"] = "; ".join(errors)[:900]
            sys.stderr.write(f"failover -> {served_by} after: {errors}\n")
        if data.get("stream"):
            self._sse(_chat_to_sse(result), extra)
        else:
            self._json(200, result, extra)

    def _messages(self, data: Dict[str, Any]):
        """Native Anthropic passthrough (streaming preserved), with model failover inside Anthropic."""
        requested = data.get("model") or ANTHROPIC_MODELS[0]
        candidates = [requested] + [m for p, m in FALLBACK_CHAIN if p == "anthropic" and m != requested]
        errors: List[str] = []
        for mdl in candidates:
            try:
                conn, resp = anthropic_request(self.path.split("?")[0], {**data, "model": mdl},
                                               {k: v for k, v in self.headers.items()})
            except UpstreamError as e:
                errors.append(f"anthropic:{mdl} -> {e.status}: {e}")
                if e.status == 400:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(e.body or b"")))
                    self.end_headers()
                    self.wfile.write(e.body or b"")
                    return
                continue
            except Exception as e:  # noqa: BLE001
                errors.append(f"anthropic:{mdl} -> {e}")
                continue
            try:
                self.send_response(resp.status)
                for k, v in resp.getheaders():
                    if k.lower() in ("connection", "keep-alive", "transfer-encoding", "content-length"):
                        continue
                    self.send_header(k, v)
                self.send_header("x-proxy-served-by", f"anthropic:{mdl}")
                if errors:
                    self.send_header("x-proxy-failover", "; ".join(errors)[:900])
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            finally:
                conn.close()
            return
        self._error(502, "all anthropic models failed: " + " | ".join(errors), openai_style=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("SUBSCRIPTION_PROXY_PORT", "3101")))
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    ready = []
    try:
        anthropic_token()
        ready.append("anthropic")
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"anthropic: {e}\n")
    try:
        if CODEX_MODELS:
            codex_client(CODEX_MODELS[0])
            ready.append("codex")
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"codex: {e}\n")
    if not ready:
        sys.exit("no subscription credentials available")
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"subscription-proxy on http://{args.host}:{args.port} providers={ready} "
          f"fallback={FALLBACK_CHAIN} (claude-code/{CC_VERSION})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
