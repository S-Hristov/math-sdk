"""Magnetic lookup weighting."""

from __future__ import annotations

import bisect
import json
import math
import os
from typing import Any

from math_targets import (
    LOOKUP_SCALE,
    MODE_COSTS,
    MODE_TARGET_MEANS,
    NATURAL_FEATURE_DESIGN,
    ZERO_WEIGHT_CAP,
)

TARGET_SCALES = {
    'BASE': 40.0,
    'CHANCE': 45.0,
    'FEATURE': 28.0,
    'BONUS': 80.0,
    'SUPER': 180.0,
}


def _log(message: str) -> None:
    print(f'[weight_lookups] {message}', flush=True)


def _book_feel_score(raw: dict[str, Any]) -> tuple[int, int]:
    magnet_count = 0
    multiplier_count = 0
    for event in raw.get('events', []):
        if event.get('type') != 'reveal':
            continue
        for reel in event.get('board', []):
            for cell in reel:
                if not cell.get('magnet'):
                    continue
                magnet_count += 1
                if int(cell.get('multiplier', 1)) > 1:
                    multiplier_count += 1
    return magnet_count, multiplier_count


def _load_books(path: str, mode: str = '') -> list[dict[str, Any]]:
    books = []
    label = mode or os.path.basename(path)
    _log(f'{label}: load books start')
    with open(path, 'r', encoding='utf-8') as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            raw = json.loads(line)
            magnet_count, multiplier_count = _book_feel_score(raw)
            books.append(
                {
                    'id': int(raw['id']),
                    'payoutMultiplier': int(raw['payoutMultiplier']),
                    'criteria': str(raw.get('criteria', 'basegame')),
                    'magnetCount': magnet_count,
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


def _build_rows_for_target_mean(books: list[dict[str, Any]], target_mean: float, total_weight: int, scale: float) -> list[tuple[int, int, int]]:
    values = [book['payoutMultiplier'] / 100.0 for book in books]
    float_weights = _weights_for_target_mean(values, target_mean, scale)
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
    if donor_idx is not None:
        donor_id, donor_weight, donor_pm = result[donor_idx]
        result[donor_idx] = (donor_id, donor_weight - 1, donor_pm)
    for idx, (book_id, weight, payout) in enumerate(result):
        if book_id == wanted_ids[0]:
            result[idx] = (book_id, max(1, weight), payout)
            break
    return result


_TAIL_PM_THRESHOLD = 1_000_000  # 10,000× bet (payout_multiplier is in cents, 1,000,000 = 10,000x)
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
    if donor_idx is not None:
        donor_id, donor_weight, donor_pm = result[donor_idx]
        result[donor_idx] = (donor_id, donor_weight - 1, donor_pm)
    book_id, _, payout = result[max_idx]
    result[max_idx] = (book_id, 1, payout)
    return result


def _weighted_avg_x(rows: list[tuple[int, int, int]]) -> float:
    total_weight = sum(weight for _, weight, _ in rows) or 1
    return sum((payout / 100.0) * weight for _, weight, payout in rows) / total_weight


FEEL_MAGNET_BOOST = 1.75
FEEL_MULTIPLIER_BOOST = 4.00


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


def _payout_feel_bucket(payout: int) -> int:
    # Coarse bands mirror player-visible win ranges; target search still clamps EV.
    for idx, threshold in enumerate((0, 200, 500, 1000, 2000, 5000, 10000, 25000, 50000, 100000, 250000, 500000, 1000000)):
        if payout <= threshold:
            return idx
    return 99


def _prefer_feel_within_payout_bucket(rows: list[tuple[int, int, int]], books: list[dict[str, Any]], mode: str = '') -> list[tuple[int, int, int]]:
    _log(f'{mode}: feel-bias start')
    # Redistribute only inside exact payout buckets. RTP and payout histogram stay unchanged;
    # selection shifts toward outcomes that show magnets / multiplier magnets.
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
            feel = 1.0 + FEEL_MAGNET_BOOST * int(book.get('magnetCount', 0)) + FEEL_MULTIPLIER_BOOST * int(book.get('multiplierCount', 0))
            scores.append(max(0.000001, weight * feel))
        next_weights = _normalize_group_weights(scores, total)
        for idx, next_weight in zip(indices, next_weights):
            book_id, _, payout = result[idx]
            result[idx] = (book_id, next_weight, payout)
        if group_idx % 10000 == 0:
            _log(f'{mode}: feel-bias group {group_idx:,}/{len(groups):,}')
    _log(f'{mode}: feel-bias done')
    return result


def _correct_weighted_mean(mode: str, rows: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    return _correct_rows_to_mean(rows, MODE_TARGET_MEANS[mode], mode)


def _correct_rows_to_mean(rows: list[tuple[int, int, int]], target_mean: float, label: str) -> list[tuple[int, int, int]]:
    _log(f'{label}: RTP correction start')
    """Small, safe EV correction after feel-bias weighting.

    The correction must never make RTP worse.  With large book sets the pre-feel
    binary search is already close; moving one weight to a very high payout can
    overshoot badly (BASE hit this).  This version only chooses payout steps that
    reduce the absolute delta, preferring the largest step that fits inside the
    remaining delta.
    """
    total_weight = sum(weight for _, weight, _ in rows) or 1
    target_sum = int(round(target_mean * 100 * total_weight))
    current_sum = sum(payout * weight for _, weight, payout in rows)
    delta = target_sum - current_sum
    if abs(delta) <= 1:
        _log(f'{label}: RTP correction skipped (delta={delta})')
        return rows

    result = list(rows)
    payout_levels = sorted({payout for _, _, payout in result})
    first_index_for_payout: dict[int, int] = {}
    for idx, (_, _, payout) in enumerate(result):
        first_index_for_payout.setdefault(payout, idx)

    if delta > 0:
        donors = sorted(
            (idx for idx, (_, weight, _) in enumerate(result) if weight > 1),
            key=lambda idx: result[idx][2],
        )
    else:
        donors = sorted(
            (idx for idx, (_, weight, _) in enumerate(result) if weight > 1),
            key=lambda idx: result[idx][2],
            reverse=True,
        )

    moves = 0
    for donor_idx in donors:
        if abs(delta) <= 1:
            break
        donor_id, donor_weight, donor_payout = result[donor_idx]
        donor_room = donor_weight - 1  # keep donor row reachable
        if donor_room <= 0:
            continue

        wanted = abs(delta)
        receiver_payout = None
        if delta > 0:
            # Need higher payout; choose highest payout with step <= wanted.
            hi = bisect.bisect_right(payout_levels, donor_payout + wanted) - 1
            while hi >= 0 and payout_levels[hi] <= donor_payout:
                hi -= 1
            if hi >= 0:
                receiver_payout = payout_levels[hi]
        else:
            # Need lower payout; choose lowest payout with step <= wanted.
            lo = bisect.bisect_left(payout_levels, donor_payout - wanted)
            while lo < len(payout_levels) and payout_levels[lo] >= donor_payout:
                lo += 1
            if lo < len(payout_levels):
                receiver_payout = payout_levels[lo]

        if receiver_payout is None:
            # No non-overshooting single-weight move exists.  Stop; current RTP is
            # already closer than any available one-step correction.
            break

        receiver_idx = first_index_for_payout[receiver_payout]
        receiver_id, receiver_weight, _ = result[receiver_idx]
        step = receiver_payout - donor_payout
        if step == 0 or (delta > 0 and step <= 0) or (delta < 0 and step >= 0):
            continue

        amount = min(donor_room, max(1, abs(delta) // abs(step)))
        next_delta = delta - step * amount
        if abs(next_delta) >= abs(delta):
            continue

        result[donor_idx] = (donor_id, donor_weight - amount, donor_payout)
        result[receiver_idx] = (receiver_id, receiver_weight + amount, receiver_payout)
        delta = next_delta
        moves += 1

    _log(f'{label}: RTP correction done (moves={moves}, remaining_delta={delta})')
    return result


def _apply_ensures(mode: str, rows: list[tuple[int, int, int]], books: list[dict[str, Any]], include_feel: bool = True) -> list[tuple[int, int, int]]:
    if mode in ('BASE', 'CHANCE'):
        rows = _ensure_weight_presence(rows, books, 'bonus')
        rows = _ensure_weight_presence(rows, books, 'super')
    if mode == 'BONUS':
        rows = _ensure_weight_presence(rows, books, 'bonus')
    if mode == 'SUPER':
        rows = _ensure_weight_presence(rows, books, 'super')
        rows = _enforce_tail_probability(rows)
    if mode == 'FEATURE':
        rows = _ensure_weight_presence(rows, books, 'feature')
    rows = _ensure_max_win_reachable(rows)
    if not include_feel:
        return rows
    rows = _prefer_feel_within_payout_bucket(rows, books, mode)
    return _correct_weighted_mean(mode, rows)


def _cap_zero_weight(values: list[float], weights: list[float], cap: float) -> list[float]:
    """Hold zero-payout books to at most `cap` of the group's weight."""
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


def _group_weights(values: list[float], target_mean: float, scale: float, cap: float | None) -> list[float]:
    """Tilt a criteria group to its own target mean, with the zero cap applied.

    Capping zeros removes weight from the bottom of the distribution and therefore RAISES the
    mean, so the tilt has to be solved against a lower input target. Same binary search the mode
    level uses, just applied per group.
    """
    if cap is None:
        return _weights_for_target_mean(values, target_mean, scale)

    def capped(input_target: float) -> tuple[list[float], float]:
        weights = _cap_zero_weight(values, _weights_for_target_mean(values, input_target, scale), cap)
        total = sum(weights) or 1.0
        return weights, sum(v * w for v, w in zip(values, weights)) / total

    weights, mean = capped(target_mean)
    if mean <= target_mean:
        return weights
    lo, hi = 0.0, target_mean
    for _ in range(40):
        mid = (lo + hi) / 2.0
        weights, mean = capped(mid)
        if mean > target_mean:
            hi = mid
        else:
            lo = mid
    return capped((lo + hi) / 2.0)[0]


def _build_grouped_lookup(mode: str, books: list[dict[str, Any]]) -> list[tuple[int, int, int]]:
    """Weight BASE / CHANCE one criteria group at a time.

    Each group gets its own target mean and its own slice of the total weight, so the trigger
    rate and the value of a natural bonus are both design inputs instead of whatever falls out
    of a single mode-wide tilt.
    """
    design = NATURAL_FEATURE_DESIGN[mode]
    groups: dict[str, list[dict[str, Any]]] = {}
    for book in books:
        groups.setdefault(book['criteria'], []).append(book)

    shares = {
        'bonus': 1.0 / design['bonus']['frequency'],
        'super': 1.0 / design['super']['frequency'],
        'basegame': design['basegame_share'],
    }
    feature_rtp = shares['bonus'] * design['bonus']['mean'] + shares['super'] * design['super']['mean']
    base_mean = (MODE_TARGET_MEANS[mode] - feature_rtp) / shares['basegame']
    shares['0'] = 1.0 - shares['bonus'] - shares['super'] - shares['basegame']
    if shares['0'] < 0:
        raise ValueError(f'{mode}: criteria shares exceed 1 ({shares})')
    _log(f'{mode}: grouped shares ' + ', '.join(f'{k} {v:.5f}' for k, v in shares.items()))
    _log(f'{mode}: base-game target mean {base_mean:.4f}x, features hold {feature_rtp / MODE_TARGET_MEANS[mode]:.1%} of RTP')

    rows: list[tuple[int, int, int]] = []
    for criteria, group in groups.items():
        share = shares.get(criteria)
        if share is None:
            raise ValueError(f'{mode}: no share defined for criteria {criteria}')
        total = int(round(share * LOOKUP_SCALE))
        values = [book['payoutMultiplier'] / 100.0 for book in group]
        if criteria == '0':
            floats = [1.0 for _ in values]
        else:
            target = base_mean if criteria == 'basegame' else design[criteria]['mean']
            floats = _group_weights(values, target, TARGET_SCALES[mode], ZERO_WEIGHT_CAP.get(criteria))
        weights = _normalize_to_total(floats, total)
        group_rows = [(book['id'], weight, int(book['payoutMultiplier'])) for book, weight in zip(group, weights)]
        # Feel-bias inside the group only: run mode-wide it would shuffle weight between criteria
        # that happen to share a payout value, which would move the trigger rates.
        group_rows = _prefer_feel_within_payout_bucket(group_rows, group, f'{mode}/{criteria}')
        if criteria != '0':
            # Integer weights are coarse for the feature groups (a few thousand books sharing
            # ~25k units), so the tilt alone lands a few percent off. Correct each group against
            # its OWN target here: left to the mode-level correction, one blunt move to fix total
            # RTP would land inside a single group and skew it (super went to 88x in testing).
            group_target = base_mean if criteria == 'basegame' else design[criteria]['mean']
            group_rows = _correct_rows_to_mean(group_rows, group_target, f'{mode}/{criteria}')
        got = sum(w for _, w, _ in group_rows) or 1
        got_mean = sum(pm * w for _, w, pm in group_rows) / got / 100.0
        got_zero = sum(w for _, w, pm in group_rows if pm == 0) / got
        _log(f'{mode}/{criteria}: weight {got:,} ({got / LOOKUP_SCALE:.5f}) mean {got_mean:.3f}x zero {got_zero:.2%}')
        rows.extend(group_rows)

    rows.sort(key=lambda row: row[0])
    rows = _ensure_weight_presence(rows, books, 'bonus')
    rows = _ensure_weight_presence(rows, books, 'super')
    rows = _ensure_max_win_reachable(rows)
    rows = _correct_weighted_mean(mode, rows)
    _log(f'{mode}: grouped lookup done rtp={_weighted_avg_x(rows) / MODE_COSTS[mode]:.9f}')
    return rows


def _build_mode_lookup(mode: str, books: list[dict[str, Any]]) -> list[tuple[int, int, int]]:
    _log(f'{mode}: build lookup start')
    if mode in NATURAL_FEATURE_DESIGN:
        return _build_grouped_lookup(mode, books)
    # Binary-search the effective target to absorb both sources of drift:
    #   1. Integer quantization error from _normalize_to_total
    #   2. The forced weight-1 added by _ensure_max_win_reachable
    # Both are consistent for a given book set — searching the input target converges fast.
    #
    # Two-phase search: phase 1 searches [desired*0.8, desired] (normal downward correction).
    # If phase 1 undershoots by more than 0.5% (integer quantization is a systematic downward
    # bias for modes with many zero-win books), phase 2 searches [desired, raw_mean*0.5] to find
    # a float input slightly above desired whose integer output lands on desired.
    desired = MODE_TARGET_MEANS[mode]
    raw_mean = sum(b['payoutMultiplier'] / 100.0 for b in books) / max(len(books), 1)
    lo, hi = desired * 0.8, desired

    for _ in range(20):
        mid = (lo + hi) / 2.0
        rows = _build_rows_for_target_mean(books, mid, LOOKUP_SCALE, TARGET_SCALES[mode])
        actual = _weighted_avg_x(_apply_ensures(mode, rows, books, include_feel=False))
        if _ % 5 == 4:
            _log(f'{mode}: phase1 iter {_ + 1}/20 actual={actual / MODE_COSTS[mode]:.9f}')
        if actual > desired:
            hi = mid
        else:
            lo = mid

    rows = _build_rows_for_target_mean(books, (lo + hi) / 2.0, LOOKUP_SCALE, TARGET_SCALES[mode])
    phase1_rows = _apply_ensures(mode, rows, books, include_feel=True)
    _log(f'{mode}: phase1 done rtp={_weighted_avg_x(phase1_rows) / MODE_COSTS[mode]:.9f}')

    # Phase 2: if phase 1 undershoots by more than 0.5%, search above desired.
    # Integer quantization creates a systematic downward bias when zero-win books dominate
    # the weight pool; the correct float input is slightly above the desired output.
    # hi2 must reach at least raw_mean so the search covers the equal-weights region —
    # critical when tail enforcement reduces the effective RTP ceiling below raw_mean*0.5.
    if desired - _weighted_avg_x(phase1_rows) > desired * 0.005:
        lo2, hi2 = desired, max(raw_mean, desired * 2)
        for _ in range(20):
            mid = (lo2 + hi2) / 2.0
            rows = _build_rows_for_target_mean(books, mid, LOOKUP_SCALE, TARGET_SCALES[mode])
            actual = _weighted_avg_x(_apply_ensures(mode, rows, books, include_feel=False))
            if _ % 5 == 4:
                _log(f'{mode}: phase2 iter {_ + 1}/20 actual={actual / MODE_COSTS[mode]:.9f}')
            if actual > desired:
                hi2 = mid
            else:
                lo2 = mid
        rows = _build_rows_for_target_mean(books, (lo2 + hi2) / 2.0, LOOKUP_SCALE, TARGET_SCALES[mode])
        phase2_rows = _apply_ensures(mode, rows, books, include_feel=True)
        _log(f'{mode}: phase2 done rtp={_weighted_avg_x(phase2_rows) / MODE_COSTS[mode]:.9f}')
        # Pick whichever phase is closer to desired
        if abs(_weighted_avg_x(phase2_rows) - desired) < abs(_weighted_avg_x(phase1_rows) - desired):
            _log(f'{mode}: build lookup done (phase2 chosen)')
            return phase2_rows

    _log(f'{mode}: build lookup done (phase1 chosen)')
    return phase1_rows


def weight_all_lookups(library_path: str, modes: list[str] | None = None) -> dict[str, float]:
    """Re-weight `modes` (default: all). Files for modes not listed are left untouched."""
    books_path = os.path.join(library_path, 'books')
    lookup_path = os.path.join(library_path, 'lookup_tables')
    publish_path = os.path.join(library_path, 'publish_files')

    lookups = {}
    for mode in (modes or list(MODE_COSTS)):
        books = _load_books(os.path.join(books_path, f'books_{mode}.jsonl'), mode)
        lookups[mode] = _build_mode_lookup(mode, books)
        _log(f'{mode}: lookup ready; releasing books from memory')

    for mode, rows in lookups.items():
        _write_lookup(os.path.join(lookup_path, f'lookUpTable_{mode}.csv'), rows)
        _write_lookup(os.path.join(publish_path, f'lookUpTable_{mode}_0.csv'), rows)

    rtps = {mode: _weighted_avg_x(rows) / MODE_COSTS[mode] for mode, rows in lookups.items()}
    _log(f'all done {rtps}')
    return rtps
