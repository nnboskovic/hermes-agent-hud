# Security Policy

## Supported versions

Security fixes are applied to the latest release.

## Reporting a vulnerability

Please use GitHub's **Report a vulnerability** flow under the repository's Security tab. Do not open a public issue for credential exposure, path traversal, symlink escape, unsafe plugin loading, or private-state disclosure.

A useful report includes:

- Hermes Agent and Hermes Desktop versions.
- Operating system.
- Reproduction steps using synthetic or redacted data.
- The affected projection, route, or file-confinement boundary.

Do not include real API keys, tokens, prompts, message bodies, private file contents, or unrestricted logs.

## Security posture

Agent HUD registers no model-facing tools or mutation actions. The backend is opt-in through Hermes's plugin allow-list, publishes a bounded sanitized projection, and returns generic failures rather than exception details. Third-party Hermes plugins execute as trusted local code after explicit user enablement; review source before enabling any plugin.
