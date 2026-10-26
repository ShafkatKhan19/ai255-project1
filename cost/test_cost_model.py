"""Tests for the cost model.  python -m pytest -q cost"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import cost_model as cm  # noqa: E402


@pytest.mark.parametrize("gib, expected", [
    (0, 0.0),
    (1, 0.0),                                   # first GiB free
    (2, 0.12),
    (1024, 1023 * 0.12),
    (2048, 1023 * 0.12 + 1024 * 0.11),
    (20480, 1023 * 0.12 + 9216 * 0.11 + 10240 * 0.08),
])
def test_egress_tiers(gib, expected):
    assert cm.egress_cost(gib) == pytest.approx(expected)


def test_ops_are_capped_by_cache():
    a, b = cm.gcs_ops(10**9, vms=1)
    cap = cm.HOURS * 3600 / cm.CACHE_SECONDS
    assert a == cap and b == pytest.approx(cap + 10**9 * cm.FILE_DOWNLOAD_SHARE)


def test_costs_increase_with_traffic():
    totals = [cm.estimate(level)["total"] for level in cm.LEVELS]
    assert totals == sorted(totals) and totals[0] > 0


def test_every_price_has_a_source():
    for name, p in cm.P["prices"].items():
        assert p.get("source", "").startswith("http"), name


def test_low_level_is_mostly_the_ip_address():
    low = cm.estimate(cm.LEVELS[0])
    ip = next(x["cost"] for x in low["lines"] if "IPv4" in x["item"])
    assert ip == pytest.approx(3.65) and ip / low["total"] > 0.9
