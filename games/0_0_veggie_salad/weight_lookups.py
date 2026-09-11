"""Exact group-probability and RTP weighting for Veggie Salad books."""

from __future__ import annotations

import bisect
import json
import math
import os
from collections import defaultdict
from typing import Any

from math_targets import (
    LOOKUP_SCALE,
    MODE_COSTS,
    MODE_GROUP_TARGET_MEANS,
    MODE_GROUP_WEIGHTS,
)


def _canonical_group(mode: str, criteria: str) -> str:
    if criteria.startswith("tail_"):
        return criteria.removeprefix("tail_")
    if criteria != "max":
        return criteria
    return {
        "BASE": "basegame",
        "CHANCE": "basegame",
        "FEATURE": "feature",
        "BONUS": "normal",
        "MYSTERY": "hidden",
        "SUPER": "super",
    }[mode]


def _load_books(path: str, mode: str) -> list[dict[str, Any]]:
    books = []
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            raw = json.loads(line)
            criteria = str(raw.get("criteria", "0"))
            books.append(
                {
                    "id": int(raw["id"]),
                    "payout": int(raw["payoutMultiplier"]),
                    "criteria": criteria,
                    "group": _canonical_group(mode, criteria),
                }
            )
    return books


def _stable_scores(values: list[int], beta: float) -> list[float]:
    if not values:
        return []
    centre = sum(values) / len(values)
    scale = max(100.0, max(values) - min(values))
    logs = [beta * ((value - centre) / scale) for value in values]
    peak = max(logs)
    return [math.exp(value - peak) for value in logs]


def _weighted_mean(values: list[int], beta: float) -> float:
    scores = _stable_scores(values, beta)
    total = sum(scores) or 1.0
    return sum(value * score for value, score in zip(values, scores)) / total


def _solve_beta(values: list[int], target: float) -> float:
    minimum, maximum = min(values), max(values)
    if target < minimum - 1e-9 or target > maximum + 1e-9:
        raise RuntimeError(
            f"target payout {target / 100:.4f}x outside generated range "
            f"[{minimum / 100:.4f}x, {maximum / 100:.4f}x]"
        )
    if abs(target - sum(values) / len(values)) < 1e-12:
        return 0.0
    low, high = -1.0, 1.0
    while _weighted_mean(values, low) > target and low > -1_000:
        low *= 2
    while _weighted_mean(values, high) < target and high < 1_000:
        high *= 2
    for _ in range(100):
        mid = (low + high) / 2
        if _weighted_mean(values, mid) < target:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def _normalize_positive(scores: list[float], total: int) -> list[int]:
    if total < len(scores):
        raise RuntimeError(f"lookup group weight {total} cannot keep {len(scores)} books reachable")
    if not scores:
        return []
    remaining = total - len(scores)
    score_total = sum(scores) or 1.0
    raw = [remaining * score / score_total for score in scores]
    weights = [1 + int(value) for value in raw]
    remainder = total - sum(weights)
    order = sorted(range(len(scores)), key=lambda index: raw[index] - int(raw[index]), reverse=True)
    for index in order[:remainder]:
        weights[index] += 1
    return weights


def _correct_sum(
    rows: list[tuple[int, int, int]],
    target_sum: int,
    fixed_ids: set[int],
) -> list[tuple[int, int, int]]:
    result = list(rows)
    current = sum(weight * payout for _, weight, payout in result)
    delta = target_sum - current
    if delta == 0:
        return result

    payout_levels = sorted({payout for _, _, payout in result})
    receiver_by_payout = {}
    for index, (book_id, _weight, payout) in enumerate(result):
        if book_id not in fixed_ids:
            receiver_by_payout.setdefault(payout, index)

    for _ in range(20_000):
        if delta == 0:
            break
        donors = [
            index
            for index, (book_id, weight, _payout) in enumerate(result)
            if book_id not in fixed_ids and weight > 1
        ]
        if not donors:
            break
        donors.sort(key=lambda index: result[index][2], reverse=delta < 0)
        moved = False
        for donor_index in donors:
            donor_id, donor_weight, donor_payout = result[donor_index]
            wanted = abs(delta)
            if delta > 0:
                candidate_index = bisect.bisect_right(payout_levels, donor_payout + wanted) - 1
                while candidate_index >= 0 and (
                    payout_levels[candidate_index] <= donor_payout
                    or payout_levels[candidate_index] not in receiver_by_payout
                ):
                    candidate_index -= 1
            else:
                candidate_index = bisect.bisect_left(payout_levels, donor_payout - wanted)
                while candidate_index < len(payout_levels) and (
                    payout_levels[candidate_index] >= donor_payout
                    or payout_levels[candidate_index] not in receiver_by_payout
                ):
                    candidate_index += 1
            if not 0 <= candidate_index < len(payout_levels):
                continue
            receiver_payout = payout_levels[candidate_index]
            receiver_index = receiver_by_payout[receiver_payout]
            step = receiver_payout - donor_payout
            if step == 0:
                continue
            amount = min(donor_weight - 1, max(1, abs(delta) // abs(step)))
            next_delta = delta - step * amount
            if abs(next_delta) >= abs(delta):
                continue
            receiver_id, receiver_weight, _ = result[receiver_index]
            result[donor_index] = (donor_id, donor_weight - amount, donor_payout)
            result[receiver_index] = (receiver_id, receiver_weight + amount, receiver_payout)
            delta = next_delta
            moved = True
            break
        if not moved:
            break
    return result


def _weight_group(
    books: list[dict[str, Any]],
    total_weight: int,
    target_mean_x: float,
) -> list[tuple[int, int, int]]:
    fixed = [book for book in books if book["criteria"] == "max"]
    regular = [book for book in books if book["criteria"] != "max"]
    fixed_rows = [(book["id"], 1, book["payout"]) for book in fixed]
    fixed_sum = sum(book["payout"] for book in fixed)
    regular_total = total_weight - len(fixed)
    target_sum = int(round(target_mean_x * 100 * total_weight))

    if not regular:
        if fixed_sum != target_sum:
            raise RuntimeError("group has no regular books available for RTP weighting")
        return fixed_rows

    target_regular_mean = (target_sum - fixed_sum) / regular_total
    values = [book["payout"] for book in regular]
    beta = _solve_beta(values, target_regular_mean)
    weights = _normalize_positive(_stable_scores(values, beta), regular_total)
    rows = fixed_rows + [
        (book["id"], weight, book["payout"]) for book, weight in zip(regular, weights)
    ]
    return _correct_sum(rows, target_sum, {book["id"] for book in fixed})


def build_mode_lookup(mode: str, books: list[dict[str, Any]]) -> list[tuple[int, int, int]]:
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for book in books:
        by_group[book["group"]].append(book)

    rows = []
    for group, total_weight in MODE_GROUP_WEIGHTS[mode].items():
        group_books = by_group.get(group, [])
        if not group_books:
            raise RuntimeError(f"{mode}: no generated books for group {group}")
        rows.extend(
            _weight_group(
                group_books,
                total_weight,
                MODE_GROUP_TARGET_MEANS[mode][group],
            )
        )
    rows.sort(key=lambda row: row[0])
    if sum(weight for _, weight, _ in rows) != LOOKUP_SCALE:
        raise RuntimeError(f"{mode}: lookup weight total mismatch")
    if any(weight <= 0 for _, weight, _ in rows):
        raise RuntimeError(f"{mode}: non-positive lookup weight")
    return rows


def _write_lookup(path: str, rows: list[tuple[int, int, int]]) -> None:
    with open(path, "w", encoding="utf-8") as file:
        for book_id, weight, payout in rows:
            file.write(f"{book_id},{weight},{payout}\n")


def _rtp(mode: str, rows: list[tuple[int, int, int]]) -> float:
    mean_x = sum(weight * payout for _, weight, payout in rows) / (LOOKUP_SCALE * 100)
    return mean_x / MODE_COSTS[mode]


def weight_all_lookups(library_path: str) -> dict[str, float]:
    books_path = os.path.join(library_path, "books")
    lookup_path = os.path.join(library_path, "lookup_tables")
    publish_path = os.path.join(library_path, "publish_files")
    os.makedirs(lookup_path, exist_ok=True)
    os.makedirs(publish_path, exist_ok=True)

    rtps = {}
    for mode in MODE_COSTS:
        books = _load_books(os.path.join(books_path, f"books_{mode}.jsonl"), mode)
        rows = build_mode_lookup(mode, books)
        _write_lookup(os.path.join(lookup_path, f"lookUpTable_{mode}.csv"), rows)
        _write_lookup(os.path.join(publish_path, f"lookUpTable_{mode}_0.csv"), rows)
        rtps[mode] = _rtp(mode, rows)
        print(f"{mode}: weighted RTP {rtps[mode]:.10f}")
    return rtps
