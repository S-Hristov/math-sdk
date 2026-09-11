"""McSchmutzo lookup weighting.

Replaces the optimizer's per-mode weighting with a per-GROUP one: each part of a mode (no-win
spins, paying base spins, wheel rounds) gets its own slice of the weight and its own target mean,
so the trigger rate and the value of a natural bonus are design inputs rather than whatever falls
out of a single mode-wide solve. See math_targets.py for the numbers and the reasoning.

Reads books from library/books/books_{mode}.jsonl if present, otherwise from the compressed
library/publish_files/books_{mode}.jsonl.zst — McSchmutzo's runs delete the raw JSONL after
compressing, so the published file is normally the only copy.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import re
from typing import Any

from math_targets import (
    LOOKUP_SCALE,
    MAX_WIN_HIT_RATE,
    MODE_COSTS,
    MODE_TARGET_MEANS,
    NATURAL_FEATURE_DESIGN,
    TARGET_SCALES,
    ZERO_WEIGHT_CAP,
)

WHEEL_RE = re.compile(r'"type"\s*:\s*"bonusWheel"')
# How the wheel was entered: 3 scatters (the bonus1 feature) or 4 (the bonus2 feature).
ENTRY_RE = re.compile(r'"scatterEntry"\s*:\s*(\d+)')
ID_RE = re.compile(r'"id"\s*:\s*(\d+)')
PAYOUT_RE = re.compile(r'"payoutMultiplier"\s*:\s*(\d+)')


def _log(message: str) -> None:
    print(f'[weight_lookups] {message}', flush=True)


# ── loading ──────────────────────────────────────────────────────────────────


def _open_books(library_path: str, mode: str):
    raw = os.path.join(library_path, 'books', f'books_{mode}.jsonl')
    if os.path.exists(raw) and os.path.getsize(raw) > 0:
        return open(raw, 'r', encoding='utf-8'), raw
    packed = os.path.join(library_path, 'publish_files', f'books_{mode}.jsonl.zst')
    import zstandard as zstd

    reader = zstd.ZstdDecompressor().stream_reader(open(packed, 'rb'))
    return io.TextIOWrapper(reader, encoding='utf-8'), packed


def _load_books(library_path: str, mode: str) -> list[dict[str, Any]]:
    """id, payout and whether the round reached the wheel.

    Regex rather than json.loads: these files are hundreds of MB and only three fields are needed.
    """
    handle, source = _open_books(library_path, mode)
    _log(f'{mode}: reading {os.path.basename(source)}')
    books = []
    with handle:
        for line in handle:
            if not line.strip():
                continue
            entry = ENTRY_RE.search(line) if WHEEL_RE.search(line) else None
            books.append(
                {
                    'id': int(ID_RE.search(line).group(1)),
                    'payoutMultiplier': int(PAYOUT_RE.search(line).group(1)),
                    'entry': int(entry.group(1)) if entry else None,
                }
            )
            if len(books) % 25_000 == 0:
                _log(f'{mode}: loaded {len(books):,} books')
    wheels = [b for b in books if b['entry'] is not None]
    kinds = {}
    for book in wheels:
        kinds[book['entry']] = kinds.get(book['entry'], 0) + 1
    _log(
        f'{mode}: {len(books):,} books, {len(wheels) / max(len(books), 1):.2%} reached the wheel '
        + ('(' + ', '.join(f'{k} scatters: {v:,}' for k, v in sorted(kinds.items())) + ')' if kinds else '')
    )
    return books


def _write_lookup(path: str, rows: list[tuple[int, int, int]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _log(f'write {os.path.basename(path)} ({len(rows):,} rows)')
    with open(path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        for book_id, weight, payout in rows:
            writer.writerow([book_id, weight, payout])


# ── weighting primitives ─────────────────────────────────────────────────────


def _normalize_to_total(weights: list[float], total: int) -> list[int]:
    """Float weights -> integers summing exactly to `total`, keeping every row reachable."""
    if not weights:
        return []
    positive = sum(w for w in weights if w > 0) or 1.0
    scaled = [max(0, int(w / positive * total)) for w in weights]
    drift = total - sum(scaled)
    if drift:
        order = sorted(range(len(scaled)), key=lambda i: weights[i], reverse=True)
        step = 1 if drift > 0 else -1
        i = 0
        while drift != 0 and order:
            idx = order[i % len(order)]
            if step < 0 and scaled[idx] <= 0:
                i += 1
                if i > len(order) * 4:
                    break
                continue
            scaled[idx] += step
            drift -= step
            i += 1
    return scaled


def _solve_alpha(values: list[float], target_mean: float, scale: float) -> float:
    """exp(-alpha * value / scale) weights whose weighted mean equals target_mean."""

    def mean_for(alpha: float) -> float:
        weights = [math.exp(-alpha * (value / scale)) for value in values]
        total = sum(weights) or 1.0
        return sum(v * w for v, w in zip(values, weights)) / total

    lo, hi = 0.0, 1.0
    for _ in range(200):
        if mean_for(hi) <= target_mean:
            break
        hi *= 2.0
        if hi > 1e9:
            break
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if mean_for(mid) > target_mean:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _weights_for_target_mean(values: list[float], target_mean: float, scale: float) -> list[float]:
    if not values:
        return []
    raw_mean = sum(values) / len(values)
    if target_mean <= 0 or target_mean >= raw_mean:
        return [1.0 for _ in values]
    if target_mean <= min(values):
        low = min(values)
        return [1.0 if value == low else 1e-9 for value in values]
    alpha = _solve_alpha(values, target_mean, scale)
    return [math.exp(-alpha * (value / scale)) for value in values]


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
    """Tilt to a target mean with the zero cap applied.

    Capping zeros lifts the mean, so the tilt is solved against a lower input target and searched
    back onto the wanted one.
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


def _weighted_avg_x(rows: list[tuple[int, int, int]]) -> float:
    total = sum(weight for _, weight, _ in rows) or 1
    return sum((payout / 100.0) * weight for _, weight, payout in rows) / total


def _correct_rows_to_mean(
    rows: list[tuple[int, int, int]], target_mean: float, label: str, protect_payout: int | None = None
) -> list[tuple[int, int, int]]:
    """Nudge integer weights so the weighted mean lands on target, never overshooting.

    `protect_payout` rows are left alone — the max-win fence is a fixed probability and must not be
    used as change for an EV correction.
    """
    total_weight = sum(weight for _, weight, _ in rows) or 1
    target_sum = int(round(target_mean * 100 * total_weight))
    current_sum = sum(payout * weight for _, weight, payout in rows)
    delta = target_sum - current_sum
    if abs(delta) <= 1:
        return rows

    result = list(rows)
    payout_levels = sorted({payout for _, _, payout in result if payout != protect_payout})
    first_index = {}
    for idx, (_, _, payout) in enumerate(result):
        if payout != protect_payout:
            first_index.setdefault(payout, idx)
    donors = sorted(
        (idx for idx, (_, weight, payout) in enumerate(result) if weight > 1 and payout != protect_payout),
        key=lambda idx: result[idx][2],
        reverse=delta < 0,
    )

    moves = 0
    for donor_idx in donors:
        if abs(delta) <= 1:
            break
        donor_id, donor_weight, donor_payout = result[donor_idx]
        room = donor_weight - 1
        if room <= 0:
            continue
        wanted = abs(delta)
        if delta > 0:
            candidates = [p for p in payout_levels if donor_payout < p <= donor_payout + wanted]
            receiver_payout = max(candidates) if candidates else None
        else:
            candidates = [p for p in payout_levels if donor_payout - wanted <= p < donor_payout]
            receiver_payout = min(candidates) if candidates else None
        if receiver_payout is None:
            break
        step = receiver_payout - donor_payout
        amount = min(room, max(1, abs(delta) // abs(step)))
        next_delta = delta - step * amount
        if abs(next_delta) >= abs(delta):
            continue
        receiver_idx = first_index[receiver_payout]
        receiver_id, receiver_weight, _ = result[receiver_idx]
        result[donor_idx] = (donor_id, donor_weight - amount, donor_payout)
        result[receiver_idx] = (receiver_id, receiver_weight + amount, receiver_payout)
        delta = next_delta
        moves += 1

    _log(f'{label}: EV correction moves={moves} remaining_delta={delta}')
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


# ── mode builders ────────────────────────────────────────────────────────────


def _group_of(book: dict[str, Any]) -> str:
    """Books only carry criteria main/wincap, so the group comes from the events.

    Wheel rounds split by entry, because a 3-scatter round is the feature bonus1 sells and a
    4-scatter round is the one bonus2 sells — they are worth different amounts and have to be
    weighted against different targets.
    """
    if book['entry'] is not None:
        return f'feature{book["entry"]}'
    return 'basegame' if book['payoutMultiplier'] > 0 else '0'


def _fence_rows(max_books: list[dict[str, Any]], weight_total: int) -> list[tuple[int, int, int]]:
    """Spread the max-win fence weight across the books that pay it."""
    floats = [1.0 for _ in max_books]
    weights = _normalize_to_total(floats, weight_total)
    return [(b['id'], w, int(b['payoutMultiplier'])) for b, w in zip(max_books, weights)]


def build_mode_lookup(mode: str, books: list[dict[str, Any]]) -> list[tuple[int, int, int]]:
    design = NATURAL_FEATURE_DESIGN.get(mode)
    target = MODE_TARGET_MEANS[mode]
    scale = TARGET_SCALES[mode]

    # The max-win fence is a fixed probability, so those books are held out of the tilt entirely
    # and given their own slice of the weight. Everything else is solved against what is left of
    # the mode's RTP.
    max_pm = max(book['payoutMultiplier'] for book in books)
    max_value = max_pm / 100.0
    max_share = 1.0 / MAX_WIN_HIT_RATE
    max_weight = max(1, int(round(max_share * LOOKUP_SCALE)))
    max_books = [book for book in books if book['payoutMultiplier'] == max_pm]
    books = [book for book in books if book['payoutMultiplier'] != max_pm]
    fence = _fence_rows(max_books, max_weight)
    _log(
        f'{mode}: max-win fence {max_value:,.0f}x across {len(max_books):,} books, '
        f'1 in {1 / max_share:,.0f} rounds ({max_share * max_value / target:.2%} of RTP)'
    )

    if design is None:
        # A bought mode: every book is the feature, so it is one group with a shape target.
        rest_share = 1.0 - max_share
        rest_target = (target - max_share * max_value) / rest_share
        values = [book['payoutMultiplier'] / 100.0 for book in books]
        floats = _group_weights(values, rest_target, scale, ZERO_WEIGHT_CAP.get(mode))
        weights = _normalize_to_total(floats, LOOKUP_SCALE - max_weight)
        rows = [(b['id'], w, int(b['payoutMultiplier'])) for b, w in zip(books, weights)]
        rows = _correct_rows_to_mean(rows, rest_target, f'{mode}/rest', protect_payout=max_pm)
        rows = sorted(rows + fence, key=lambda row: row[0])
        rows = _correct_rows_to_mean(rows, target, mode, protect_payout=max_pm)
        _log(f'{mode}: mean {_weighted_avg_x(rows):.4f}x rtp={_weighted_avg_x(rows) / MODE_COSTS[mode]:.9f}')
        return rows

    groups: dict[str, list[dict[str, Any]]] = {}
    for book in books:
        groups.setdefault(_group_of(book), []).append(book)
    features = design['features']
    for required in list(features) + ['basegame', '0']:
        if not groups.get(required):
            raise ValueError(f'{mode}: no books in group {required!r}')

    feature_rtp = sum(spec['mean'] / spec['frequency'] for spec in features.values())
    feature_share = sum(1.0 / spec['frequency'] for spec in features.values())
    paying_share = design['paying_share'] - feature_share - max_share
    if paying_share <= 0:
        raise ValueError(f'{mode}: feature frequencies exceed the paying share')
    base_mean = (target - feature_rtp - max_share * max_value) / paying_share
    if base_mean <= 0:
        raise ValueError(
            f'{mode}: the features alone cost {feature_rtp:.4f} against a mode RTP of {target:.4f} '
            f'— make them rarer or lower their means'
        )
    shares = {name: 1.0 / spec['frequency'] for name, spec in features.items()}
    shares['basegame'] = paying_share
    shares['0'] = 1.0 - design['paying_share']
    _log(f'{mode}: fence holds {max_share:.3e} of the weight')
    _log(f'{mode}: shares ' + ', '.join(f'{k} {v:.5f}' for k, v in shares.items()))
    for name, spec in features.items():
        _log(
            f'{mode}: {name} 1 in {spec["frequency"]} @ {spec["mean"]:.2f}x '
            f'({spec["mean"] / spec["frequency"] / target:.1%} of RTP)'
        )
    _log(f'{mode}: features hold {feature_rtp / target:.1%} of RTP, paying base spin target {base_mean:.3f}x')

    rows: list[tuple[int, int, int]] = []
    for group, group_books in groups.items():
        total = int(round(shares[group] * LOOKUP_SCALE))
        values = [book['payoutMultiplier'] / 100.0 for book in group_books]
        group_target = base_mean if group == 'basegame' else features.get(group, {}).get('mean')
        if group == '0':
            floats = [1.0 for _ in values]
        else:
            floats = _group_weights(values, group_target, scale, ZERO_WEIGHT_CAP.get(group))
        weights = _normalize_to_total(floats, total)
        group_rows = [(b['id'], w, int(b['payoutMultiplier'])) for b, w in zip(group_books, weights)]
        if group != '0':
            group_rows = _correct_rows_to_mean(group_rows, group_target, f'{mode}/{group}')
        got = sum(w for _, w, _ in group_rows) or 1
        _log(
            f'{mode}/{group}: weight share {got / LOOKUP_SCALE:.5f} '
            f'mean {sum(pm * w for _, w, pm in group_rows) / got / 100:.3f}x '
            f'zero {sum(w for _, w, pm in group_rows if pm == 0) / got:.2%}'
        )
        rows.extend(group_rows)

    rows.extend(fence)
    rows.sort(key=lambda row: row[0])
    rows = _correct_rows_to_mean(rows, target, mode, protect_payout=max_pm)
    fence_weight = sum(w for _, w, pm in rows if pm == max_pm)
    total = sum(w for _, w, _ in rows) or 1
    _log(
        f'{mode}: max win {max_value:,.0f}x at 1 in {total / fence_weight:,.0f} rounds; '
        f'rtp={_weighted_avg_x(rows) / MODE_COSTS[mode]:.9f}'
    )
    return rows


def weight_all_lookups(library_path: str, modes: list[str] | None = None) -> dict[str, float]:
    """Re-weight `modes` (default: all). Lookups for modes not listed are left untouched."""
    lookups = {}
    for mode in (modes or list(MODE_COSTS)):
        books = _load_books(library_path, mode)
        lookups[mode] = build_mode_lookup(mode, books)
        _log(f'{mode}: lookup ready; releasing books from memory')
        del books

    for mode, rows in lookups.items():
        _write_lookup(os.path.join(library_path, 'lookup_tables', f'lookUpTable_{mode}.csv'), rows)
        _write_lookup(os.path.join(library_path, 'publish_files', f'lookUpTable_{mode}_0.csv'), rows)

    rtps = {mode: _weighted_avg_x(rows) / MODE_COSTS[mode] for mode, rows in lookups.items()}
    _log(f'all done {rtps}')
    return rtps
