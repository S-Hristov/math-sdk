"""Fit positive integer LUT weights to Rogue Bandit RTP/behavior targets."""

from __future__ import annotations

import bisect
from collections import defaultdict
from fractions import Fraction
import io
import json
import math
from pathlib import Path

import zstandard as zstd

try:
    from . import math_targets as T
except ImportError:
    import math_targets as T


def load_books(path: Path) -> list[dict]:
    with path.open("rb") as raw, zstd.ZstdDecompressor().stream_reader(raw) as reader:
        with io.TextIOWrapper(reader) as text:
            return [json.loads(line) for line in text if line.strip()]


def _scores(values: list[int], beta: float) -> list[float]:
    low, high = min(values), max(values)
    span = max(1, high - low)
    logs = [beta * (value - low) / span for value in values]
    peak = max(logs)
    return [math.exp(value - peak) for value in logs]


def _score_mean(values: list[int], beta: float) -> float:
    weights = _scores(values, beta)
    return sum(value * weight for value, weight in zip(values, weights)) / sum(weights)


def _correct_moment(values: list[int], weights: list[int], target: int) -> int:
    delta = target - sum(value * weight for value, weight in zip(values, weights))
    by_value: dict[int, int] = {}
    for index, value in enumerate(values):
        by_value.setdefault(value, index)
    levels = sorted(by_value)
    donors = sorted(range(len(values)), key=lambda index: values[index])
    for _ in range(100_000):
        if delta == 0:
            return 0
        moved = False
        for donor in donors if delta > 0 else reversed(donors):
            if weights[donor] <= 1:
                continue
            value = values[donor]
            if delta > 0:
                pos = bisect.bisect_right(levels, value + delta) - 1
                if pos < 0 or levels[pos] <= value:
                    continue
            else:
                pos = bisect.bisect_left(levels, value + delta)
                if pos == len(levels) or levels[pos] >= value:
                    continue
            receiver = by_value[levels[pos]]
            step = values[receiver] - value
            count = min(weights[donor] - 1, abs(delta) // abs(step))
            if count:
                weights[donor] -= count
                weights[receiver] += count
                delta -= count * step
                moved = True
                break
        if not moved:
            return delta
    raise RuntimeError(f"moment correction did not converge: {delta}")


def fit_positive(values: list[int], total: int, target_mean_x: Fraction) -> tuple[list[int], dict]:
    if not values or total <= len(values):
        raise ValueError("weight mass must exceed candidate count")
    target_moment_fraction = target_mean_x * T.BOOK_SCALE * total
    if target_moment_fraction.denominator != 1:
        target_moment = round(target_moment_fraction)
    else:
        target_moment = target_moment_fraction.numerator
    remaining_mass = total - len(values)
    residual_mean = Fraction(target_moment - sum(values), remaining_mass)
    if not min(values) <= residual_mean <= max(values):
        raise RuntimeError(f"target {float(target_mean_x):.6f}x outside support "
                           f"[{min(values)/100:.2f}, {max(values)/100:.2f}]")
    lo, hi = -1.0, 1.0
    while _score_mean(values, lo) > residual_mean:
        lo *= 2
    while _score_mean(values, hi) < residual_mean:
        hi *= 2
    for _ in range(90):
        mid = (lo + hi) / 2
        if _score_mean(values, mid) < residual_mean:
            lo = mid
        else:
            hi = mid
    scores = _scores(values, (lo + hi) / 2)
    allocations = [remaining_mass * score / sum(scores) for score in scores]
    weights = [1 + math.floor(value) for value in allocations]
    remainder = total - sum(weights)
    for index in sorted(range(len(values)), key=lambda i: allocations[i] % 1, reverse=True)[:remainder]:
        weights[index] += 1
    residual = _correct_moment(values, weights, target_moment)
    actual = Fraction(sum(value * weight for value, weight in zip(values, weights)), T.BOOK_SCALE * total)
    if sum(weights) != total or min(weights) < 1:
        raise RuntimeError("weight invariant failed")
    return weights, {"targetMeanX": float(target_mean_x), "actualMeanX": float(actual),
                     "momentResidual": residual, "supportX": [min(values)/100, max(values)/100],
                     "effectiveBookCount": total * total / sum(weight * weight for weight in weights)}


def uniform(count: int, total: int) -> list[int]:
    if count <= 0 or total < count:
        raise ValueError("invalid uniform group")
    whole, remainder = divmod(total, count)
    return [whole + (index < remainder) for index in range(count)]


def _partition_fit(records: list[dict], groups: dict[str, list[int]], masses: dict[str, int],
                   targets: dict[str, Fraction]) -> tuple[list[int], dict]:
    weights = [0] * len(records)
    reports = {}
    for name, indexes in groups.items():
        values = [records[index]["payoutMultiplier"] for index in indexes]
        target = targets[name]
        if min(values) == max(values):
            fitted = uniform(len(values), masses[name])
            report = {"targetMeanX": float(target), "actualMeanX": values[0] / 100,
                      "momentResidual": 0, "supportX": [values[0]/100, values[0]/100]}
        else:
            fitted, report = fit_positive(values, masses[name], target)
        for index, weight in zip(indexes, fitted):
            weights[index] = weight
        reports[name] = {**report, "probability": masses[name] / T.LOOKUP_SCALE,
                         "candidates": len(indexes)}
    if min(weights) < 1 or sum(weights) != T.LOOKUP_SCALE:
        raise RuntimeError("partition weighting failed")
    return weights, reports


def _base_weights(mode: str, records: list[dict]) -> tuple[list[int], dict]:
    has_steal = lambda row: any(event["type"] == "steal" for event in row["events"])
    groups = {
        "0": [i for i, row in enumerate(records) if row["criteria"] == "0"],
        "basegame_plain": [i for i, row in enumerate(records) if row["criteria"] == "basegame" and not has_steal(row)],
        "basegame_steal": [i for i, row in enumerate(records) if row["criteria"] == "basegame" and has_steal(row)],
        "freegame": [i for i, row in enumerate(records) if row["criteria"] == "freegame"],
        "wincap": [i for i, row in enumerate(records) if row["criteria"] == "wincap"],
    }
    cap_mass = round(T.MAX_WIN_RATE * T.LOOKUP_SCALE)
    free_mass = round(T.NATURAL_TRIGGER_RATES[mode] * T.LOOKUP_SCALE)
    hit_mass = round(T.BASE_HIT_RATES[mode] * T.LOOKUP_SCALE)
    base_mass = hit_mass - free_mass - cap_mass
    steal_mass = round(T.BASE_STEAL_VISIBLE_RATE * T.LOOKUP_SCALE)
    base_steal_mass = steal_mass - free_mass
    masses = {"wincap": cap_mass, "freegame": free_mass,
              "basegame_steal": base_steal_mass,
              "basegame_plain": base_mass - base_steal_mass,
              "0": T.LOOKUP_SCALE - hit_mass}
    target = T.MODE_TARGET_MEANS[mode]
    cap_contribution = Fraction(cap_mass, T.LOOKUP_SCALE) * T.MAX_WIN_X
    nonzero = {name: groups[name] for name in ("basegame_plain", "basegame_steal", "freegame")}
    nonzero_masses = {name: masses[name] for name in nonzero}
    targets = _tilted_partition_targets(records, nonzero, nonzero_masses, target - cap_contribution)
    targets.update({"0": Fraction(0), "wincap": Fraction(T.MAX_WIN_X)})
    weights, report = _partition_fit(records, groups, masses, targets)
    report["publishedHitRate"] = hit_mass / T.LOOKUP_SCALE
    report["publishedTriggerRate"] = free_mass / T.LOOKUP_SCALE
    report["publishedStealVisibleRate"] = steal_mass / T.LOOKUP_SCALE
    return weights, report


def _tilted_partition_targets(records: list[dict], groups: dict[str, list[int]], masses: dict[str, int],
                              total_target: Fraction) -> dict[str, Fraction]:
    def mean(beta: float) -> float:
        return sum((masses[name] / T.LOOKUP_SCALE) * (_score_mean(
            [records[index]["payoutMultiplier"] for index in indexes], beta) / 100)
                   for name, indexes in groups.items())
    lo, hi = -1.0, 1.0
    while mean(lo) > float(total_target):
        lo *= 2
    while mean(hi) < float(total_target):
        hi *= 2
    for _ in range(90):
        mid = (lo + hi) / 2
        if mean(mid) < float(total_target):
            lo = mid
        else:
            hi = mid
    beta = (lo + hi) / 2
    return {name: Fraction(str(_score_mean([records[index]["payoutMultiplier"] for index in indexes], beta) / 100))
            for name, indexes in groups.items()}


def _superspin_weights(records: list[dict]) -> tuple[list[int], dict]:
    cap = [i for i, row in enumerate(records) if row["payoutMultiplier"] == T.MAX_WIN_AMOUNT]
    groups = {
        "under10": [i for i, row in enumerate(records) if row["payoutMultiplier"] < 1_000],
        "10to100": [i for i, row in enumerate(records) if 1_000 <= row["payoutMultiplier"] < 10_000],
        "100plus": [i for i, row in enumerate(records) if 10_000 <= row["payoutMultiplier"] < T.MAX_WIN_AMOUNT],
        "wincap": cap,
    }
    cap_mass = round(T.MAX_WIN_RATE * T.LOOKUP_SCALE)
    masses = {"under10": round(T.SUPERSPIN_BANDS["under10"] * T.LOOKUP_SCALE),
              "10to100": round(T.SUPERSPIN_BANDS["10to100"] * T.LOOKUP_SCALE),
              "100plus": round(T.SUPERSPIN_BANDS["100plus"] * T.LOOKUP_SCALE) - cap_mass,
              "wincap": cap_mass}
    noncap_target = (T.MODE_TARGET_MEANS["superspin"] - Fraction(cap_mass, T.LOOKUP_SCALE) * T.MAX_WIN_X)
    noncap_groups = {name: indexes for name, indexes in groups.items() if name != "wincap"}
    noncap_masses = {name: masses[name] for name in noncap_groups}
    # Helper assumes masses over the global scale, so target remains the global non-cap contribution.
    targets = _tilted_partition_targets(records, noncap_groups, noncap_masses, noncap_target)
    targets["wincap"] = Fraction(T.MAX_WIN_X)
    return _partition_fit(records, groups, masses, targets)


def _buy_weights(mode: str, records: list[dict]) -> tuple[list[int], dict]:
    groups = {"regular": [i for i, row in enumerate(records) if row["payoutMultiplier"] < T.MAX_WIN_AMOUNT],
              "wincap": [i for i, row in enumerate(records) if row["payoutMultiplier"] == T.MAX_WIN_AMOUNT]}
    cap_mass = round(T.MAX_WIN_RATE * T.LOOKUP_SCALE)
    regular_mass = T.LOOKUP_SCALE - cap_mass
    regular_target = ((T.MODE_TARGET_MEANS[mode] * T.LOOKUP_SCALE) - cap_mass * T.MAX_WIN_X) / regular_mass
    masses = {"regular": regular_mass, "wincap": cap_mass}
    targets = {"regular": regular_target, "wincap": Fraction(T.MAX_WIN_X)}
    return _partition_fit(records, groups, masses, targets)


def weight_all(library: Path) -> dict:
    report = {"modelVersion": T.MODEL_VERSION, "lookupScale": T.LOOKUP_SCALE, "modes": {}}
    for mode, cost in T.MODE_COSTS.items():
        records = load_books(library / "publish_files" / f"books_{mode}.jsonl.zst")
        if mode in ("base", "ante"):
            weights, details = _base_weights(mode, records)
        elif mode == "superspin":
            weights, details = _superspin_weights(records)
        else:
            weights, details = _buy_weights(mode, records)
        rows = [(row["id"], weight, row["payoutMultiplier"]) for row, weight in zip(records, weights)]
        for path in (library / "lookup_tables" / f"lookUpTable_{mode}.csv",
                     library / "publish_files" / f"lookUpTable_{mode}_0.csv"):
            path.write_text("".join(f"{book_id},{weight},{payout}\n" for book_id, weight, payout in rows))
        mean = Fraction(sum(weight * payout for _, weight, payout in rows), T.LOOKUP_SCALE * T.BOOK_SCALE)
        rtp = mean / cost
        report["modes"][mode] = {"books": len(records), "meanX": float(mean), "rtp": float(rtp),
                                  "exactRtp": str(rtp), "groups": details}
    return report
