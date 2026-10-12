"""REV10 cost-anchored design proposal; no factual or exploration data is read."""

import ast
import json
from pathlib import Path

import pytest

from research.swl1_rev10_short_v1 import design
from research.swl1_rev10_short_v1.design import (
    CostModel,
    leg_turnover,
    load_cost_model,
    net_spread,
    planning_table,
    proposal,
    rebalance_sessions,
    required_periods,
)

ROOT = Path(__file__).resolve().parents[1]


def test_minimal_effect_comes_from_declared_costs_only():
    cost = load_cost_model(ROOT)
    assert cost == CostModel(3.0, 5.0, 0.0)
    # Both legs fully replaced: 2 legs x (sell 8bp + buy 8bp) = 32bp.
    assert cost.minimal_effect == pytest.approx(0.0032)
    assert CostModel(3.0, 5.0, 10.0).minimal_effect == pytest.approx(0.0052)
    with pytest.raises(ValueError, match="NEGATIVE_COST"):
        CostModel(-1.0, 5.0, 0.0)


def test_module_never_references_seen_results_or_factual_panels():
    source = (ROOT / "research/swl1_rev10_short_v1/design.py").read_text()
    for forbidden in ("swl1_short_horizon_exploration", "returns.npy", "factual_panel", "0.0556"):
        assert forbidden not in source
    imports = [
        node.module or ""
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    ]
    assert not any(name.startswith(("research", "strategies")) for name in imports)


def test_rebalance_cohort_is_non_overlapping_from_activation():
    sessions = [f"2027-01-{d:02d}" for d in range(1, 31)]
    assert rebalance_sessions(sessions, sessions[3]) == [sessions[3], sessions[13], sessions[23]]
    with pytest.raises(ValueError, match="FIRST_SESSION"):
        rebalance_sessions(sessions, "2026-12-31")
    with pytest.raises(ValueError, match="SORTED_UNIQUE"):
        rebalance_sessions(sessions[::-1], sessions[3])


def test_turnover_and_net_spread_charge_each_replaced_name():
    first = (("a", "b", "c", "d", "e"), ("v", "w", "x", "y", "z"))
    second = (("a", "b", "c", "d", "f"), ("v", "w", "x", "y", "z"))
    opening = net_spread(0.01, CostModel(3, 5, 0), None, first)
    assert opening["cost"] == pytest.approx(0.0032) and opening["net"] == pytest.approx(0.0068)
    rolled = net_spread(0.01, CostModel(3, 5, 0), first, second)
    assert (rolled["top_turnover"], rolled["bottom_turnover"]) == (0.2, 0.0)
    assert rolled["cost"] == pytest.approx(0.2 * 0.0016)
    with pytest.raises(ValueError, match="FIVE_DISTINCT"):
        leg_turnover(None, ("a", "a", "b", "c", "d"))


def test_precision_planning_scales_with_dispersion_and_dependence():
    assert required_periods(0.0032, 0.01) == 17
    assert required_periods(0.0032, 0.02) == 65
    assert required_periods(0.0032, 0.02, inflation=2.0) == 129
    assert [row["periods"] for row in planning_table(0.0032, (0.01, 0.03))] == [17, 145]
    with pytest.raises(ValueError, match="INFLATION"):
        required_periods(0.0032, 0.01, inflation=0.5)


def test_proposal_stays_pending_and_reads_no_performance():
    result = proposal(ROOT)
    assert result["status"] == "PROPOSAL_NOT_LOCKED"
    assert result["statistical_design"] == "STATISTICAL_DESIGN_PENDING"
    assert result["performance_inputs_read"] is False
    spec = json.loads((ROOT / "config/research/swl1-rev10-short-v1.json").read_bytes())
    assert spec["statistical_design"] == "STATISTICAL_DESIGN_PENDING"
    assert design.COST_SOURCE == "strategies/etf_quant_v2/config/release.json"
