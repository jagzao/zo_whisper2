# 0006 — Private LAN access for phone uploads

## Status
Accepted

## Decision

The dashboard remains loopback-bound by default. Setting `DASHBOARD_HOST=0.0.0.0`
enables access from private or loopback IP addresses so a phone on the same LAN
can use the existing `/api/upload` form for audio and video. Requests with a
public client or Host address are rejected. Mutating requests still require the
per-process dashboard token and a local Origin.

Use the computer's private IP and dashboard port from the phone. This is a
trusted-LAN boundary, not user authentication or encryption; do not expose the
port to the public internet.
