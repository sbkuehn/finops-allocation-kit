"""
generate_sample_data.py

Builds a synthetic, FOCUS-shaped cost export so you can run every script in
this kit without touching real billing data. Six months of charges across a
handful of teams, a shared Kubernetes node pool, a shared GPU inference pool,
enterprise support, and a pile of untagged stragglers that slowly get cleaned
up month over month (so the coverage trend has something to show).

Usage:
    python scripts/generate_sample_data.py --out examples/focus_export_sample.csv
"""

import argparse
import json
import random
from datetime import date

import pandas as pd

TEAMS = ["payments", "search", "data-platform", "mobile", "ml-research"]

# (ResourceId suffix, ServiceCategory, base monthly cost, owner or None)
DIRECT_RESOURCES = [
    ("vm-payments-api-01", "Compute", 2100, "payments"),
    ("sql-payments-ledger", "Databases", 3400, "payments"),
    ("vm-search-indexer-01", "Compute", 1800, "search"),
    ("st-search-snapshots", "Storage", 650, "search"),
    ("adf-data-platform-etl", "Analytics", 2900, "data-platform"),
    ("st-data-lake-raw", "Storage", 1700, "data-platform"),
    ("app-mobile-backend", "Compute", 1250, "mobile"),
    ("cdn-mobile-assets", "Networking", 480, "mobile"),
    ("aml-ml-research-ws", "AI and Machine Learning", 2600, "ml-research"),
]

# Shared resources carry shared=true and no team. Weights come from telemetry.
SHARED_RESOURCES = [
    ("aks-shared-nodepool-01", "Compute", 9200),
    ("gpu-shared-inference-pool", "AI and Machine Learning", 14800),
    ("aoai-shared-gateway", "AI and Machine Learning", 6100),
]

# Costs your written policy keeps centralized (see docs/shared-cost-policy-template.md)
CENTRAL_RESOURCES = [
    ("support-enterprise-plan", "Other", 5000),
    ("defender-for-cloud", "Security", 2300),
]

# Untagged stragglers. Each month, some of them get fixed.
UNTAGGED = [
    ("vm-legacy-jumpbox", "Compute", 420, "payments"),
    ("st-old-backups-2023", "Storage", 1300, "data-platform"),
    ("vm-poc-do-not-delete", "Compute", 950, "search"),
    ("pip-orphaned-03", "Networking", 60, "mobile"),
    ("disk-unattached-17", "Storage", 210, "ml-research"),
    ("vm-hackathon-gpu", "Compute", 3100, "ml-research"),
    ("st-temp-export", "Storage", 380, "payments"),
    ("appgw-test-legacy", "Networking", 720, "search"),
]

PROVIDER = "Microsoft"
SUB = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-sbek-demo/providers"


def month_starts(n: int, end: date) -> list[date]:
    months = []
    y, m = end.year, end.month
    for _ in range(n):
        months.append(date(y, m, 1))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(months))


def row(period: date, rid: str, category: str, cost: float, tags: dict, rng: random.Random) -> dict:
    jitter = rng.uniform(0.9, 1.12)
    list_cost = round(cost * jitter, 2)
    # Compute and GPU resources are partly covered by commitments, so their
    # effective (amortized) cost is lower than list. Billed cost reflects
    # what lands on the invoice for this line, which for covered usage is 0
    # because the commitment purchase is billed on its own line.
    covered = category in ("Compute", "AI and Machine Learning")
    effective = round(list_cost * (0.72 if covered else 1.0), 2)
    billed = round(list_cost * (0.35 if covered else 1.0), 2)
    return {
        "BillingPeriodStart": period.isoformat(),
        "ChargePeriodStart": period.isoformat(),
        "ProviderName": PROVIDER,
        "ResourceId": f"{SUB}/{rid}",
        "ResourceName": rid,
        "ServiceCategory": category,
        "ListCost": list_cost,
        "EffectiveCost": effective,
        "BilledCost": billed,
        "Tags": json.dumps(tags),
    }


def build(months: int, end: date, seed: int) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    periods = month_starts(months, end)
    for i, period in enumerate(periods):
        for rid, cat, cost, team in DIRECT_RESOURCES:
            rows.append(row(period, rid, cat, cost, {"team": team, "env": "prod", "costcenter": f"cc-{team}"}, rng))
        for rid, cat, cost in SHARED_RESOURCES:
            # GPU pool spend grows month over month, like it does in real life
            growth = 1 + (0.09 * i if "gpu" in rid or "aoai" in rid else 0.02 * i)
            rows.append(row(period, rid, cat, cost * growth, {"shared": "true", "env": "prod"}, rng))
        for rid, cat, cost in CENTRAL_RESOURCES:
            rows.append(row(period, rid, cat, cost, {"shared": "true", "allocation": "central"}, rng))
        # Tag remediation: one more straggler gets fixed each month
        for j, (rid, cat, cost, owner) in enumerate(UNTAGGED):
            fixed = j < i
            tags = {"team": owner, "env": "dev"} if fixed else {}
            # A couple of resources show the classic casing mess
            if fixed and j % 3 == 0:
                tags = {"Team": owner.upper(), "Env": "Dev"}
            rows.append(row(period, rid, cat, cost, tags, rng))
    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="examples/focus_export_sample.csv")
    p.add_argument("--months", type=int, default=6)
    p.add_argument("--end", default="2026-09-01", help="last billing month (YYYY-MM-DD)")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    df = build(args.months, date.fromisoformat(args.end), args.seed)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
