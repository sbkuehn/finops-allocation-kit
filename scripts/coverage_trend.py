"""
coverage_trend.py

Allocation coverage month over month. The current value matters less than
the direction. A model sitting flat at 70% for two quarters is a bigger
governance problem than one at 55% that climbs every month.

Prints a table, optionally writes a CSV, and optionally draws a PNG.

Usage:
    python scripts/coverage_trend.py examples/focus_export_sample.csv \
        --weights examples/shared_resource_weights.csv \
        --png coverage_trend.png
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from allocate import (  # noqa: E402
    COST_COLUMNS, UNALLOCATED_BUCKETS, allocate, allocation_coverage, load_costs, load_weights,
)


def trend(costs: pd.DataFrame, weights: pd.DataFrame, cost_column: str, fallback: str) -> pd.DataFrame:
    rows = []
    for period, chunk in costs.groupby("BillingPeriodStart", sort=True):
        report = allocate(chunk, weights, cost_column, fallback)
        total = report["AllocatedCost"].sum()
        unalloc = report.loc[report["Team"].isin(UNALLOCATED_BUCKETS), "AllocatedCost"].sum()
        rows.append({
            "BillingPeriodStart": period,
            "TotalCost": round(total, 2),
            "UnallocatedCost": round(unalloc, 2),
            "Coverage": round(allocation_coverage(report), 4),
        })
    out = pd.DataFrame(rows)
    out["CoverageChange"] = out["Coverage"].diff().round(4)
    return out


def draw(df: pd.DataFrame, path: str, target: float | None) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = pd.to_datetime(df["BillingPeriodStart"]).dt.strftime("%b %Y")
    pct = df["Coverage"] * 100

    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    ax.plot(labels, pct, color="#2a78d6", linewidth=2, marker="o", markersize=7,
            markeredgecolor="#fcfcfb", markeredgewidth=2)
    if target is not None:
        ax.axhline(target * 100, color="#8a8984", linewidth=1, linestyle=(0, (4, 4)))
        ax.text(len(df) - 1, target * 100 + 1, f"target {target:.0%}", ha="right", va="bottom",
                color="#52514e", fontsize=9)
    for i in (0, len(df) - 1):
        ax.annotate(f"{pct.iloc[i]:.0f}%", (i, pct.iloc[i]), textcoords="offset points",
                    xytext=(0, -16), ha="center", color="#0b0b0b", fontsize=10)
    ax.set_ylim(max(0, pct.min() - 15), 100)
    ax.set_ylabel("Allocation coverage (%)", color="#52514e")
    ax.set_title("Allocation coverage by month", loc="left", color="#0b0b0b", fontsize=13)
    ax.grid(axis="y", color="#e6e5e0", linewidth=0.8)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.tick_params(colors="#52514e", length=0)
    fig.tight_layout()
    fig.savefig(path, facecolor=fig.get_facecolor())
    print(f"Chart written to {path}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input")
    p.add_argument("--weights")
    p.add_argument("--cost-column", choices=COST_COLUMNS, default="EffectiveCost")
    p.add_argument("--fallback", choices=("bucket", "even"), default="bucket")
    p.add_argument("--target", type=float, default=0.9, help="coverage target line, 0 to 1")
    p.add_argument("--csv", help="write the trend table to CSV")
    p.add_argument("--png", help="draw the trend to a PNG")
    args = p.parse_args()

    costs = load_costs(args.input)
    weights = load_weights(args.weights)
    df = trend(costs, weights, args.cost_column, args.fallback)

    show = df.copy()
    show["Coverage"] = (show["Coverage"] * 100).map("{:.1f}%".format)
    show["CoverageChange"] = (show["CoverageChange"] * 100).map(lambda v: "" if pd.isna(v) else f"{v:+.1f} pts")
    print(show.to_string(index=False))

    flat = df["CoverageChange"].dropna().tail(3)
    if len(flat) == 3 and flat.abs().max() < 0.005:
        print("\nHeads up: coverage has been flat for three months. Who owns the unallocated bucket?")

    if args.csv:
        df.to_csv(args.csv, index=False)
    if args.png:
        draw(df, args.png, args.target)


if __name__ == "__main__":
    main()
