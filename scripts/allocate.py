"""
allocate.py

FOCUS-based showback allocation with tag-and-fallback logic.

Every cost row lands in exactly one of these places:

  1. Direct      the row carries a team tag, so that team owns the cost
  2. Central     the row is tagged allocation=central, meaning your written
                 shared-cost policy says it stays on the central budget
  3. Weighted    the row is tagged shared=true and has a usage weighting
                 (GPU-hours, CPU-seconds, requests), so it gets split
  4. Fallback    shared=true but no weighting yet. Either an even split
                 across teams (--fallback even) or a tracked bucket
                 (--fallback bucket, the default)
  5. Unallocated no team, not shared, not central. This is the number you
                 want to shrink every month

Pick which FOCUS cost column to allocate with --cost-column:

  EffectiveCost  amortized cost with commitment discounts applied to whoever
                 consumed them (teams get the benefit of the RI/Savings Plan)
  ListCost       public on-demand rate (finance keeps the discount as its
                 own lever and teams see the "undiscounted" number)
  BilledCost     what hit the invoice on that line (useful for reconciling,
                 confusing for showback because commitment purchases show up
                 as their own lines)

Whichever you pick, write it down. Switching between them is the classic
"why did my number move 20% this month" budget meeting question.

Usage:
    python scripts/allocate.py examples/focus_export_sample.csv \
        --weights examples/shared_resource_weights.csv \
        --cost-column EffectiveCost --period 2026-09-01
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from flatten_tags import flatten  # noqa: E402

UNALLOCATED = "UNALLOCATED"
UNALLOCATED_NO_WEIGHT = "UNALLOCATED_NO_WEIGHT"
CENTRAL = "CENTRAL"
UNALLOCATED_BUCKETS = {UNALLOCATED, UNALLOCATED_NO_WEIGHT}
COST_COLUMNS = ("EffectiveCost", "ListCost", "BilledCost")


def load_costs(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "x_Team" not in df.columns:
        if "Tags" not in df.columns:
            raise SystemExit("Need either an x_Team column or a FOCUS Tags column.")
        df = flatten(df)
    return df


def load_weights(path: str | None) -> pd.DataFrame:
    """
    Columns: ResourceId, Team, WeightShare (0.0 to 1.0, sums to 1 per resource)
    Optional: BillingPeriodStart, if your weights change month to month
    (they should, if they come from real telemetry).
    ResourceId can be the full ID or just the resource name.
    """
    if not path:
        return pd.DataFrame(columns=["ResourceId", "Team", "WeightShare"])
    w = pd.read_csv(path)
    missing = {"ResourceId", "Team", "WeightShare"} - set(w.columns)
    if missing:
        raise SystemExit(f"Weights file is missing columns: {sorted(missing)}")
    return w


def _is_true(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.lower().isin({"true", "yes", "1"})


def classify(costs: pd.DataFrame) -> pd.Series:
    has_team = costs["x_Team"].notna() & (costs["x_Team"].astype(str).str.len() > 0)
    central = costs.get("x_Allocation", pd.Series(index=costs.index, dtype=object)).fillna("").eq("central")
    shared = _is_true(costs.get("x_Shared", pd.Series(index=costs.index, dtype=object)))

    kind = pd.Series("unallocated", index=costs.index)
    kind[shared] = "shared"
    kind[central] = "central"
    kind[has_team] = "direct"  # an explicit team tag always wins
    return kind


def allocate(
    costs: pd.DataFrame,
    weights: pd.DataFrame,
    cost_column: str = "EffectiveCost",
    fallback: str = "bucket",
    by: list[str] | None = None,
) -> pd.DataFrame:
    """Returns one row per allocated slice with Team, AllocatedCost, and any `by` columns."""
    by = by or []
    if cost_column not in costs.columns:
        raise SystemExit(f"Cost column {cost_column} not found in export.")

    df = costs.copy()
    df["_kind"] = classify(df)
    df["_cost"] = df[cost_column].fillna(0.0)
    keep = ["_cost", "ServiceCategory", "BillingPeriodStart", "ResourceId", "ResourceName"]
    keep = [c for c in keep if c in df.columns]

    parts = []

    direct = df[df["_kind"] == "direct"].copy()
    direct["Team"] = direct["x_Team"]
    parts.append(direct)

    central = df[df["_kind"] == "central"].copy()
    central["Team"] = CENTRAL
    parts.append(central)

    unalloc = df[df["_kind"] == "unallocated"].copy()
    unalloc["Team"] = UNALLOCATED
    parts.append(unalloc)

    shared = df[df["_kind"] == "shared"][keep].copy()
    if not shared.empty:
        w = weights.copy()
        # Let the weights file use either full resource IDs or short names
        id_keys = set(w["ResourceId"])
        shared["_wkey"] = shared["ResourceId"].where(
            shared["ResourceId"].isin(id_keys), shared.get("ResourceName", shared["ResourceId"])
        )
        w = w.rename(columns={"ResourceId": "_wkey"})
        on = ["_wkey"]
        if "BillingPeriodStart" in w.columns and "BillingPeriodStart" in shared.columns:
            on.append("BillingPeriodStart")
        merged = shared.merge(w, on=on, how="left")

        weighted = merged[merged["WeightShare"].notna()].copy()
        weighted["_cost"] = weighted["_cost"] * weighted["WeightShare"]
        parts.append(weighted)

        no_weight = merged[merged["WeightShare"].isna()].drop(columns=["Team", "WeightShare"], errors="ignore")
        if fallback == "even":
            teams = sorted(df.loc[df["_kind"] == "direct", "x_Team"].dropna().unique())
            if teams:
                spread = no_weight.loc[no_weight.index.repeat(len(teams))].copy()
                spread["Team"] = teams * len(no_weight)
                spread["_cost"] = spread["_cost"] / len(teams)
                parts.append(spread)
            else:
                no_weight["Team"] = UNALLOCATED_NO_WEIGHT
                parts.append(no_weight)
        else:
            no_weight["Team"] = UNALLOCATED_NO_WEIGHT
            parts.append(no_weight)

    combined = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    combined = combined.rename(columns={"_cost": "AllocatedCost"})
    group = ["Team"] + by
    return (
        combined.groupby(group, as_index=False)["AllocatedCost"].sum()
        .sort_values("AllocatedCost", ascending=False)
        .reset_index(drop=True)
    )


def allocation_coverage(report: pd.DataFrame) -> float:
    """
    Share of total cost that is either attributed to a team or deliberately
    held centrally by policy. Accidental unallocated cost is what counts
    against you; a documented central bucket does not.
    """
    total = report["AllocatedCost"].sum()
    if not total:
        return 0.0
    unallocated = report.loc[report["Team"].isin(UNALLOCATED_BUCKETS), "AllocatedCost"].sum()
    return 1 - (unallocated / total)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", help="FOCUS export (raw with Tags, or already flattened)")
    p.add_argument("--weights", help="CSV of usage weights for shared resources")
    p.add_argument("--cost-column", choices=COST_COLUMNS, default="EffectiveCost")
    p.add_argument("--fallback", choices=("bucket", "even"), default="bucket",
                   help="what to do with shared resources that have no weighting")
    p.add_argument("--period", help="only allocate one BillingPeriodStart (YYYY-MM-DD)")
    p.add_argument("--by", default="", help="extra breakdown columns, e.g. ServiceCategory")
    p.add_argument("--out", help="write the report to CSV")
    args = p.parse_args()

    costs = load_costs(args.input)
    if args.period:
        costs = costs[costs["BillingPeriodStart"] == args.period]
        if costs.empty:
            raise SystemExit(f"No rows for period {args.period}")
    weights = load_weights(args.weights)
    by = [c for c in args.by.split(",") if c]

    report = allocate(costs, weights, args.cost_column, args.fallback, by)
    coverage = allocation_coverage(report)

    pd.set_option("display.float_format", lambda v: f"{v:,.2f}")
    print(report.to_string(index=False))
    print(f"\nCost column:          {args.cost_column}")
    print(f"Total allocated:      {report['AllocatedCost'].sum():,.2f}")
    print(f"Allocation coverage:  {coverage:.1%}")
    if args.out:
        report.to_csv(args.out, index=False)
        print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
