"""Write a memory-safe weighted Magnetic report from publish lookup tables."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from math_targets import MODE_COSTS, TARGET_BASE_HIT_RATE, TARGET_RTP

QUANTILES = (0.50, 0.75, 0.90, 0.95, 0.99, 0.999)


def mode_report(path: Path, cost: float) -> dict:
    rows = 0
    total_weight = 0
    weighted_payout = 0
    hit_weight = 0
    payout_weights: dict[int, int] = defaultdict(int)
    max_payout = 0

    with path.open() as file:
        for line in file:
            if not line.strip():
                continue
            _, weight_raw, payout_raw = line.rstrip().split(',')
            weight = int(weight_raw)
            payout = int(payout_raw)
            rows += 1
            total_weight += weight
            weighted_payout += payout * weight
            payout_weights[payout] += weight
            if payout > 0:
                hit_weight += weight
            if weight > 0:
                max_payout = max(max_payout, payout)

    total_weight = max(total_weight, 1)
    avg_x = weighted_payout / total_weight / 100
    quantiles = {}
    cumulative = 0
    targets = [(quantile, total_weight * quantile) for quantile in QUANTILES]
    target_index = 0
    for payout, weight in sorted(payout_weights.items()):
        cumulative += weight
        while target_index < len(targets) and cumulative >= targets[target_index][1]:
            quantile = targets[target_index][0]
            quantiles[f'p{quantile * 100:g}'] = payout / 100
            target_index += 1

    return {
        'rows': rows,
        'total_weight': total_weight,
        'avg_x': avg_x,
        'rtp': avg_x / cost,
        'hit_rate': hit_weight / total_weight,
        'max_x_observed': max_payout / 100,
        'quantiles': quantiles,
    }


def main() -> None:
    library = Path(__file__).with_name('library')
    reports = {
        mode: mode_report(library / 'publish_files' / f'lookUpTable_{mode}_0.csv', cost)
        for mode, cost in MODE_COSTS.items()
    }
    report = {
        'math_contract': {
            'payout_formula': 'paytable_x * exact_compounded_multiplier',
            'mode_payout_scales': False,
            'max_win_x': 20_000,
        },
        'modes': reports,
        'summary': {
            'target_rtp': TARGET_RTP,
            'target_hit_rate': TARGET_BASE_HIT_RATE,
            'mode_costs': MODE_COSTS,
            'base_rtp_delta': reports['BASE']['rtp'] - TARGET_RTP,
            'base_hit_rate_delta': reports['BASE']['hit_rate'] - TARGET_BASE_HIT_RATE,
        },
    }
    output = library / 'configs' / 'simulation_report.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(output)
    for mode, values in reports.items():
        print(mode, f"rtp={values['rtp']:.9f}", f"hit={values['hit_rate']:.6f}", f"max={values['max_x_observed']:.2f}x")


if __name__ == '__main__':
    main()
