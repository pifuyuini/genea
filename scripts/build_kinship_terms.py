#!/usr/bin/env python3
"""Export a blood-relative naming table from the pinned relationship.js release.

Uses the Python standard library and macOS JavaScriptCore. No Node or npm is
required. Supply --source-file to rebuild entirely offline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from urllib.request import urlopen

VERSION = "1.2.9"
SOURCE_REVISION = "35c44427befb6fd59e16f583b5b92a680a7948db"
SOURCE_URL = (
    "https://raw.githubusercontent.com/mumuy/relationship/"
    f"{SOURCE_REVISION}/dist/relationship.min.js"
)
JSC = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc"

# A canonical blood path is either direct ancestry/descent or an ancestry
# prefix, exactly one gender-specific sibling pivot, and a descent suffix.
# Age, spouse, ego-sex prefixes, and multiple sibling pivots are excluded.
EXPORT_JAVASCRIPT = r"""
const bloodPath = /^(?:[fm],)*[fm]$|^(?:[sd],)*[sd]$|^(?:[fm],)*(?:xb|xs)(?:,[sd])*$/;
const terms = Object.fromEntries(
    Array.from(relationship.data.entries()).filter(([selector]) => bloodPath.test(selector))
);
print(JSON.stringify(terms));
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-file", type=Path,
        help="Read the official JavaScript bundle from this file instead of downloading it.",
    )
    parser.add_argument(
        "--output", type=Path, required=True,
        help="Explicit destination for the generated JSON table.",
    )
    args = parser.parse_args()

    if args.source_file is None:
        with urlopen(SOURCE_URL, timeout=30) as response:
            source = response.read().decode("utf-8")
    else:
        source = args.source_file.read_text(encoding="utf-8")

    # A release header check confirms the documented version; provenance is
    # the pinned official revision above, rather than a content checksum.
    version = re.search(r"relationship\.js v([0-9]+\.[0-9]+\.[0-9]+)", source)
    if version is None or version.group(1) != VERSION:
        raise ValueError(f"Expected the official relationship.js v{VERSION} bundle")

    result = subprocess.run(
        [JSC, "-e", source + "\n" + EXPORT_JAVASCRIPT],
        check=True, capture_output=True, text=True, timeout=30,
    )
    terms = json.loads(result.stdout)
    serialized = json.dumps(terms, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    args.output.write_text(serialized, encoding="utf-8")
    print(f"Exported {len(terms)} selectors from relationship.js v{VERSION} to {args.output}")


if __name__ == "__main__":
    main()
