# Changelog

All notable changes to Hermes Agent HUD are documented here.

## 1.0.1 — 2026-08-18

- Count fresh Desktop and CLI sessions even when the messaging gateway reports no active foreground turns.
- Preserve `gateway_state.active_agents` as a lower bound for gateway work that has not reached the session database yet.
- Use the newer of session-summary and message activity when deciding whether an open session is fresh.

## 1.0.0 — 2026-08-18

- Publishable unified Hermes plugin with a native Desktop pane, page, sidebar entry, and status chip.
- Bounded read-only backend route at `/api/plugins/agent-hud/state`.
- Independent primary-agent groups with authoritative subagent ownership.
- Recent structured activity with command, file, diff, and tool projections.
- Linux standalone GTK overlay with AppIndicator, private position persistence, and multi-monitor clamping.
- Privacy hardening for paths, credentials, malformed metadata, symlinked logs, and bounded collections.
- Descriptor-verified delegation-manifest reads reject symlinks, replacement races, non-regular files, and oversized payloads.
- MIT licensing and clean-room plugin lifecycle acceptance.
