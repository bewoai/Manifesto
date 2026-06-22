"""CLI: planlama xlsx + gün + balon kodu -> <BALLOON>.xlsx manifesto.

Kullanım:
  python -m scripts.export_manifest --date 22.06.2026 --balloon BZR --out-dir .
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402
from app.manifest.writer import build_rows, export  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="planlama sayfa adı, ör. 22.06.2026")
    ap.add_argument("--balloon", required=True, help="balon kodu, ör. BZR")
    ap.add_argument("--planning", type=Path, default=config.PLANNING_XLSX)
    ap.add_argument("--template", type=Path, default=config.MANIFEST_TEMPLATE_PATH)
    ap.add_argument("--out-dir", type=Path, default=Path("."))
    args = ap.parse_args()

    rows = build_rows(args.planning, args.date, args.balloon)
    warned = [r for r in rows if r.warnings]
    path = export(args.planning, args.date, args.balloon, args.out_dir, args.template)
    print(f"{len(rows)} yolcu yazıldı -> {path}")
    for r in warned:
        print(f"  [uyarı] {r.name}: {'; '.join(r.warnings)}")


if __name__ == "__main__":
    main()
