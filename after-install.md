# Agent HUD installed

The package is installed but inert until you explicitly enable both halves:

1. Enable the read-only backend:

   ```bash
   hermes plugins enable agent-hud --no-allow-tool-override
   ```

2. Fully quit and reopen Hermes Desktop so the backend route mounts.
3. In **Settings → Plugins**, enable **Hermes Agent HUD**.

The plugin adds a right-side pane, an **Agent HUD** sidebar page, and a status-bar summary. It registers no model-facing tools or mutation actions.

Linux users who want the independent always-on-top GTK overlay can install it separately from this repository with `python3 install.py`.
