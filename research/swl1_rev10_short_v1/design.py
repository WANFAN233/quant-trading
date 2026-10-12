"""Result-free statistical design proposal for REV10 Short-V1.

Nothing here reads factual returns, exploration aggregates or any performance
metric. The minimal meaningful effect comes from the repository's declared
execution costs, never from the seen exploratory RankIC. Locking these values
remains an owner decision; status stays STATISTICAL_DESIGN_PENDING until then.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

COST_SOURCE = "strategies/etf_quant_v2/config/release.json"
HORIZON = 10
LEG_SIZE = 5
# 90% one-sided interval for the mean net spread per rebalance.
ONE_SIDED_Z = 1.2815515655446004
SESSIONS_PER_YEAR = 242


@dataclass(frozen=True)
class CostModel:
    commission_bps: float
    slippage_bps: float
    stamp_duty_bps: float

    def __post_init__(self) -> None:
        if min(self.commission_bps, self.slippage_bps, self.stamp_duty_bps) < 0:
            raise ValueError("NEGATIVE_COST_FORBIDDEN")

    @property
    def replacement_bps(self) -> float:
        """Cost to replace one full leg: sell (with stamp duty) and buy."""
        return 2 * (self.commission_bps + self.slippage_bps) + self.stamp_duty_bps

    def rebalance_cost(self, top_turnover: float, bottom_turnover: float) -> float:
        """Fractional cost of one Top5-Bottom5 rebalance."""
        for value in (top_turnover, bottom_turnover):
            if not 0 <= value <= 1:
                raise ValueError("TURNOVER_OUTSIDE_UNIT_INTERVAL")
        return (top_turnover + bottom_turnover) * self.replacement_bps / 1e4

    @property
    def minimal_effect(self) -> float:
        """Worst-case cost: both legs fully replaced every rebalance."""
        return self.rebalance_cost(1.0, 1.0)


def load_cost_model(repository: Path) -> CostModel:
    release = json.loads((repository / COST_SOURCE).read_bytes())
    return CostModel(
        float(release["commission_bps"]),
        float(release["slippage_bps"]),
        float(release["stamp_duty_bps"]),
    )


def rebalance_sessions(sessions: Sequence[str], first_session: str) -> list[str]:
    """Non-overlapping H10 cohort: every tenth exchange session from activation."""
    if list(sessions) != sorted(set(sessions)):
        raise ValueError("SORTED_UNIQUE_EXCHANGE_SPINE_REQUIRED")
    if first_session not in sessions:
        raise ValueError("FIRST_SESSION_NOT_ON_SPINE")
    return list(sessions[sessions.index(first_session) :: HORIZON])


def leg_turnover(previous: Sequence[str] | None, current: Sequence[str]) -> float:
    if len(current) != LEG_SIZE or len(set(current)) != LEG_SIZE:
        raise ValueError("FIVE_DISTINCT_INDUSTRIES_REQUIRED")
    if previous is None:
        return 1.0
    return len(set(current) - set(previous)) / LEG_SIZE


def net_spread(
    gross: float,
    cost: CostModel,
    previous: tuple[Sequence[str], Sequence[str]] | None,
    current: tuple[Sequence[str], Sequence[str]],
) -> dict[str, float]:
    """Gross raw Top5-Bottom5 H10 return minus the realized rebalance cost."""
    top = leg_turnover(previous[0] if previous else None, current[0])
    bottom = leg_turnover(previous[1] if previous else None, current[1])
    charge = cost.rebalance_cost(top, bottom)
    return {
        "gross": gross,
        "top_turnover": top,
        "bottom_turnover": bottom,
        "cost": charge,
        "net": gross - charge,
    }


def required_periods(effect: float, sd: float, inflation: float = 1.0) -> int:
    """Non-overlapping periods until the one-sided half-width is at most ``effect``.

    Precision planning, not power: a true mean net spread of at least ``effect``
    would then have a lower bound above zero at its point estimate.

    ``sd`` is the per-period net-spread standard deviation; ``inflation`` is a
    variance inflation factor for residual dependence between periods. Both must be
    fixed from sources independent of the seen REV10 results.
    """
    if effect <= 0 or sd <= 0 or inflation < 1:
        raise ValueError("POSITIVE_EFFECT_SD_AND_INFLATION_AT_LEAST_ONE_REQUIRED")
    return math.ceil(inflation * (ONE_SIDED_Z * sd / effect) ** 2)


def planning_table(
    effect: float, sds: Sequence[float], inflation: float = 1.0
) -> list[dict[str, Any]]:
    periods_per_year = SESSIONS_PER_YEAR / HORIZON
    rows = []
    for sd in sds:
        periods = required_periods(effect, sd, inflation)
        rows.append(
            {
                "period_sd": sd,
                "periods": periods,
                "years": round(periods / periods_per_year, 2),
            }
        )
    return rows


def proposal(repository: Path) -> dict[str, Any]:
    cost = load_cost_model(repository)
    effect = cost.minimal_effect
    return {
        "status": "PROPOSAL_NOT_LOCKED",
        "statistical_design": "STATISTICAL_DESIGN_PENDING",
        "cost_source": COST_SOURCE,
        "cost_model": {
            "commission_bps": cost.commission_bps,
            "slippage_bps": cost.slippage_bps,
            "stamp_duty_bps": cost.stamp_duty_bps,
        },
        "rebalance": "NON_OVERLAPPING_EVERY_10_SESSIONS_FROM_ACTIVATION",
        "co_endpoint": "MEAN_NET_TOP5_BOTTOM5_H10_SPREAD_PER_REBALANCE",
        "minimal_meaningful_effect": effect,
        "minimal_effect_basis": "WORST_CASE_FULL_REPLACEMENT_OF_BOTH_LEGS",
        "precision_target": "90% ONE_SIDED HALF_WIDTH <= MINIMAL_MEANINGFUL_EFFECT",
        "success_rule": "90% ONE_SIDED LOWER BOUND OF MEAN NET SPREAD > 0",
        "planning_table": planning_table(effect, (0.01, 0.02, 0.03, 0.04)),
        "performance_inputs_read": False,
    }


if __name__ == "__main__":
    print(json.dumps(proposal(Path(__file__).resolve().parents[2]), indent=2))
