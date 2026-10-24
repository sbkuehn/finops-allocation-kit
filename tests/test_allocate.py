import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from allocate import allocate, allocation_coverage  # noqa: E402
from flatten_tags import flatten  # noqa: E402
from validate_weights import check  # noqa: E402


def make(rows):
    df = pd.DataFrame(rows)
    df["Tags"] = df["Tags"].map(json.dumps)
    df["ServiceCategory"] = "Compute"
    df["BillingPeriodStart"] = "2026-09-01"
    df["ResourceName"] = df["ResourceId"]
    return flatten(df)


@pytest.fixture
def costs():
    return make([
        {"ResourceId": "a", "EffectiveCost": 100.0, "Tags": {"team": "alpha"}},
        {"ResourceId": "b", "EffectiveCost": 50.0, "Tags": {"Team": "BETA"}},
        {"ResourceId": "pool", "EffectiveCost": 200.0, "Tags": {"shared": "true"}},
        {"ResourceId": "gw", "EffectiveCost": 40.0, "Tags": {"shared": "true"}},
        {"ResourceId": "support", "EffectiveCost": 60.0, "Tags": {"shared": "true", "allocation": "central"}},
        {"ResourceId": "orphan", "EffectiveCost": 50.0, "Tags": {}},
    ])


@pytest.fixture
def weights():
    return pd.DataFrame({
        "ResourceId": ["pool", "pool"],
        "Team": ["alpha", "beta"],
        "WeightShare": [0.75, 0.25],
    })


def by_team(report):
    return dict(zip(report["Team"], report["AllocatedCost"].round(2)))


def test_money_is_conserved(costs, weights):
    report = allocate(costs, weights)
    assert report["AllocatedCost"].sum() == pytest.approx(costs["EffectiveCost"].sum())


def test_direct_weighted_and_buckets(costs, weights):
    t = by_team(allocate(costs, weights))
    assert t["alpha"] == 100 + 150
    assert t["beta"] == 50 + 50  # casing normalized, then weighted share
    assert t["CENTRAL"] == 60
    assert t["UNALLOCATED_NO_WEIGHT"] == 40
    assert t["UNALLOCATED"] == 50


def test_even_fallback_spreads_unweighted_shared(costs, weights):
    t = by_team(allocate(costs, weights, fallback="even"))
    assert "UNALLOCATED_NO_WEIGHT" not in t
    assert t["alpha"] == 250 + 20
    assert t["beta"] == 100 + 20


def test_coverage_counts_central_as_allocated(costs, weights):
    report = allocate(costs, weights)
    assert allocation_coverage(report) == pytest.approx(1 - 90 / 500)


def test_validate_catches_bad_sums():
    bad = pd.DataFrame({"ResourceId": ["x", "x"], "Team": ["a", "b"], "WeightShare": [0.6, 0.6]})
    errors, _ = check(bad)
    assert any("sum to 1.2" in e for e in errors)
