# Changelog

All notable changes to Hermes Agent HUD are documented here.

## 1.0.0 — 2026-08-18

- Publishable unified Hermes plugin with a native Desktop pane, page, sidebar entry, and status chip.
- Bounded read-only backend route at `/api/plugins/agent-hud/state`.
- Independent primary-agent groups with authoritative subagent ownership.
- Recent structured activity with command, file, diff, and tool projections.
- Linux standalone GTK overlay with AppIndicator, private position persistence, and multi-monitor clamping.
- Privacy hardening for paths, credentials, malformed metadata, symlinked logs, and bounded collections.
- Descriptor-verified delegation-manifest reads reject symlinks, replacement races, non-regular files, and oversized payloads.
- MIT licensing and clean-room plugin lifecycle acceptance.
