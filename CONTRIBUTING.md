# Contributing

Contributions are welcome when they preserve the core contract: Agent HUD is a bounded, read-only observability surface, not an agent control plane or raw transcript viewer.

## Development

```bash
npm ci --ignore-scripts --no-audit --no-fund
python3 -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py' -v
node tests/test_ui_model.mjs
npm run test:desktop
gjs tests/test_css.js
node --check desktop/plugin.js
hermes plugins doctor . --ci
```

Linux native integration tests require GTK 3, GJS, AyatanaAppIndicator3, Xvfb, and xdotool.

## Pull requests

- Add a regression test before changing behavior.
- Keep every displayed field tied to an authoritative source.
- Do not add mutation controls, prompts, reasoning, raw results, file contents, full patch bodies, credentials, or unrestricted paths.
- Preserve independent primary-agent groups; never infer ownership.
- Include the Hermes version and platforms tested.
- Run `git diff --check` before submitting.

By contributing, you agree that your contribution is licensed under the MIT License.
