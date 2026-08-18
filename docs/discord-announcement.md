# Discord announcement

**Hermes Agent HUD v1.0.0**

A privacy-safe, read-only live operations view for Hermes agents and subagents.

It adds a native Hermes Desktop pane, full sidebar page, and status-bar summary. Linux users can also install the independent always-on-top GTK overlay.

**Highlights**
- Independent primary-agent groups with their own subagents
- Explicit running/finalizing/stalling/completed/failed lifecycle
- Recent sanitized tool activity and diff/file/command summaries
- No model identity, inferred progress, prompts, reasoning, raw results, secrets, or mutation controls
- Cross-platform Desktop plugin; optional multi-monitor Linux overlay

**Install**
```bash
hermes plugins install nnboskovic/hermes-agent-hud --no-enable
hermes plugins enable agent-hud --no-allow-tool-override
```

Then fully restart Hermes Desktop and enable **Hermes Agent HUD** under **Settings → Plugins**.

Source, screenshots, privacy model, and Linux standalone instructions:
https://github.com/nnboskovic/hermes-agent-hud

MIT licensed. Tested with Hermes Agent 0.20.2.
