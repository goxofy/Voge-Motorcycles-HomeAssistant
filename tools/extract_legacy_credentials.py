#!/usr/bin/env python3
"""Extract local legacy signer values from the user's JADX output.

The generated module is intentionally excluded from source control. This script never
prints either value.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    text = args.source.read_text(encoding="utf-8")
    access_match = re.search(
        r'\.put\(\s*"accessKey"\s*,\s*"([^"]+)"\s*\)',
        text,
    )
    secret_match = re.search(
        r'VogeSignUtil\.getSign\(.*?,\s*"([^"]+)"\s*\)',
        text,
        re.DOTALL,
    )
    if access_match is None or secret_match is None:
        raise SystemExit("Could not identify both legacy signer values")

    access_key = access_match.group(1)
    signing_secret = secret_match.group(1)
    if not access_key or not signing_secret:
        raise SystemExit("Extracted an empty legacy signer value")

    args.output.write_text(
        '"""Private values generated locally from the supplied official APK."""\n\n'
        "# Never publish this file or include it in diagnostics.\n"
        f"LEGACY_ACCESS_KEY = {access_key!r}\n"
        f"LEGACY_SIGNING_SECRET = {signing_secret!r}\n",
        encoding="utf-8",
    )
    os.chmod(args.output, 0o600)
    print(f"Generated private credential module at {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
