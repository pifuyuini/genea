"""Run the public 《百年孤独》 Demo2 in an isolated mutable data copy."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import shutil
import subprocess
import sys
from pathlib import Path

DEMO = Path(__file__).resolve().parent
ROOT = DEMO.parent


def prepare_data_directory(data_dir: str | Path | None = None) -> Path:
    if data_dir is not None:
        target = Path(data_dir).expanduser().resolve()
        protected = (ROOT / "data", ROOT / "demo" / "data", DEMO / "data")
        if any(target == source.resolve() or target.is_relative_to(source.resolve()) for source in protected):
            raise ValueError("Demo2 must use an independent data copy, never the real data/ or either committed demo data/.")
        if not target.is_dir() or not (target / "workspace.json").is_file():
            raise ValueError("--data-dir must point to an existing independent directory containing workspace.json.")
        return target

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    session = ROOT / "tmp" / (stamp + "-genea-demo2")
    session.mkdir(parents=True, exist_ok=False)
    (session / ".codex-tmp").write_text("Created by demo2/run_demo.py as an isolated Demo2 session.\n", encoding="utf-8")
    target = session / "data"
    shutil.copytree(DEMO / "data", target)
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--data-dir", help="reuse an existing independent Demo2 data copy without resetting edits")
    args = parser.parse_args(argv)
    try:
        data_dir = prepare_data_directory(args.data_dir)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Genea Demo2: http://127.0.0.1:{args.port}  (data: {data_dir})", flush=True)
    print("首次默认启用实验功能；已有 settings.json 的选择优先。", flush=True)
    return subprocess.call([sys.executable, str(ROOT / "server.py"), "--port", str(args.port),
                            "--data-dir", str(data_dir), "--experimental-cross-generation"])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
