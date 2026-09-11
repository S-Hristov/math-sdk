"""Weighted prototype report for Veggie Salad."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any

from math_targets import (
    BASE_TRIGGER_RATE,
    CHANCE_TRIGGER_RATE,
    MODE_COSTS,
    NATURAL_TIER_MIX,
    TARGET_RTP,
)


def _weights(path: str) -> dict[int, int]:
    result = {}
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            book_id, weight, _payout = line.strip().split(",")
            result[int(book_id)] = int(weight)
    return result


def _mode_report(books_path: str, lookup_path: str, cost: float) -> dict[str, Any]:
    weights = _weights(lookup_path)
    total_weight = sum(weights.values()) or 1
    payout_sum = 0
    hit_weight = 0
    trigger_weight = 0
    max_weight = 0
    tier_weights: dict[str, int] = defaultdict(int)
    weighted_tumbles = 0
    multiplier_cap_weight = 0
    rows = 0

    with open(books_path, "r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            book = json.loads(line)
            rows += 1
            weight = weights.get(int(book["id"]), 0)
            payout = int(book["payoutMultiplier"])
            payout_sum += payout * weight
            hit_weight += weight if payout > 0 else 0
            max_weight += weight if payout == 2_500_000 else 0
            tier = None
            tumble_count = 0
            capped_multiplier = False
            for event in book.get("events", []):
                if event.get("type") == "freeSpinTrigger":
                    trigger_weight += weight
                    tier = str(event.get("tier"))
                elif event.get("type") == "mysterySelect":
                    tier = str(event.get("tier"))
                elif event.get("type") == "tumbleRemove":
                    tumble_count += 1
                elif event.get("type") == "clusterWin":
                    capped_multiplier = capped_multiplier or any(
                        int(win.get("appliedMultiplier", 1)) == 256
                        for win in event.get("wins", [])
                    )
            if tier:
                tier_weights[tier] += weight
            weighted_tumbles += tumble_count * weight
            multiplier_cap_weight += weight if capped_multiplier else 0

    mean_x = payout_sum / total_weight / 100
    return {
        "rows": rows,
        "avg_x": mean_x,
        "rtp": mean_x / cost,
        "hit_rate": hit_weight / total_weight,
        "trigger_rate": trigger_weight / total_weight,
        "tier_mix": {tier: weight / max(sum(tier_weights.values()), 1) for tier, weight in tier_weights.items()},
        "average_tumbles": weighted_tumbles / total_weight,
        "multiplier_cap_rate": multiplier_cap_weight / total_weight,
        "max_win_rate": max_weight / total_weight,
    }


def write_report(library_path: str) -> str:
    report: dict[str, Any] = {
        "target_rtp": TARGET_RTP,
        "assumptions": {
            "standard_trigger_rate": BASE_TRIGGER_RATE,
            "extra_chance_trigger_rate": CHANCE_TRIGGER_RATE,
            "natural_tier_mix": NATURAL_TIER_MIX,
            "feature_spin_cost": MODE_COSTS["FEATURE"],
        },
        "modes": {},
    }
    for mode, cost in MODE_COSTS.items():
        report["modes"][mode] = _mode_report(
            os.path.join(library_path, "books", f"books_{mode}.jsonl"),
            os.path.join(library_path, "publish_files", f"lookUpTable_{mode}_0.csv"),
            cost,
        )
    output = os.path.join(library_path, "configs", "simulation_report.json")
    with open(output, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
    return output
