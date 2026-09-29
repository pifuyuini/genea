"""Start Genea with the public 《红楼梦》 demo, fully isolated from the real data/ directory.

Each launch copies demo/data into demo/.runtime (ignored by Git) so edits made while presenting never
change the committed demo. Pass --keep to continue with the previous session's edits.

Usage:  python3 demo/run_demo.py [--port 8766] [--keep]
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

DEMO = Path(__file__).resolve().parent
ROOT = DEMO.parent
RUNTIME = DEMO / ".runtime"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--keep", action="store_true", help="keep edits from the previous demo session")
    args = parser.parse_args()
    if not args.keep or not (RUNTIME / "workspace.json").exists():
        shutil.rmtree(RUNTIME, ignore_errors=True)
        shutil.copytree(DEMO / "data", RUNTIME)
    print(f"Genea demo: http://127.0.0.1:{args.port}  (data: {RUNTIME.relative_to(ROOT)})")
    return subprocess.call([sys.executable, str(ROOT / "server.py"), "--port", str(args.port), "--data-dir", str(RUNTIME)])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
