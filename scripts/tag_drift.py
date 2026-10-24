"""
tag_drift.py

Presence-only tag audits tell you a resource has a team tag. They don't tell
you the tag is still true. This script compares two billing periods and flags
resources whose ownership tags changed, disappeared, or showed up, so a human
can confirm the change was intentional.

It also flags the quieter problem: a resource whose team tag stayed the same
while its cost jumped a lot, which is often a sign it got repurposed for some
other team's workload and nobody updated the tag.

Usage:
    python scripts/tag_drift.py examples/focus_export_sample.csv \
        --from 2026-08-01 --to 2026-09-01
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from allocate import load_costs  # noqa: E402

WATCH = ["x_Team", "x_CostCenter", "x_Shared", "x_Allocation"]


def snapshot(df: pd.DataFrame, period: str, cost_column: str) -> pd.DataFrame:
    chunk = df[df["BillingPeriodStart"] == period]
    cols = [c for c in WATCH if c in chunk.columns]
    agg = {c: "first" for c in cols}
    agg[cost_column] = "sum"
    return chunk.groupby("ResourceId").agg(agg)


def drift(df: pd.DataFrame, before: str, after: str, cost_column: str, jump: float) -> pd.DataFrame:
    a = snapshot(df, before, cost_column)
    b = snapshot(df, after, cost_column)
    joined = a.join(b, how="outer", lsuffix="_before", rsuffix="_after")
    findings = []
    for rid, r in joined.iterrows():
        name = rid.rsplit("/", 1)[-1]
        for c in WATCH:
            if f"{c}_before" not in joined.columns:
                continue
            old, new = r[f"{c}_before"], r[f"{c}_after"]
            old = None if pd.isna(old) else old
            new = None if pd.isna(new) else new
            if old != new:
                kind = "added" if old is None else "removed" if new is None else "changed"
                findings.append({"Resource": name, "Field": c, "Change": kind, "Before": old, "After": new})
        c0, c1 = r.get(f"{cost_column}_before"), r.get(f"{cost_column}_after")
        team_same = r.get("x_Team_before") == r.get("x_Team_after") and not pd.isna(r.get("x_Team_after"))
        if team_same and pd.notna(c0) and pd.notna(c1) and c0 > 0 and (c1 - c0) / c0 >= jump:
            findings.append({"Resource": name, "Field": cost_column, "Change": "cost jump, same owner",
                             "Before": round(c0, 2), "After": round(c1, 2)})
    return pd.DataFrame(findings, columns=["Resource", "Field", "Change", "Before", "After"])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input")
    p.add_argument("--from", dest="before", required=True)
    p.add_argument("--to", dest="after", required=True)
    p.add_argument("--cost-column", default="EffectiveCost")
    p.add_argument("--jump", type=float, default=0.5, help="flag same-owner cost jumps at or above this ratio")
    args = p.parse_args()

    df = load_costs(args.input)
    out = drift(df, args.before, args.after, args.cost_column, args.jump)
    if out.empty:
        print("No tag drift between those periods.")
    else:
        print(out.to_string(index=False))
        print(f"\n{len(out)} finding(s) to review.")


if __name__ == "__main__":
    main()
