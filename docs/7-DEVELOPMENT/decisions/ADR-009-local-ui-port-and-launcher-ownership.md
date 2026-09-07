# ADR-009: Local UI runs on port 3001; the launcher owns only verified processes

- **Status**: Accepted
- **Date**: 2026-09
- **Related**: `scripts/app/open-notebook.sh`, `scripts/app/test_launcher.py`, [learn-feature.md](../learn-feature.md)

## Context

This personal fork runs as a packaged macOS app next to other local services. On the primary machine the Hermes WhatsApp bridge already listens on port 3000, so the Next.js default port made the Notebook UI fail to start. The first launcher also reused any listener on its ports and stopped processes by name pattern, which could terminate an unrelated service that merely looked similar.

## Decision

**The fork's local UI runs on port 3001 (`UI_PORT` override allowed), and the launcher may only reuse, rebuild, or stop a process whose identity it has verified as its own service.**

- Development commands use `PORT=3001 npm run dev` / `PORT=3001 make start-all`; upstream Docker images and generic docs keep port 3000.
- Ownership requires the service's PID file plus a matching command and working directory (and a start-time stamp for launcher-started processes). An occupied port or a bare PID is never proof of ownership.
- Frontend and OpenMAIC builds run only while their verified process is stopped; an owned process on an old port fails fast with a stop/restart message instead of being killed.
- Shutdown signals verified owner process trees only; no `pkill` by name or port.

## Alternatives considered

- **Move WhatsApp off 3000** — rejected: Hermes owns that bridge configuration, and the Notebook launcher must not depend on another tool's port.
- **Kill whatever holds the port** — rejected: this is exactly the unrelated-process kill the reliability pass reproduced.
- **Detect the frontend by bound socket** — rejected: unproven on macOS and weaker than command + cwd + start time.

## Consequences

- Any doc or config that assumes port 3000 for this fork is wrong; upstream defaults are intentionally untouched.
- Rebuilding the UI or Learn sidecar requires stopping the app first (the launcher says so).
- OpenMAIC's CSP `frame-ancestors` is baked with the UI URL at build time, so changing `UI_PORT` triggers a sidecar rebuild.
