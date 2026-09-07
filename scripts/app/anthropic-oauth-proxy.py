#!/usr/bin/env python3
"""
Anthropic OAuth proxy for the OpenMAIC sidecar.

OpenMAIC's Anthropic provider only knows API keys (x-api-key). A Claude
subscription uses an OAuth token that must go out as `Authorization: Bearer`
with Claude Code's beta headers, user-agent and system prefix. This proxy
accepts plain Anthropic Messages API requests on localhost, resolves the OAuth
token through Hermes' credential layer (auto-refresh included) and forwards to
api.anthropic.com, streaming the response back unchanged.

Usage: anthropic-oauth-proxy.py [--port 3101]
Point OpenMAIC at it:  ANTHROPIC_BASE_URL=http://127.0.0.1:3101/v1  ANTHROPIC_API_KEY=oauth
"""

import argparse
import http.client
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERMES_AGENT = Path(os.environ.get("HERMES_AGENT_DIR", Path.home() / ".hermes" / "hermes-agent"))
sys.path.insert(0, str(HERMES_AGENT))

UPSTREAM_HOST = "api.anthropic.com"
BETAS = "claude-code-20250219,oauth-2025-04-20"
SYSTEM_PREFIX = "You are Claude Code, Anthropic's official CLI for Claude."
HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade", "proxy-authorization",
              "host", "content-length", "x-api-key", "authorization"}


def _claude_code_version() -> str:
    try:
        out = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=5).stdout.strip()
        if out:
            return out.split()[0]
    except Exception:  # noqa: BLE001
        pass
    return "2.1.74"


CC_VERSION = _claude_code_version()


def resolve_token() -> str:
    from agent.anthropic_credentials import resolve_anthropic_token  # Hermes: env > ~/.claude creds (refreshes) > pool

    token = resolve_anthropic_token()
    if not token:
        raise RuntimeError("No Anthropic OAuth token found (run `claude` login or `hermes auth`)")
    return token


def _inject_system_prefix(body: bytes) -> bytes:
    """Claude Code OAuth tokens are only accepted when the system prompt starts with the CLI identity."""
    try:
        data = json.loads(body)
    except Exception:  # noqa: BLE001
        return body
    system = data.get("system")
    prefix = {"type": "text", "text": SYSTEM_PREFIX}
    if system is None:
        data["system"] = [prefix]
    elif isinstance(system, str):
        data["system"] = [prefix, {"type": "text", "text": system}] if system else [prefix]
    elif isinstance(system, list):
        if not (system and isinstance(system[0], dict) and str(system[0].get("text", "")).startswith(SYSTEM_PREFIX)):
            data["system"] = [prefix] + system
    return json.dumps(data).encode()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002  # quieter, one line per request
        sys.stderr.write("%s %s\n" % (self.address_string(), format % args))

    def _forward(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if self.command == "POST" and self.path.rstrip("/").endswith("/messages"):
            body = _inject_system_prefix(body)
        try:
            token = resolve_token()
        except Exception as e:  # noqa: BLE001
            self._error(401, str(e))
            return

        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
        headers["Authorization"] = f"Bearer {token}"
        headers["anthropic-version"] = headers.get("anthropic-version", "2023-06-01")
        existing = headers.get("anthropic-beta", "")
        headers["anthropic-beta"] = ",".join([b for b in existing.split(",") if b] + BETAS.split(","))
        headers["user-agent"] = f"claude-code/{CC_VERSION} (external, cli)"
        headers["x-app"] = "cli"
        headers["Content-Length"] = str(len(body))

        conn = http.client.HTTPSConnection(UPSTREAM_HOST, timeout=600)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            self.send_response(resp.status)
            chunked = resp.getheader("transfer-encoding", "").lower() == "chunked"
            for k, v in resp.getheaders():
                if k.lower() in ("connection", "keep-alive", "transfer-encoding", "content-length"):
                    continue
                self.send_header(k, v)
            if chunked or resp.getheader("content-length") is None:
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
            else:
                data = resp.read()
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            self.wfile.flush()
        except Exception as e:  # noqa: BLE001
            self._error(502, f"upstream error: {e}")
        finally:
            conn.close()

    def _error(self, status: int, message: str):
        payload = json.dumps({"type": "error", "error": {"type": "proxy_error", "message": message}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true,"proxy":"anthropic-oauth"}')
            return
        self._forward()

    do_POST = _forward


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("ANTHROPIC_PROXY_PORT", "3101")))
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    resolve_token()  # fail fast if no credentials
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"anthropic-oauth-proxy listening on http://{args.host}:{args.port} (claude-code/{CC_VERSION})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
