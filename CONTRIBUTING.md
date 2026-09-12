# Contributing

Contributions are welcome.

## Before opening an issue or pull request

- Search existing issues and pull requests.
- Do not publish mobile numbers, passwords, password hashes, access or refresh tokens, VINs, complete device/message/route identifiers, precise coordinates, addresses, raw responses, or private signing material.
- Use private GitHub security advisories for vulnerabilities. See [SECURITY.md](SECURITY.md).

## Development setup

The compatibility baseline is Home Assistant 2026.9.0 with Python 3.14.2. With `uv` installed:

```bash
uv run --python 3.14.2 --with pytest --with pytest-homeassistant-custom-component \
  --with homeassistant==2026.9.0 --with aiohttp \
  pytest -q --asyncio-mode=auto

uv run --python 3.14.2 --with ruff ruff check .

uv run --python 3.14.2 --with pyright --with homeassistant==2026.9.0 \
  --with pytest pyright custom_components/voge tests \
  tools/inspect_vehicle_capabilities.py
```

Tests must use synthetic fixtures and mocks. Normal test and validation runs must not call production services.

## Pull requests

A pull request should:

1. Describe the intended Home Assistant behavior.
2. Add regression tests for changed behavior.
3. Update user documentation and translations when necessary.
4. Pass tests, Ruff, Pyright, HACS validation, and Hassfest.

Do not include generated caches, Home Assistant local state, local inspection output, private data, or distributable archives.
