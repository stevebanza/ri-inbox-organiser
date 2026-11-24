"""File country data attachments from a mailbox into Country/DataType folders.

    python organise.py --demo                      # build a synthetic inbox and file it
    python organise.py --source eml --eml-dir X    # a folder of exported .eml files
    python organise.py --source outlook            # Outlook desktop inbox (Windows)
    python organise.py --source outlook --dry-run  # show decisions, save nothing
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

from organiser.demo import write_demo_inbox
from organiser.process import process
from organiser.report import build_report
from organiser.sources import eml_messages, outlook_messages


def load_config(path: str) -> dict:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    env = os.environ.get("TARGET_RECIPIENTS")
    if env:  # real addresses stay out of the repository
        cfg["target_recipients"] = [a.strip() for a in env.split(",") if a.strip()]
    if os.environ.get("ESA_ROOT"):
        cfg["output_root"] = os.environ["ESA_ROOT"]
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--source", choices=["outlook", "eml"], default="eml")
    ap.add_argument("--eml-dir", default="inbox_demo")
    ap.add_argument("--outlook-folder", help="e.g. 'Inbox/RI data' (default: Inbox)")
    ap.add_argument("--days", type=int, help="override days_back")
    ap.add_argument("--out", help="override output_root")
    ap.add_argument("--dry-run", action="store_true", help="decide and report, save nothing")
    ap.add_argument("--demo", action="store_true", help="write the synthetic inbox first")
    a = ap.parse_args()

    cfg = load_config(a.config)
    days = a.days or cfg["days_back"]
    root = Path(a.out or cfg["output_root"])
    if a.demo:
        write_demo_inbox(Path(a.eml_dir))
    msgs = (outlook_messages(days, a.outlook_folder) if a.source == "outlook"
            else eml_messages(Path(a.eml_dir), days))
    result = process(msgs, cfg, root, dry_run=a.dry_run)
    report = build_report(result, root / "_reports" / f"run_{result['run'].replace(':', '')}.html")
    for k, v in sorted(result["counts"].items()):
        print(f"{k:<45}{v:>5}")
    for r in result["rows"]:
        if r["status"] != "skipped":
            print(f"  {r['status']:<10} {r['country']:<14} {r['data_type']:<8} {r['attachment']}")
    print(f"Report: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
