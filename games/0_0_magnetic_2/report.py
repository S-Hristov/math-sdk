"""Magnetic book/report helpers."""

from __future__ import annotations

import json
import os
from typing import Any

from math_targets import MODE_COSTS, MYSTERY_MIX, MYSTERY_TIER_MEANS, TARGET_BASE_HIT_RATE, TARGET_RTP


def _load_lookup(path: str) -> dict[int, int]:
    weights: dict[int, int] = {}
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            if not line.strip():
                continue
            book_id, weight, _payout = line.strip().split(',')
            weights[int(book_id)] = int(weight)
    return weights


def _event_count(book: dict[str, Any], event_type: str) -> int:
    return sum(1 for event in book['events'] if event.get('type') == event_type)


def _weighted_quantiles(payout_weights: dict[int, int], total_weight: int, quantiles: list[float]) -> dict[str, float]:
    results: dict[str, float] = {}
    cumulative = 0
    qi = 0
    for payout, weight in sorted(payout_weights.items()):
        cumulative += weight
        while qi < len(quantiles) and cumulative / max(total_weight, 1) >= quantiles[qi]:
            results[f'p{int(quantiles[qi] * 100)}'] = payout / 100
            qi += 1
        if qi >= len(quantiles):
            break
    for quantile in quantiles[qi:]:
        results[f'p{int(quantile * 100)}'] = max(payout_weights, default=0) / 100
    return results


def _super_profile_stats(profile_data: dict[str, dict[str, float]]) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    total = sum(int(values['count']) for values in profile_data.values()) or 1
    for profile, values in sorted(profile_data.items()):
        count = int(values['count'])
        stats[profile] = {
            'count': count,
            'fraction': round(count / total, 4),
            'avg_payout': round(values['payout_sum'] / max(count, 1), 2),
            'hit_rate': round(values['hits'] / max(count, 1), 4),
            'max_payout': values['max_payout'],
        }
    return stats


def _mystery_tier_stats(tiers: dict[str, dict[str, float]], total_weight: int) -> dict[str, Any]:
    """What the Mystery buy actually paid per awarded bonus.

    The reveal advertises 70/25/5 and promises the real bonus behind each icon,
    so the weighted share and the tier's own mean both belong in the report.
    """
    out: dict[str, Any] = {}
    for tier, values in tiers.items():
        weight = values['weight'] or 1
        out[tier] = {
            'weighted_share': round(values['weight'] / max(total_weight, 1), 5),
            'target_share': MYSTERY_MIX.get(tier, 0.0),
            'avg_x': round(values['payout'] / weight, 2),
            'target_avg_x': round(MYSTERY_TIER_MEANS.get(tier, 0.0), 2),
            'books': int(values['books']),
        }
    return out


def _stream_mode_stats(path: str, weights: dict[int, int], include_profiles: bool) -> dict[str, Any]:
    rows = 0
    weighted_payout = 0.0
    hit_weight = 0
    trigger_weight = 0
    max_payout = 0
    payout_weights: dict[int, int] = {}
    profiles: dict[str, dict[str, float]] = {}
    tiers: dict[str, dict[str, float]] = {}
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            if not line.strip():
                continue
            row = json.loads(line)
            rows += 1
            payout = int(row['payoutMultiplier'])
            weight = weights.get(int(row['id']), 0)
            weighted_payout += (payout / 100) * weight
            if payout > 0:
                hit_weight += weight
            if _event_count(row, 'freeSpinTrigger') > 0:
                trigger_weight += weight
            max_payout = max(max_payout, payout)
            payout_weights[payout] = payout_weights.get(payout, 0) + weight
            for event in row.get('events', []):
                if event.get('type') == 'mysteryBonusReveal':
                    values = tiers.setdefault(str(event.get('mode', '')), {'weight': 0.0, 'payout': 0.0, 'books': 0.0})
                    values['weight'] += weight
                    values['payout'] += (payout / 100) * weight
                    values['books'] += 1
                    break
            if include_profiles:
                profile = 'unknown'
                for event in row.get('events', []):
                    if event.get('type') == 'magnetActivated':
                        profile = str(event.get('symbol', 'unknown'))
                        break
                values = profiles.setdefault(profile, {'count': 0, 'payout_sum': 0.0, 'hits': 0, 'max_payout': 0.0})
                values['count'] += 1
                values['payout_sum'] += payout / 100
                values['hits'] += int(payout > 0)
                values['max_payout'] = max(values['max_payout'], payout / 100)
    return {
        'rows': rows,
        'weighted_payout': weighted_payout,
        'hit_weight': hit_weight,
        'trigger_weight': trigger_weight,
        'max_payout': max_payout,
        'payout_weights': payout_weights,
        'profiles': profiles,
        'tiers': tiers,
    }


def build_report(library_path: str, mode_costs: dict[str, float]) -> dict[str, Any]:
    books_path = os.path.join(library_path, 'books')
    publish_path = os.path.join(library_path, 'publish_files')
    report: dict[str, Any] = {'modes': {}, 'summary': {}}
    quantiles = [0.50, 0.75, 0.90, 0.95, 0.99, 0.999]

    for mode, cost in mode_costs.items():
        lookup_weights = _load_lookup(os.path.join(publish_path, f'lookUpTable_{mode}_0.csv'))
        total_weight = sum(lookup_weights.values()) or 1
        stats = _stream_mode_stats(os.path.join(books_path, f'books_{mode}.jsonl'), lookup_weights, mode == 'SUPER')
        weighted_avg_x = stats['weighted_payout'] / total_weight
        hit_rate = stats['hit_weight'] / total_weight
        trigger_rate = stats['trigger_weight'] / total_weight
        mode_report: dict[str, Any] = {
            'rows': stats['rows'],
            'avg_x': weighted_avg_x if stats['rows'] else 0.0,
            'rtp': (weighted_avg_x / cost) if stats['rows'] else 0.0,
            'hit_rate': hit_rate if stats['rows'] else 0.0,
            'trigger_rate': trigger_rate if stats['rows'] else 0.0,
            'max_x_observed': stats['max_payout'] / 100 if stats['rows'] else 0.0,
            'quantiles': _weighted_quantiles(stats['payout_weights'], total_weight, quantiles) if stats['rows'] else {},
        }
        if mode == 'SUPER':
            mode_report['profile_breakdown'] = _super_profile_stats(stats['profiles'])
        if stats['tiers']:
            mode_report['mystery_tier_breakdown'] = _mystery_tier_stats(stats['tiers'], total_weight)
        report['modes'][mode] = mode_report

    base = report['modes'].get('BASE', {})
    report['summary'] = {
        'target_rtp': TARGET_RTP,
        'target_hit_rate': TARGET_BASE_HIT_RATE,
        'mode_costs': MODE_COSTS,
        'base_rtp_delta': base.get('rtp', 0.0) - TARGET_RTP,
        'base_hit_rate_delta': base.get('hit_rate', 0.0) - TARGET_BASE_HIT_RATE,
    }
    return report


def write_report(library_path: str, mode_costs: dict[str, float]) -> str:
    report = build_report(library_path, mode_costs)
    output_path = os.path.join(library_path, 'configs', 'simulation_report.json')
    with open(output_path, 'w', encoding='utf-8') as file:
        json.dump(report, file, indent=2)
    return output_path
