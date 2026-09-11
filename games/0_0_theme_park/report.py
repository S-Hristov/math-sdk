"""Theme Park lookup/report helpers.

Reports read compact lookup artifacts rather than materializing multi-gigabyte
JSONL books. The segmented lookup already contains criteria plus base/free win
splits for every book id.
"""

from __future__ import annotations

import json
import os
from typing import Any

from math_targets import MODE_COSTS, TARGET_BASE_HIT_RATE, TARGET_RTP, TARGET_RTP_SHARES


def _load_lookup(path: str) -> list[dict[str, int]]:
    rows: list[dict[str, int]] = []
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            if not line.strip():
                continue
            book_id, weight, payout = line.strip().split(',')
            rows.append({'id': int(book_id), 'weight': int(weight), 'payout': int(payout)})
    return rows


def _load_segmented(path: str) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    with open(path, 'r', encoding='utf-8') as file:
        for line in file:
            if not line.strip():
                continue
            book_id, criteria, base_win, free_win = line.strip().split(',')
            rows[int(book_id)] = {
                'criteria': '' if criteria == '0' else criteria,
                'base_win': float(base_win),
                'free_win': float(free_win),
            }
    return rows


def _load_tail_books(path: str, count: int) -> list[dict[str, Any]]:
    """Read only the final JSONL rows, where post-build injected books live."""
    if count <= 0:
        return []
    with open(path, 'rb') as file:
        file.seek(0, os.SEEK_END)
        position = file.tell()
        chunks: list[bytes] = []
        newline_count = 0
        while position > 0 and newline_count <= count:
            block_size = min(64 * 1024, position)
            position -= block_size
            file.seek(position)
            chunk = file.read(block_size)
            chunks.append(chunk)
            newline_count += chunk.count(b'\n')
    lines = b''.join(reversed(chunks)).splitlines()
    return [json.loads(line) for line in lines[-count:] if line.strip()]


def _weighted_quantiles(rows: list[dict[str, int]], quantiles: list[float]) -> dict[str, float]:
    total_weight = sum(row['weight'] for row in rows) or 1
    ordered = sorted(rows, key=lambda row: row['payout'])
    results: dict[str, float] = {}
    cumulative = 0
    qi = 0
    for row in ordered:
        cumulative += row['weight']
        while qi < len(quantiles) and cumulative / total_weight >= quantiles[qi]:
            results[f'p{quantiles[qi] * 100:g}'] = row['payout'] / 100
            qi += 1
        if qi >= len(quantiles):
            break
    fallback = ordered[-1]['payout'] / 100 if ordered else 0.0
    for quantile in quantiles[qi:]:
        results[f'p{quantile * 100:g}'] = fallback
    return results


def _criteria_stats(rows: list[dict[str, int]], segmented: dict[int, dict[str, Any]]) -> dict[str, Any]:
    total_weight = sum(row['weight'] for row in rows) or 1
    groups: dict[str, list[dict[str, int]]] = {}
    for row in rows:
        criteria = segmented[row['id']]['criteria']
        groups.setdefault(criteria, []).append(row)

    stats: dict[str, Any] = {}
    for criteria, group in sorted(groups.items()):
        label = criteria or 'none'
        stats[label] = {
            'count': len(group),
            'weighted_prob': round(sum(row['weight'] for row in group) / total_weight, 6),
            'avg_payout_raw': round(
                sum((row['payout'] / 100) * row['weight'] for row in group)
                / max(sum(row['weight'] for row in group), 1),
                3,
            ),
            'max_payout': max(row['payout'] for row in group) / 100,
        }
    return stats


def build_report(library_path: str, mode_costs: dict[str, float]) -> dict[str, Any]:
    books_path = os.path.join(library_path, 'books')
    publish_path = os.path.join(library_path, 'publish_files')
    segmented_path = os.path.join(library_path, 'lookup_tables')
    report: dict[str, Any] = {'modes': {}, 'summary': {}}
    quantiles = [0.50, 0.75, 0.90, 0.95, 0.99, 0.999]

    for mode, cost in mode_costs.items():
        rows = _load_lookup(os.path.join(publish_path, f'lookUpTable_{mode}_0.csv'))
        segmented = _load_segmented(os.path.join(segmented_path, f'lookUpTableSegmented_{mode}.csv'))
        row_ids = {row['id'] for row in rows}
        missing_ids = row_ids - set(segmented)
        for book in _load_tail_books(os.path.join(books_path, f'books_{mode}.jsonl'), len(missing_ids)):
            book_id = int(book['id'])
            if book_id in missing_ids:
                segmented[book_id] = {
                    'criteria': str(book.get('criteria') or ''),
                    'base_win': float(book.get('baseGameWins', 0.0)),
                    'free_win': float(book.get('freeGameWins', 0.0)),
                }
        if row_ids - set(segmented):
            raise ValueError(f'{mode}: could not resolve injected lookup ids')

        total_weight = sum(row['weight'] for row in rows) or 1
        weighted_avg_x = sum(row['payout'] / 100 * row['weight'] for row in rows) / total_weight
        base_rtp = sum(segmented[row['id']]['base_win'] * row['weight'] for row in rows) / total_weight / cost
        freespin_rtp = sum(
            segmented[row['id']]['free_win'] * row['weight']
            for row in rows
            if segmented[row['id']]['criteria'] in {'roller', 'coaster'}
        ) / total_weight / cost
        bonus_rtp = sum(
            segmented[row['id']]['free_win'] * row['weight']
            for row in rows
            if segmented[row['id']]['criteria'] == 'duck'
        ) / total_weight / cost
        feature_rtp = freespin_rtp + bonus_rtp

        criteria_weight = lambda names: sum(  # noqa: E731 - concise weighted predicate
            row['weight'] for row in rows if segmented[row['id']]['criteria'] in names
        ) / total_weight

        report['modes'][mode] = {
            'rows': len(rows),
            'lookup_total_weight': total_weight,
            'avg_x': weighted_avg_x,
            'rtp': weighted_avg_x / cost,
            'base_rtp_contribution': base_rtp,
            'free_rtp_contribution': feature_rtp,
            'freespin_rtp_contribution': freespin_rtp,
            'bonus_rtp_contribution': bonus_rtp,
            'hit_rate': sum(row['weight'] for row in rows if row['payout'] > 0) / total_weight,
            'freespin_trigger_rate': criteria_weight({'roller', 'coaster'}),
            'feature_trigger_rate': criteria_weight({'duck', 'roller', 'coaster'}),
            'duck_bonus_rate': criteria_weight({'duck'}),
            'duck_collect_rate': criteria_weight({'duckcollect'}),
            'max_x_observed': max((row['payout'] for row in rows), default=0) / 100,
            'quantiles': _weighted_quantiles(rows, quantiles),
            'criteria': _criteria_stats(rows, segmented),
        }

    base = report['modes'].get('BASE', {})
    base_rtp = base.get('base_rtp_contribution', 0.0)
    freespin_rtp = base.get('freespin_rtp_contribution', 0.0)
    bonus_rtp = base.get('bonus_rtp_contribution', 0.0)
    total_rtp = base.get('rtp', 0.0) or 1.0
    report['summary'] = {
        'target_rtp': TARGET_RTP,
        'target_hit_rate': TARGET_BASE_HIT_RATE,
        'mode_costs': MODE_COSTS,
        'base_rtp_delta': base.get('rtp', 0.0) - TARGET_RTP,
        'base_hit_rate_delta': base.get('hit_rate', 0.0) - TARGET_BASE_HIT_RATE,
        'base_rtp_split': {
            'target_shares': TARGET_RTP_SHARES,
            'base_share': base_rtp / total_rtp,
            'freespin_share': freespin_rtp / total_rtp,
            'bonus_share': bonus_rtp / total_rtp,
            'feature_share': (freespin_rtp + bonus_rtp) / total_rtp,
        },
    }
    return report


def write_report(library_path: str, mode_costs: dict[str, float]) -> str:
    report = build_report(library_path, mode_costs)
    output_path = os.path.join(library_path, 'configs', 'simulation_report.json')
    with open(output_path, 'w', encoding='utf-8') as file:
        json.dump(report, file, indent=2)
        file.write('\n')
    return output_path
