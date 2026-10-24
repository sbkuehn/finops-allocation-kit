"""
validate_weights.py

Sanity checks for a shared-resource weights file before it goes anywhere
near a showback report. Catches the stuff that quietly makes numbers wrong:

  - weights that don't sum to 1.0 for a resource (money appears or vanishes)
  - negative weights or weights over 1.0
  - duplicate Team rows for the same resource and period
  - shared resources in the export that have no weighting at all

Exits non-zero on errors so you can drop it into a pipeline.

Usage:
    python scripts/validate_weights.py examples/shared_resource_weights.csv \
        --export examples/focus_export_sample.csv
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from allocate import classify, load_costs  # noqa: E402

TOLERANCE = 0.001


def check(weights: pd.DataFrame, export: pd.DataFrame | None = None) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    keys = ["ResourceId"] + (["BillingPeriodStart"] if "BillingPeriodStart" in weights.columns else [])

    bad_range = weights[(weights["WeightShare"] < 0) | (weights["WeightShare"] > 1)]
    for _, r in bad_range.iterrows():
        errors.append(f"{r['ResourceId']} / {r['Team']}: WeightShare {r['WeightShare']} is outside 0..1")

    dupes = weights[weights.duplicated(keys + ["Team"], keep=False)]
    for k, _ in dupes.groupby(keys + ["Team"]):
        errors.append(f"Duplicate weight row for {k}")

    sums = weights.groupby(keys)["WeightShare"].sum()
    for k, total in sums.items():
        if abs(total - 1.0) > TOLERANCE:
            errors.append(f"{k}: weights sum to {total:.4f}, expected 1.0")

    if export is not None:
        shared = export[classify(export) == "shared"]
        names = set(shared.get("ResourceName", shared["ResourceId"])) | set(shared["ResourceId"])
        weighted = set(weights["ResourceId"])
        for name in sorted(n for n in set(shared.get("ResourceName", shared["ResourceId"])) if n not in weighted):
            full = shared.loc[shared.get("ResourceName", shared["ResourceId"]) == name, "ResourceId"].iloc[0]
            if full not in weighted:
                warnings.append(f"Shared resource {name} has no weighting (lands in UNALLOCATED_NO_WEIGHT)")
        for w in sorted(weighted - names):
            warnings.append(f"Weights reference {w}, which isn't a shared resource in this export")

    return errors, warnings


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("weights")
    p.add_argument("--export", help="FOCUS export, to cross-check shared resources")
    args = p.parse_args()

    weights = pd.read_csv(args.weights)
    export = load_costs(args.export) if args.export else None
    errors, warnings = check(weights, export)

    for w in warnings:
        print(f"WARN   {w}")
    for e in errors:
        print(f"ERROR  {e}")
    if not errors and not warnings:
        print("Weights look good.")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
