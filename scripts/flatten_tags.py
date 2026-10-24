"""
flatten_tags.py

FOCUS puts resource tags in a single JSON column called Tags. That is great
for the spec and annoying for allocation, so this script pulls the keys you
care about out into their own x_ columns (x_ is the FOCUS convention for
custom columns).

It also normalizes the casing mess every estate has. "team", "Team", "TEAM",
and "team_name" can all map to x_Team, and values get lowercased so
"PAYMENTS" and "payments" stop showing up as two different teams.

Usage:
    python scripts/flatten_tags.py examples/focus_export_sample.csv \
        --out examples/focus_export_flat.csv
"""

import argparse
import json

import pandas as pd

# Output column -> tag keys that should feed it (matched case-insensitively)
DEFAULT_KEY_MAP = {
    "x_Team": ["team", "team_name", "owner_team", "squad"],
    "x_CostCenter": ["costcenter", "cost_center", "cost-center", "cc"],
    "x_Environment": ["env", "environment", "stage"],
    "x_Shared": ["shared"],
    "x_Allocation": ["allocation"],
}


def parse_tags(raw) -> dict:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)) or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def flatten(df: pd.DataFrame, key_map: dict[str, list[str]] = DEFAULT_KEY_MAP) -> pd.DataFrame:
    out = df.copy()
    lowered = out["Tags"].map(parse_tags).map(lambda t: {str(k).lower(): v for k, v in t.items()})
    for col, keys in key_map.items():
        def pick(tags: dict, keys=keys):
            for k in keys:
                v = tags.get(k.lower())
                if v not in (None, ""):
                    return str(v).strip().lower()
            return None
        out[col] = lowered.map(pick)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    df = pd.read_csv(args.input)
    if "Tags" not in df.columns:
        raise SystemExit("No Tags column found. Is this a FOCUS export?")
    flat = flatten(df)
    flat.to_csv(args.out, index=False)

    tagged = flat["x_Team"].notna().sum()
    print(f"Wrote {len(flat)} rows to {args.out} ({tagged} rows carry a team tag)")


if __name__ == "__main__":
    main()
