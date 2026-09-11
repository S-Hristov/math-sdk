"""Theme Park lookup weighting (magnetic-style).

Builds weighted lookup tables per mode via an exponential tilt that hits
0.961 * cost exactly, with max-win reachability, a hard tail-probability cap
(<= 0.2% weight above 10,000x) and a feel-bias redistribution inside exact
payout buckets. BASE gets a second constrained entropy pass that locks the
PRD's 52/40/8 RTP contribution shares and natural feature trigger quotas.
"""

from __future__ import annotations

import bisect
import json
import math
import os
from typing import Any

import numpy as np

from math_targets import (
    ANTE_RATES,
    BASE_RATES,
    LOOKUP_SCALE,
    MODE_COSTS,
    MODE_TARGET_MEANS,
    TARGET_BASE_HIT_RATE,
    TARGET_RTP,
    TARGET_RTP_SHARES,
)

TARGET_SCALES = {
    'BASE': 40.0,
    'ANTE': 45.0,
    'FSPIN1': 30.0,
    'FSPIN2': 55.0,
    'DUCK': 80.0,
    'ROLLER': 150.0,
    'COASTER': 300.0,
}

# A 0x outcome stays possible, but rare: the most weight a mode may keep on zero-payout books.
# FSPIN2 is the reason this exists — 39.6% of its books genuinely pay nothing and the weighting
# was selecting them at 40.07%, so two in five 60x purchases returned zero. The pool has plenty of
# other material (12.7% at 10-50x, 5.8% at 50-200x, raw mean 74.9x against a 57.66x target), so the
# weight moves off the zeros with RTP untouched. Modes absent from this table are left alone.
ZERO_WEIGHT_CAP = {
    'FSPIN2': 0.02,
}

# Criteria whose books must keep non-zero selection weight per mode.
ENSURE_CRITERIA = {
    'BASE': ['duckcollect', 'duck', 'roller', 'coaster'],
    'ANTE': ['duckcollect', 'duck', 'roller', 'coaster'],
    'FSPIN1': ['duckcollect'],
    'FSPIN2': ['rollerwild'],
    'DUCK': ['duck'],
    'ROLLER': ['roller'],
    'COASTER': ['coaster'],
}


def _log(message: str) -> None:
    print(f'[weight_lookups] {message}', flush=True)


def _book_feel_score(raw: dict[str, Any]) -> tuple[int, int]:
    """(duck_count, multiplier_wild_count) — used for feel-bias inside payout buckets."""
    duck_count = 0
    multiplier_count = 0
    for event in raw.get('events', []):
        etype = event.get('type')
        if etype in ('duckReveal', 'duckPick'):
            duck_count += 1
        elif etype == 'reveal':
            for reel in event.get('board', []):
                for cell in reel:
                    if cell.get('wild') and int(cell.get('multiplier', 0)) > 1:
                        multiplier_count += 1
    return duck_count, multiplier_count


def _load_books(path: str, mode: str = '') -> list[dict[str, Any]]:
    books = []
    label = mode or os.path.basename(path)
    _log(f'{label}: load books start')
    with open(path, 'r', encoding='utf-8') as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            raw = json.loads(line)
            duck_count, multiplier_count = _book_feel_score(raw)
            books.append(
                {
                    'id': int(raw['id']),
                    'payoutMultiplier': int(raw['payoutMultiplier']),
                    'criteria': str(raw.get('criteria', 'basegame')),
                    'baseWinCents': int(round(float(raw.get('baseGameWins', 0.0)) * 100)),
                    'duckCount': duck_count,
                    'multiplierCount': multiplier_count,
                }
            )
            if line_number % 50000 == 0:
                _log(f'{label}: loaded {line_number:,} books')
    _log(f'{label}: load books done ({len(books):,})')
    return books


def _write_lookup(path: str, rows: list[tuple[int, int, int]]) -> None:
    _log(f'write {os.path.basename(path)} start ({len(rows):,} rows)')
    with open(path, 'w', encoding='utf-8') as file:
        for idx, (book_id, weight, payout_multiplier) in enumerate(rows, start=1):
            file.write(f'{book_id},{weight},{payout_multiplier}\n')
            if idx % 100000 == 0:
                _log(f'write {os.path.basename(path)} {idx:,}/{len(rows):,}')
    _log(f'write {os.path.basename(path)} done')


def _normalize_to_total(weights: list[float], total: int) -> list[int]:
    if not weights:
        return []
    raw_total = sum(weights)
    if raw_total <= 0:
        return [1] * len(weights)
    if total >= len(weights):
        # Every generated book stays reachable. Reserve one unit per row,
        # then distribute the remaining mass using the requested shape.
        remaining_total = total - len(weights)
        scaled = [remaining_total * (weight / raw_total) for weight in weights]
        ints = [1 + int(value) for value in scaled]
        remainder = total - sum(ints)
        order = sorted(
            range(len(weights)),
            key=lambda idx: scaled[idx] - int(scaled[idx]),
            reverse=True,
        )
        for idx in order[: max(0, remainder)]:
            ints[idx] += 1
        return ints
    scaled = [total * (weight / raw_total) for weight in weights]
    ints = [int(value) for value in scaled]
    remainder = total - sum(ints)
    order = sorted(range(len(weights)), key=lambda idx: scaled[idx] - ints[idx], reverse=True)
    for idx in order[: max(0, remainder)]:
        ints[idx] += 1
    return ints


def _solve_alpha(values: list[float], target_mean: float, scale: float) -> float:
    if not values:
        return 0.0
    raw_mean = sum(values) / len(values)
    if target_mean <= 0 or target_mean >= raw_mean:
        return 0.0

    def _mean(alpha: float) -> float:
        weights = [math.exp(-alpha * (value / scale)) for value in values]
        total_weight = sum(weights)
        return sum(value * weight for value, weight in zip(values, weights)) / max(total_weight, 1e-9)

    lo, hi = 0.0, 20.0
    while _mean(hi) > target_mean and hi < 200:
        hi *= 2.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _mean(mid) > target_mean:
            lo = mid
        else:
            hi = mid
    return hi


def _weights_for_target_mean(values: list[float], target_mean: float, scale: float) -> list[float]:
    if not values:
        return []
    raw_mean = sum(values) / len(values)
    if target_mean <= 0 or target_mean >= raw_mean:
        return [1.0 for _ in values]
    if target_mean <= min(values):
        min_value = min(values)
        return [1.0 if value == min_value else 1e-9 for value in values]
    alpha = _solve_alpha(values, target_mean, scale)
    return [math.exp(-alpha * (value / scale)) for value in values]


def _cap_zero_weight(values: list[float], weights: list[float], cap: float) -> list[float]:
    """Hold zero-payout books to at most `cap` of the total weight.

    Applied INSIDE the weight computation, so the mode's existing binary search over the input
    target absorbs the change automatically: capping removes weight from the bottom of the
    distribution, the search compensates, and the mode still lands on its RTP target.
    """
    total = sum(weights)
    if total <= 0:
        return weights
    zero_weight = sum(w for value, w in zip(values, weights) if value == 0)
    if zero_weight <= 0 or zero_weight <= cap * total:
        return weights
    non_zero = total - zero_weight
    wanted_zero = cap * non_zero / (1.0 - cap)
    factor = wanted_zero / zero_weight
    return [w * factor if value == 0 else w for value, w in zip(values, weights)]


def _build_rows_for_target_mean(books: list[dict[str, Any]], target_mean: float, total_weight: int, scale: float, zero_cap: float | None = None) -> list[tuple[int, int, int]]:
    values = [book['payoutMultiplier'] / 100.0 for book in books]
    float_weights = _weights_for_target_mean(values, target_mean, scale)
    if zero_cap is not None:
        float_weights = _cap_zero_weight(values, float_weights, zero_cap)
    int_weights = _normalize_to_total(float_weights, total_weight)
    return [(book['id'], weight, int(book['payoutMultiplier'])) for book, weight in zip(books, int_weights)]


def _ensure_weight_presence(rows: list[tuple[int, int, int]], books: list[dict[str, Any]], criteria: str) -> list[tuple[int, int, int]]:
    if not rows:
        return rows
    wanted_ids = [book['id'] for book in books if book['criteria'] == criteria]
    if not wanted_ids:
        return rows
    weights = {book_id: weight for book_id, weight, _ in rows}
    if any(weights.get(book_id, 0) > 0 for book_id in wanted_ids):
        return rows
    result = list(rows)
    donor_idx = max(
        (idx for idx, (_, weight, payout) in enumerate(result) if payout == 0 and weight > 1),
        key=lambda idx: result[idx][1],
        default=None,
    )
    if donor_idx is None:
        donor_idx = max(
            (idx for idx, (book_id, weight, _) in enumerate(result) if book_id not in wanted_ids and weight > 1),
            key=lambda idx: result[idx][1],
            default=None,
        )
    if donor_idx is None:
        raise ValueError(f'cannot transfer weight to required criteria {criteria}')
    donor_id, donor_weight, donor_pm = result[donor_idx]
    result[donor_idx] = (donor_id, donor_weight - 1, donor_pm)
    for idx, (book_id, weight, payout) in enumerate(result):
        if book_id == wanted_ids[0]:
            result[idx] = (book_id, max(1, weight), payout)
            break
    return result


_TAIL_PM_THRESHOLD = 1_000_000  # 10,000x bet (payout multiplier is in cents)
_TAIL_MAX_PROB = 0.002          # 0.2% compliance limit


def _enforce_tail_probability(rows: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    total_weight = sum(w for _, w, _ in rows)
    max_tail_weight = int(total_weight * _TAIL_MAX_PROB)
    tail_weight = sum(w for _, w, pm in rows if pm >= _TAIL_PM_THRESHOLD)
    if tail_weight <= max_tail_weight:
        return rows

    scale = max_tail_weight / tail_weight
    result = list(rows)
    freed = 0
    for i, (bid, w, pm) in enumerate(result):
        if pm >= _TAIL_PM_THRESHOLD:
            new_w = max(1, int(w * scale))
            freed += w - new_w
            result[i] = (bid, new_w, pm)

    # Redistribute freed weight to zero-payout books proportionally (RTP-neutral)
    zero_indices = [i for i, (_, _, pm) in enumerate(result) if pm == 0]
    if zero_indices:
        zero_total = sum(result[i][1] for i in zero_indices)
        added = 0
        for i in zero_indices[:-1]:
            bid, w, pm = result[i]
            add = int(freed * w / zero_total)
            result[i] = (bid, w + add, pm)
            added += add
        bid, w, pm = result[zero_indices[-1]]
        result[zero_indices[-1]] = (bid, w + (freed - added), pm)
    else:
        # No zero books — spread evenly to non-tail books
        non_tail_weight = sum(result[i][1] for i in range(len(result)) if result[i][2] < _TAIL_PM_THRESHOLD)
        added = 0
        last_non_tail = None
        for i in range(len(result)):
            if result[i][2] < _TAIL_PM_THRESHOLD:
                bid, w, pm = result[i]
                add = int(freed * w / non_tail_weight)
                result[i] = (bid, w + add, pm)
                added += add
                last_non_tail = i
        if last_non_tail is not None and added < freed:
            bid, w, pm = result[last_non_tail]
            result[last_non_tail] = (bid, w + (freed - added), pm)

    return result


def _ensure_max_win_reachable(rows: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    if not rows:
        return rows
    result = list(rows)
    max_pm = max(pm for _, _, pm in result)
    if any(weight > 0 for _, weight, pm in result if pm == max_pm):
        return result
    max_idx = next(idx for idx, (_, _, pm) in enumerate(result) if pm == max_pm)
    donor_idx = max(
        (idx for idx, (_, weight, payout) in enumerate(result) if payout == 0 and weight > 1),
        key=lambda idx: result[idx][1],
        default=None,
    )
    if donor_idx is None:
        donor_idx = max(
            (idx for idx, (_, weight, _) in enumerate(result) if idx != max_idx and weight > 1),
            key=lambda idx: result[idx][1],
            default=None,
        )
    if donor_idx is None:
        raise ValueError('cannot transfer weight to max-win book')
    donor_id, donor_weight, donor_pm = result[donor_idx]
    result[donor_idx] = (donor_id, donor_weight - 1, donor_pm)
    book_id, _, payout = result[max_idx]
    result[max_idx] = (book_id, 1, payout)
    return result


def _weighted_avg_x(rows: list[tuple[int, int, int]]) -> float:
    total_weight = sum(weight for _, weight, _ in rows) or 1
    return sum((payout / 100.0) * weight for _, weight, payout in rows) / total_weight


FEEL_DUCK_BOOST = 1.25
FEEL_MULTIPLIER_BOOST = 0.06


def _normalize_group_weights(scores: list[float], total: int) -> list[int]:
    scaled = _normalize_to_total(scores, total)
    if total >= len(scores):
        # Keep every book in the payout bucket reachable.
        for idx, value in enumerate(scaled):
            if value == 0:
                donor = max(range(len(scaled)), key=lambda i: scaled[i])
                if scaled[donor] > 1:
                    scaled[donor] -= 1
                    scaled[idx] = 1
    return scaled


def _prefer_feel_within_payout_bucket(rows: list[tuple[int, int, int]], books: list[dict[str, Any]], mode: str = '') -> list[tuple[int, int, int]]:
    _log(f'{mode}: feel-bias start')
    # Redistribute only inside exact payout buckets. RTP and payout histogram stay
    # unchanged; selection shifts toward outcomes that show ducks / multiplier wilds.
    by_id = {book['id']: book for book in books}
    groups: dict[int, list[int]] = {}
    for idx, (_, _, payout) in enumerate(rows):
        groups.setdefault(payout, []).append(idx)

    result = list(rows)
    _log(f'{mode}: feel-bias groups {len(groups):,}')
    for group_idx, indices in enumerate(groups.values(), start=1):
        total = sum(rows[idx][1] for idx in indices)
        if total <= 0 or len(indices) <= 1:
            continue
        scores = []
        for idx in indices:
            book_id, weight, _ = rows[idx]
            book = by_id.get(book_id, {})
            feel = 1.0 + FEEL_DUCK_BOOST * int(book.get('duckCount', 0)) + FEEL_MULTIPLIER_BOOST * int(book.get('multiplierCount', 0))
            scores.append(max(0.000001, weight * feel))
        next_weights = _normalize_group_weights(scores, total)
        for idx, next_weight in zip(indices, next_weights):
            book_id, _, payout = result[idx]
            result[idx] = (book_id, next_weight, payout)
        if group_idx % 10000 == 0:
            _log(f'{mode}: feel-bias group {group_idx:,}/{len(groups):,}')
    _log(f'{mode}: feel-bias done')
    return result


def _correct_weighted_mean(mode: str, rows: list[tuple[int, int, int]], target_mean: float | None = None) -> list[tuple[int, int, int]]:
    _log(f'{mode}: RTP correction start')
    """Exact integer EV correction, preserving row reachability and quota."""
    total_weight = sum(weight for _, weight, _ in rows) or 1
    target_sum = int(round((MODE_TARGET_MEANS[mode] if target_mean is None else target_mean) * 100 * total_weight))
    current_sum = sum(payout * weight for _, weight, payout in rows)
    delta = target_sum - current_sum
    if abs(delta) <= 1:
        _log(f'{mode}: RTP correction skipped (delta={delta})')
        return rows

    result = list(rows)
    payout_levels = sorted({payout for _, _, payout in result})
    first_index_for_payout: dict[int, int] = {}
    for idx, (_, _, payout) in enumerate(result):
        first_index_for_payout.setdefault(payout, idx)

    moves = 0
    while delta:
        wanted = abs(delta)
        donor_indices = [idx for idx, (_, weight, _) in enumerate(result) if weight > 1]
        if not donor_indices:
            break

        # Pick the largest valid payout step. Repeating with the residual then
        # reaches the exact integer target when the payout lattice permits it.
        best: tuple[int, int, int] | None = None
        for donor_idx in donor_indices:
            donor_payout = result[donor_idx][2]
            if delta > 0:
                limit = bisect.bisect_right(payout_levels, donor_payout + wanted)
                receiver_payout = payout_levels[limit - 1] if limit else None
                if receiver_payout is None or receiver_payout <= donor_payout:
                    continue
                step = receiver_payout - donor_payout
            else:
                limit = bisect.bisect_left(payout_levels, donor_payout - wanted)
                receiver_payout = payout_levels[limit] if limit < len(payout_levels) else None
                if receiver_payout is None or receiver_payout >= donor_payout:
                    continue
                step = donor_payout - receiver_payout
            candidate = (step, donor_idx, first_index_for_payout[receiver_payout])
            if best is None or candidate[0] > best[0]:
                best = candidate

        if best is None:
            break
        step, donor_idx, receiver_idx = best
        donor_id, donor_weight, donor_payout = result[donor_idx]
        receiver_id, receiver_weight, receiver_payout = result[receiver_idx]
        amount = min(donor_weight - 1, wanted // step)
        if amount <= 0:
            break
        signed_step = step if delta > 0 else -step
        result[donor_idx] = (donor_id, donor_weight - amount, donor_payout)
        result[receiver_idx] = (receiver_id, receiver_weight + amount, receiver_payout)
        delta -= signed_step * amount
        moves += 1

    _log(f'{mode}: RTP correction done (moves={moves}, remaining_delta={delta})')
    return result


NATURAL_FEATURE_TARGETS = {
    'duck': MODE_TARGET_MEANS['DUCK'],
    'roller': MODE_TARGET_MEANS['ROLLER'],
    'coaster': MODE_TARGET_MEANS['COASTER'],
}
NATURAL_RATES = {'BASE': BASE_RATES, 'ANTE': ANTE_RATES}


def _quotas_for_rates(rates: dict[str, float]) -> dict[str, int]:
    """Convert natural trigger rates to exact integer lookup quotas."""
    scaled = {criteria: LOOKUP_SCALE * rate for criteria, rate in rates.items()}
    quotas = {criteria: int(value) for criteria, value in scaled.items()}
    remainder = LOOKUP_SCALE - sum(quotas.values())
    order = sorted(scaled, key=lambda criteria: scaled[criteria] - quotas[criteria], reverse=True)
    for criteria in order[:max(0, remainder)]:
        quotas[criteria] += 1
    if sum(quotas.values()) != LOOKUP_SCALE:
        raise ValueError('natural criteria quotas do not sum to lookup scale')
    return quotas


def _build_natural_lookup(mode: str, books: list[dict[str, Any]]) -> list[tuple[int, int, int]]:
    """Build BASE/ANTE lookup with bought-equivalent feature means and 96.1% total RTP."""
    rates = NATURAL_RATES[mode]
    quotas = _quotas_for_rates(rates)
    by_criteria: dict[str, list[dict[str, Any]]] = {}
    for book in books:
        by_criteria.setdefault(book['criteria'], []).append(book)

    feature_sum = 0
    feature_rows: dict[str, list[tuple[int, int, int]]] = {}
    for criteria, target_mean in NATURAL_FEATURE_TARGETS.items():
        group = by_criteria.get(criteria, [])
        quota = quotas.get(criteria, 0)
        if not group or quota <= 0:
            raise ValueError(f'{mode}: missing natural feature pool or quota for {criteria}')
        values = [book['payoutMultiplier'] / 100.0 for book in group]
        weights = _normalize_to_total(
            _weights_for_target_mean(values, target_mean, TARGET_SCALES[mode]),
            quota,
        )
        rows = [
            (book['id'], weight, int(book['payoutMultiplier']))
            for book, weight in zip(group, weights)
        ]
        rows = _enforce_tail_probability(rows)
        rows = _ensure_max_win_reachable(rows)
        rows = _correct_weighted_mean(mode, rows, target_mean)
        feature_rows[criteria] = rows
        feature_sum += int(round(target_mean * 100 * quota))

    non_feature_criteria = [criteria for criteria in quotas if criteria not in NATURAL_FEATURE_TARGETS]
    non_feature_quota = sum(quotas[criteria] for criteria in non_feature_criteria)
    if non_feature_quota <= 0:
        raise ValueError(f'{mode}: no natural non-feature quota')
    target_total = int(round(MODE_TARGET_MEANS[mode] * 100 * LOOKUP_SCALE))
    non_feature_target_sum = target_total - feature_sum
    non_feature_target_mean = non_feature_target_sum / (100 * non_feature_quota)

    non_feature_rows: list[tuple[int, int, int]] = []
    non_feature_groups: dict[str, list[tuple[int, int, int]]] = {}
    for criteria in non_feature_criteria:
        group = by_criteria.get(criteria, [])
        quota = quotas[criteria]
        if not group or quota <= 0:
            continue
        values = [book['payoutMultiplier'] / 100.0 for book in group]
        weights = _normalize_to_total(
            _weights_for_target_mean(values, non_feature_target_mean, TARGET_SCALES[mode]),
            quota,
        )
        group_rows = [
            (book['id'], weight, int(book['payoutMultiplier']))
            for book, weight in zip(group, weights)
        ]
        group_rows = _enforce_tail_probability(group_rows)
        non_feature_groups[criteria] = group_rows
        non_feature_rows.extend(group_rows)

    # Correct only inside one non-feature criterion. A correction across the
    # aggregate would silently change trigger quotas (e.g. duckcollect +2e-6).
    actual_non_feature_sum = sum(payout * weight for _, weight, payout in non_feature_rows)
    non_feature_delta = non_feature_target_sum - actual_non_feature_sum
    if non_feature_delta:
        correction_criteria = next(
            criteria for criteria in ('basegame', 'duckcollect', '0')
            if criteria in non_feature_groups
        )
        correction_rows = non_feature_groups[correction_criteria]
        correction_quota = sum(weight for _, weight, _ in correction_rows)
        current_mean = _weighted_avg_x(correction_rows)
        target_mean = current_mean + non_feature_delta / (100 * correction_quota)
        corrected_rows = _correct_weighted_mean(mode, correction_rows, target_mean)
        non_feature_groups[correction_criteria] = corrected_rows
        non_feature_rows = [
            row
            for criteria in non_feature_criteria
            for row in non_feature_groups.get(criteria, [])
        ]

    rows = [row for criteria in quotas for row in feature_rows.get(criteria, [])]
    rows.extend(non_feature_rows)
    if sum(weight for _, weight, _ in rows) != LOOKUP_SCALE:
        raise ValueError(f'{mode}: natural lookup weight mismatch')
    # Publisher contract: CSV row N must describe event/book row N. The grouped
    # construction above is useful for exact criteria quotas, but cannot be
    # emitted in criteria order because the JSONL books stay in id order.
    rows_by_id = {book_id: (book_id, weight, payout) for book_id, weight, payout in rows}
    rows = [rows_by_id[book['id']] for book in books]
    _log(
        f'{mode}: natural lookup done '
        f'(rtp={_weighted_avg_x(rows) / MODE_COSTS[mode]:.9f}, '
        f'feature_means=' + ', '.join(
            f'{criteria}={_weighted_avg_x(feature_rows[criteria]):.6f}x'
            for criteria in NATURAL_FEATURE_TARGETS
        ) + ')'
    )
    return rows


def _apply_ensures(mode: str, rows: list[tuple[int, int, int]], books: list[dict[str, Any]], include_feel: bool = True) -> list[tuple[int, int, int]]:
    for criteria in ENSURE_CRITERIA.get(mode, []):
        rows = _ensure_weight_presence(rows, books, criteria)
    rows = _enforce_tail_probability(rows)
    rows = _ensure_max_win_reachable(rows)
    if not include_feel:
        return rows
    rows = _prefer_feel_within_payout_bucket(rows, books, mode)
    return _correct_weighted_mean(mode, rows)


def _build_mode_lookup(mode: str, books: list[dict[str, Any]]) -> list[tuple[int, int, int]]:
    _log(f'{mode}: build lookup start')
    # Binary-search the effective target to absorb integer quantization and the
    # forced weight-1 rows added by the ensure passes. Two-phase search: phase 1
    # searches [desired*0.8, desired]; if that undershoots by >0.5%, phase 2
    # searches above desired (systematic downward bias when zero-win books
    # dominate the weight pool).
    desired = MODE_TARGET_MEANS[mode]
    zero_cap = ZERO_WEIGHT_CAP.get(mode)
    if zero_cap is not None:
        _log(f'{mode}: zero-payout weight capped at {zero_cap:.1%}')
    raw_mean = sum(b['payoutMultiplier'] / 100.0 for b in books) / max(len(books), 1)
    lo, hi = desired * 0.8, desired

    for _ in range(20):
        mid = (lo + hi) / 2.0
        rows = _build_rows_for_target_mean(books, mid, LOOKUP_SCALE, TARGET_SCALES[mode], zero_cap)
        actual = _weighted_avg_x(_apply_ensures(mode, rows, books, include_feel=False))
        if _ % 5 == 4:
            _log(f'{mode}: phase1 iter {_ + 1}/20 actual={actual / MODE_COSTS[mode]:.9f}')
        if actual > desired:
            hi = mid
        else:
            lo = mid

    rows = _build_rows_for_target_mean(books, (lo + hi) / 2.0, LOOKUP_SCALE, TARGET_SCALES[mode], zero_cap)
    phase1_rows = _apply_ensures(mode, rows, books, include_feel=True)
    _log(f'{mode}: phase1 done rtp={_weighted_avg_x(phase1_rows) / MODE_COSTS[mode]:.9f}')

    if desired - _weighted_avg_x(phase1_rows) > desired * 0.005:
        lo2, hi2 = desired, max(raw_mean, desired * 2)
        for _ in range(20):
            mid = (lo2 + hi2) / 2.0
            rows = _build_rows_for_target_mean(books, mid, LOOKUP_SCALE, TARGET_SCALES[mode], zero_cap)
            actual = _weighted_avg_x(_apply_ensures(mode, rows, books, include_feel=False))
            if _ % 5 == 4:
                _log(f'{mode}: phase2 iter {_ + 1}/20 actual={actual / MODE_COSTS[mode]:.9f}')
            if actual > desired:
                hi2 = mid
            else:
                lo2 = mid
        rows = _build_rows_for_target_mean(books, (lo2 + hi2) / 2.0, LOOKUP_SCALE, TARGET_SCALES[mode], zero_cap)
        phase2_rows = _apply_ensures(mode, rows, books, include_feel=True)
        _log(f'{mode}: phase2 done rtp={_weighted_avg_x(phase2_rows) / MODE_COSTS[mode]:.9f}')
        if abs(_weighted_avg_x(phase2_rows) - desired) < abs(_weighted_avg_x(phase1_rows) - desired):
            _log(f'{mode}: build lookup done (phase2 chosen)')
            return phase2_rows

    _log(f'{mode}: build lookup done (phase1 chosen)')
    return phase1_rows


def _load_base_components(
    library_path: str,
    rows: list[tuple[int, int, int]],
) -> tuple[list[str], np.ndarray]:
    """Load exact BASE component payouts in cents, including injected tail books."""
    segmented_path = os.path.join(library_path, 'lookup_tables', 'lookUpTableSegmented_BASE.csv')
    metadata: dict[int, tuple[str, int, int]] = {}
    with open(segmented_path, 'r', encoding='utf-8') as file:
        for line in file:
            if not line.strip():
                continue
            book_id, criteria, base_win, free_win = line.strip().split(',')
            metadata[int(book_id)] = (
                criteria or '0',
                int(round(float(base_win) * 100)),
                int(round(float(free_win) * 100)),
            )

    row_ids = {book_id for book_id, _, _ in rows}
    missing_ids = row_ids - set(metadata)
    if missing_ids:
        # Injected coverage/max-win books are always appended to JSONL.
        from report import _load_tail_books

        books_path = os.path.join(library_path, 'books', 'books_BASE.jsonl')
        for book in _load_tail_books(books_path, len(missing_ids)):
            book_id = int(book['id'])
            if book_id in missing_ids:
                metadata[book_id] = (
                    str(book.get('criteria') or '0'),
                    int(round(float(book.get('baseGameWins', 0.0)) * 100)),
                    int(round(float(book.get('freeGameWins', 0.0)) * 100)),
                )

    unresolved = row_ids - set(metadata)
    if unresolved:
        raise ValueError(f'BASE: unresolved segmented ids: {sorted(unresolved)[:5]}')

    criteria: list[str] = []
    components = np.zeros((len(rows), 3), dtype=np.int64)
    for idx, (book_id, _, payout) in enumerate(rows):
        criterion, base_cents, free_cents = metadata[book_id]
        criterion = '0' if criterion in ('', '0') else criterion
        if base_cents + free_cents != payout:
            raise ValueError(
                f'BASE book {book_id}: component sum {base_cents + free_cents} != payout {payout}'
            )
        criteria.append(criterion)
        components[idx, 0] = base_cents
        if criterion in ('roller', 'coaster'):
            components[idx, 1] = free_cents
        elif criterion == 'duck':
            components[idx, 2] = free_cents
        elif free_cents:
            raise ValueError(f'BASE book {book_id}: unexpected free win for {criterion}')
    return criteria, components


def _exact_criteria_quotas() -> dict[str, int]:
    quotas = {criteria: int(LOOKUP_SCALE * rate) for criteria, rate in BASE_RATES.items()}
    remainder = LOOKUP_SCALE - sum(quotas.values())
    order = sorted(
        BASE_RATES,
        key=lambda criteria: (LOOKUP_SCALE * BASE_RATES[criteria] - quotas[criteria], criteria),
        reverse=True,
    )
    for criteria in order[:remainder]:
        quotas[criteria] += 1
    if sum(quotas.values()) != LOOKUP_SCALE:
        raise ValueError('BASE criteria quotas do not sum to lookup scale')
    return quotas


def _target_component_sums() -> np.ndarray:
    total = int(round(TARGET_RTP * 100 * LOOKUP_SCALE))
    base = int(round(total * TARGET_RTP_SHARES['base']))
    freespin = int(round(total * TARGET_RTP_SHARES['freespin']))
    bonus = total - base - freespin
    return np.array([base, freespin, bonus], dtype=np.int64)


def _solve_component_weights(
    rows: list[tuple[int, int, int]],
    criteria: list[str],
    components: np.ndarray,
    quotas: dict[str, int],
) -> np.ndarray:
    """Minimum-change entropy projection onto criteria and RTP constraints."""
    groups: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, float]] = {}
    old_weights = np.array([weight for _, weight, _ in rows], dtype=np.float64)
    for criterion, quota in quotas.items():
        indices = np.array(
            [idx for idx, value in enumerate(criteria) if value == criterion],
            dtype=np.int64,
        )
        if not len(indices):
            raise ValueError(f'BASE: no books for required criteria {criterion}')
        values_x = components[indices].astype(np.float64) / 100.0
        # Tiny pseudocount keeps previously zero-weight outcomes eligible without
        # materially discarding the existing distribution as the prior.
        log_prior = np.log(old_weights[indices] + 0.01)
        groups[criterion] = (indices, values_x, log_prior, quota / LOOKUP_SCALE)

    target = _target_component_sums().astype(np.float64) / LOOKUP_SCALE / 100.0

    def evaluate(lambdas: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
        moments = np.zeros(3, dtype=np.float64)
        jacobian = np.zeros((3, 3), dtype=np.float64)
        probabilities: dict[str, np.ndarray] = {}
        for criterion, (_, values, log_prior, mass) in groups.items():
            scores = log_prior + values @ lambdas
            scores -= scores.max()
            probability = np.exp(scores)
            probability /= probability.sum()
            probabilities[criterion] = probability
            mean = probability @ values
            centered = values - mean
            moments += mass * mean
            jacobian += mass * ((centered * probability[:, None]).T @ centered)
        return moments, jacobian, probabilities

    lambdas = np.zeros(3, dtype=np.float64)
    probabilities: dict[str, np.ndarray] = {}
    for iteration in range(50):
        moments, jacobian, probabilities = evaluate(lambdas)
        error = target - moments
        if np.max(np.abs(error)) < 1e-11:
            break
        delta = np.linalg.solve(jacobian + np.eye(3) * 1e-12, error)
        old_error = np.linalg.norm(error / target)
        step = 1.0
        while step >= 1e-7:
            next_moments, _, _ = evaluate(lambdas + delta * step)
            if np.linalg.norm((target - next_moments) / target) < old_error:
                break
            step *= 0.5
        if step < 1e-7:
            raise ValueError('BASE RTP split solver failed to make progress')
        lambdas += delta * step
    else:
        raise ValueError('BASE RTP split solver did not converge')

    weights = np.zeros(len(rows), dtype=np.int64)
    for criterion, (indices, _, _, _) in groups.items():
        raw = probabilities[criterion] * quotas[criterion]
        integer = np.floor(raw).astype(np.int64)
        remainder = quotas[criterion] - int(integer.sum())
        if remainder:
            fractional = raw - integer
            order = np.argsort(fractional, kind='stable')
            integer[order[-remainder:]] += 1
        weights[indices] = integer
    return weights


def _ensure_base_max_reachable(
    rows: list[tuple[int, int, int]],
    criteria: list[str],
    weights: np.ndarray,
) -> np.ndarray:
    max_idx = max(range(len(rows)), key=lambda idx: rows[idx][2])
    if weights[max_idx] > 0:
        return weights
    criterion = criteria[max_idx]
    donor = max(
        (idx for idx, value in enumerate(criteria) if value == criterion and weights[idx] > 0),
        key=lambda idx: weights[idx],
        default=None,
    )
    if donor is None:
        raise ValueError('BASE: cannot make max win reachable')
    weights[donor] -= 1
    weights[max_idx] = 1
    return weights


_BASE_TAIL_ROW_THRESHOLD = 500_000  # 5,000x in payout cents
_BASE_TAIL_ROW_MAX_WEIGHT = 1


def _cap_base_tail_rows(
    rows: list[tuple[int, int, int]],
    criteria: list[str],
    weights: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Cap individual 5,000x+ BASE outcomes so volatility stays compliance-safe."""
    caps = np.full(len(rows), LOOKUP_SCALE, dtype=np.int64)
    for idx, (_, _, payout) in enumerate(rows):
        if payout >= _BASE_TAIL_ROW_THRESHOLD:
            caps[idx] = _BASE_TAIL_ROW_MAX_WEIGHT

    for idx, cap in enumerate(caps):
        if weights[idx] <= cap:
            continue
        excess = int(weights[idx] - cap)
        weights[idx] = cap
        criterion = criteria[idx]
        receiver = min(
            (
                candidate
                for candidate, value in enumerate(criteria)
                if value == criterion and weights[candidate] < caps[candidate]
            ),
            key=lambda candidate: rows[candidate][2],
            default=None,
        )
        if receiver is None:
            raise ValueError(f'BASE: cannot redistribute capped {criterion} tail weight')
        weights[receiver] += excess
    return weights, caps


def _correct_component_sum(
    weights: np.ndarray,
    values: np.ndarray,
    target: int,
    criteria: list[str],
    eligible_criteria: tuple[str, ...],
    protected: np.ndarray,
    caps: np.ndarray,
) -> None:
    """Exact integer moment correction via within-criteria weight transfers."""
    delta = target - int(weights @ values)
    group_levels: dict[str, tuple[list[int], dict[int, list[int]]]] = {}
    for criterion in eligible_criteria:
        by_value: dict[int, list[int]] = {}
        for idx, value in enumerate(criteria):
            if value == criterion:
                by_value.setdefault(int(values[idx]), []).append(idx)
        group_levels[criterion] = (sorted(by_value), by_value)

    moves = 0
    while delta and moves < 10_000:
        sign = 1 if delta > 0 else -1
        wanted = abs(delta)
        best: tuple[int, int, int, int, dict[int, list[int]]] | None = None
        for criterion in eligible_criteria:
            levels, by_value = group_levels[criterion]
            receiver_capacity = {
                value: sum(max(0, int(caps[idx] - weights[idx])) for idx in indices)
                for value, indices in by_value.items()
            }
            receiver_levels = sorted(value for value, capacity in receiver_capacity.items() if capacity)
            for donor_value in levels:
                available = sum(
                    max(0, int(weights[idx] - protected[idx]))
                    for idx in by_value[donor_value]
                )
                if not available:
                    continue
                if sign > 0:
                    pos = bisect.bisect_right(receiver_levels, donor_value + wanted) - 1
                    if pos < 0 or receiver_levels[pos] <= donor_value:
                        continue
                else:
                    pos = bisect.bisect_left(receiver_levels, donor_value - wanted)
                    if pos >= len(receiver_levels) or receiver_levels[pos] >= donor_value:
                        continue
                receiver_value = receiver_levels[pos]
                step = abs(receiver_value - donor_value)
                if best is None or step > best[0]:
                    best = (
                        step,
                        donor_value,
                        receiver_value,
                        min(available, receiver_capacity[receiver_value]),
                        by_value,
                    )

        if best is None:
            raise ValueError(f'BASE: cannot exactly correct component delta {delta}')
        step, donor_value, receiver_value, available, by_value = best
        amount = min(available, wanted // step)
        if amount <= 0:
            raise ValueError(f'BASE: zero-size component correction for delta {delta}')
        remaining = amount
        for donor_idx in by_value[donor_value]:
            take = min(remaining, max(0, int(weights[donor_idx] - protected[donor_idx])))
            weights[donor_idx] -= take
            remaining -= take
            if not remaining:
                break
        remaining = amount
        for receiver_idx in by_value[receiver_value]:
            put = min(remaining, max(0, int(caps[receiver_idx] - weights[receiver_idx])))
            weights[receiver_idx] += put
            remaining -= put
            if not remaining:
                break
        delta -= sign * step * amount
        moves += 1


def _rebalance_base_rows(
    library_path: str,
    rows: list[tuple[int, int, int]],
) -> list[tuple[int, int, int]]:
    _log('BASE: constrained 52/40/8 rebalance start')
    criteria, components = _load_base_components(library_path, rows)
    quotas = _exact_criteria_quotas()
    weights = _solve_component_weights(rows, criteria, components, quotas)
    weights, caps = _cap_base_tail_rows(rows, criteria, weights)
    weights = _ensure_base_max_reachable(rows, criteria, weights)

    protected = np.zeros(len(rows), dtype=np.int64)
    max_idx = max(range(len(rows)), key=lambda idx: rows[idx][2])
    protected[max_idx] = 1
    targets = _target_component_sums()
    # Feature corrections can slightly alter their trigger-spin base wins, so
    # correct bonus -> free spins -> base in that order.
    _correct_component_sum(
        weights,
        components[:, 2],
        int(targets[2]),
        criteria,
        ('duck',),
        protected,
        caps,
    )
    _correct_component_sum(
        weights,
        components[:, 1],
        int(targets[1]),
        criteria,
        ('roller', 'coaster'),
        protected,
        caps,
    )
    _correct_component_sum(
        weights,
        components[:, 0],
        int(targets[0]),
        criteria,
        ('basegame', 'duckcollect'),
        protected,
        caps,
    )

    actual = weights @ components
    if not np.array_equal(actual, targets):
        raise ValueError(f'BASE RTP component mismatch: {actual.tolist()} != {targets.tolist()}')
    if int(weights.sum()) != LOOKUP_SCALE:
        raise ValueError(f'BASE lookup weight mismatch: {int(weights.sum())}')
    if np.any(weights > caps):
        raise ValueError('BASE tail row cap violated')
    for criterion, quota in quotas.items():
        actual_quota = sum(int(weights[idx]) for idx, value in enumerate(criteria) if value == criterion)
        if actual_quota != quota:
            raise ValueError(f'BASE {criterion} quota mismatch: {actual_quota} != {quota}')
    tail_weight = sum(
        int(weights[idx]) for idx, (_, _, payout) in enumerate(rows) if payout >= _TAIL_PM_THRESHOLD
    )
    if tail_weight > int(LOOKUP_SCALE * _TAIL_MAX_PROB):
        raise ValueError(f'BASE tail probability exceeds cap: {tail_weight / LOOKUP_SCALE:.6%}')
    hit_rate = sum(
        int(weights[idx]) for idx, (_, _, payout) in enumerate(rows) if payout > 0
    ) / LOOKUP_SCALE
    if abs(hit_rate - TARGET_BASE_HIT_RATE) > 0.002:
        raise ValueError(f'BASE hit rate out of tolerance: {hit_rate:.6%}')

    result = [
        (book_id, int(weights[idx]), payout)
        for idx, (book_id, _, payout) in enumerate(rows)
    ]
    _log(
        'BASE: constrained rebalance done '
        f'(rtp={_weighted_avg_x(result):.9f}, hit={hit_rate:.6%}, tail={tail_weight / LOOKUP_SCALE:.6%})'
    )
    return result


def rebalance_base_lookup(library_path: str) -> float:
    """Rebalance an existing BASE lookup and update both release copies."""
    source = os.path.join(library_path, 'lookup_tables', 'lookUpTable_BASE.csv')
    rows: list[tuple[int, int, int]] = []
    with open(source, 'r', encoding='utf-8') as file:
        for line in file:
            if line.strip():
                book_id, weight, payout = line.strip().split(',')
                rows.append((int(book_id), int(weight), int(payout)))
    rows = _rebalance_base_rows(library_path, rows)
    _write_lookup(source, rows)
    _write_lookup(os.path.join(library_path, 'publish_files', 'lookUpTable_BASE_0.csv'), rows)
    return _weighted_avg_x(rows)


def weight_all_lookups(library_path: str, modes: list[str] | None = None) -> dict[str, float]:
    """Re-weight `modes` (default: all). Lookups for modes not listed are left untouched."""
    books_path = os.path.join(library_path, 'books')
    lookup_path = os.path.join(library_path, 'lookup_tables')
    publish_path = os.path.join(library_path, 'publish_files')

    lookups = {}
    for mode in (modes or list(MODE_COSTS)):
        books = _load_books(os.path.join(books_path, f'books_{mode}.jsonl'), mode)
        lookups[mode] = (
            _build_natural_lookup(mode, books)
            if mode in NATURAL_RATES
            else _build_mode_lookup(mode, books)
        )
        _log(f'{mode}: lookup ready; releasing books from memory')

    for mode, rows in lookups.items():
        _write_lookup(os.path.join(lookup_path, f'lookUpTable_{mode}.csv'), rows)
        _write_lookup(os.path.join(publish_path, f'lookUpTable_{mode}_0.csv'), rows)

    rtps = {mode: _weighted_avg_x(rows) / MODE_COSTS[mode] for mode, rows in lookups.items()}
    _log(f'all done {rtps}')
    return rtps
