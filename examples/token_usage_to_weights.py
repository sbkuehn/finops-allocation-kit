"""
token_usage_to_weights.py

Example of turning AI gateway telemetry into allocation weights. Token-based
API spend is metered per request, not per resource, so the billing line for a
shared gateway (Azure OpenAI behind APIM, an LLM proxy, Bedrock behind a
shared account) has no natural owner. The usage logs do.

Input:  a CSV of gateway requests with a caller identity and token counts
        (examples/gateway_token_usage.csv)
Output: weights rows you can append to shared_resource_weights.csv

Weighting by raw token count is the simplest defensible option. If the
gateway fronts models with very different prices, weight by estimated cost
instead (tokens x per-model rate) so a team hammering a cheap model doesn't
subsidize a team calling the expensive one.

Usage:
    python examples/token_usage_to_weights.py examples/gateway_token_usage.csv \
        --resource aoai-shared-gateway
"""

import argparse

import pandas as pd

# Illustrative per-1K-token rates. Swap in your actual negotiated pricing.
RATES_PER_1K = {
    "small-model": {"input": 0.00015, "output": 0.0006},
    "large-model": {"input": 0.0025, "output": 0.01},
}


def weights_from_usage(usage: pd.DataFrame, resource: str, by_cost: bool) -> pd.DataFrame:
    df = usage.copy()
    if by_cost:
        df["Weight"] = df.apply(
            lambda r: r["InputTokens"] / 1000 * RATES_PER_1K[r["Model"]]["input"]
            + r["OutputTokens"] / 1000 * RATES_PER_1K[r["Model"]]["output"],
            axis=1,
        )
        source = "estimated token cost from gateway logs"
    else:
        df["Weight"] = df["InputTokens"] + df["OutputTokens"]
        source = "total tokens from gateway logs"
    per_team = df.groupby("Team")["Weight"].sum()
    shares = (per_team / per_team.sum()).round(4)
    # Push any rounding remainder onto the largest consumer so it sums to exactly 1
    shares.iloc[shares.argmax()] += round(1 - shares.sum(), 4)
    return pd.DataFrame({
        "ResourceId": resource,
        "Team": shares.index,
        "WeightShare": shares.values,
        "Source": source,
    })


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("usage")
    p.add_argument("--resource", required=True)
    p.add_argument("--by-tokens", action="store_true", help="weight by raw tokens instead of estimated cost")
    args = p.parse_args()

    usage = pd.read_csv(args.usage)
    out = weights_from_usage(usage, args.resource, by_cost=not args.by_tokens)
    print(out.to_csv(index=False), end="")


if __name__ == "__main__":
    main()
