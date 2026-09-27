"""Command-line retraining for operators who cannot use the API.

The API endpoint ``POST /models/retrain`` is the normal path, because it also
registers the new version and audits the run. This script covers the offline case:
retraining from CSV files on a machine that has the model directory but not the
database, for example when preparing a bundle to ship.

    python ml/retrain.py --extra-csv new_outcomes.csv --activate
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from features import PORTFOLIO_LABEL  # noqa: E402
from train_model import HISTORY_PATH, load_training_frame, train_bundle  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrain delay models from CSV inputs")
    parser.add_argument("--extra-csv", action="append", default=[], help="Additional labelled CSV; repeatable")
    parser.add_argument("--version", default=None, help="Version label (default: utc timestamp)")
    parser.add_argument("--activate", action="store_true", help="Point serving at the new bundle")
    args = parser.parse_args()

    frame, source = load_training_frame()
    for path in args.extra_csv:
        extra = pd.read_csv(path)
        if PORTFOLIO_LABEL not in extra.columns:
            raise SystemExit(f"{path} has no '{PORTFOLIO_LABEL}' column")
        # Later files win for a project that appears more than once.
        frame = pd.concat([frame, extra]).drop_duplicates(subset="project_id", keep="last")
        source = f"{source} + file:{Path(path).name}({len(extra)})"

    version = args.version or datetime.now(timezone.utc).strftime("v%Y%m%d%H%M%S")
    card = train_bundle(frame, version, source, mirror=args.activate)
    print(json.dumps({
        "version": card["version"], "rows": card["training_rows"], "source": source,
        "activated": args.activate, "seed_history": str(HISTORY_PATH),
        "metrics": {"portfolio": {key: value for key, value in card["metrics"]["portfolio"].items() if key != "importance"}},
    }, indent=2))


if __name__ == "__main__":
    main()
