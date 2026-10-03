"""Publication integrity and weighted-math validation."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path

try:
    from . import math_targets as T
    from .weight_lookups import load_books
except ImportError:
    import math_targets as T
    from weight_lookups import load_books


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_book(book: dict) -> dict:
    events = book["events"]
    require(events and events[-1]["type"] == "finalWin", "missing finalWin")
    require(all(event["index"] == index for index, event in enumerate(events)), "event index mismatch")
    require(events[-1]["amount"] == book["payoutMultiplier"], "final payout mismatch")
    require(0 <= book["payoutMultiplier"] <= T.MAX_WIN_AMOUNT, "payout outside cap")
    require(Decimal(str(book["baseGameWins"])) * 100 + Decimal(str(book["freeGameWins"])) * 100
            == book["payoutMultiplier"], "base/free payout mismatch")
    current_heat = 0
    steals = triggers = 0
    max_heat = 0
    for index, event in enumerate(events):
        kind = event["type"]
        if kind == "winInfo":
            require(event["totalWin"] == sum(win["win"] for win in event["wins"]), "winInfo sum mismatch")
            for win in event["wins"]:
                require(win["symbol"] in T.SYMBOLS and len(win["positions"]) >= T.MIN_CLUSTER,
                        "invalid cluster win")
                require(win["meta"]["globalMult"] in T.HEAT, "invalid Heat multiplier")
        elif kind == "steal":
            steals += 1
            heat = event["heat"]
            require(0 <= heat["level"] < len(T.HEAT), "invalid Heat level")
            require(heat["multiplier"] == T.HEAT[heat["level"]], "Heat ladder mismatch")
            require(len(event["nearMiss"]) + 1 >= T.MIN_CLUSTER, "steal cannot complete cluster")
            require(index + 1 < len(events) and events[index + 1] == {
                "index": index + 1, "type": "updateGlobalMult", "globalMult": heat["multiplier"]},
                "steal Heat event mismatch")
            current_heat = heat["level"]
            max_heat = max(max_heat, current_heat)
        elif kind == "freeSpinTrigger":
            triggers += 1
            require(event["totalFs"] == T.FREE_SPINS, "incorrect initial free spins")
        elif kind == "freeSpinRetrigger":
            require(event["totalFs"] >= T.FREE_SPINS + T.RETRIGGER_SPINS, "bad retrigger total")
    return {"steals": steals, "triggered": triggers > 0, "maxHeatLevel": max_heat}


def validate_library(library: Path, expected_count: int) -> dict:
    index = json.loads((library / "publish_files/index.json").read_text())
    require([row["name"] for row in index["modes"]] == list(T.MODE_COSTS), "mode order mismatch")
    results = {}
    blockers = []
    for mode_row in index["modes"]:
        mode = mode_row["name"]
        books = load_books(library / "publish_files" / mode_row["events"])
        lookup = [tuple(map(int, line.split(","))) for line in
                  (library / "publish_files" / mode_row["weights"]).read_text().splitlines() if line]
        require(len(books) == len(lookup) == expected_count, f"{mode}: book count mismatch")
        total_weight = weighted = hit_weight = trigger_weight = steal_weight = cap_weight = 0
        heat = Counter()
        distinct = set()
        for index, (book, row) in enumerate(zip(books, lookup)):
            book_id, weight, payout = row
            require(book_id == book["id"] == index and payout == book["payoutMultiplier"],
                    f"{mode}/{index}: lookup alignment")
            require(weight > 0, f"{mode}/{index}: non-positive weight")
            metrics = validate_book(book)
            digest = json.dumps(book["events"], sort_keys=True, separators=(",", ":"))
            require(digest not in distinct, f"{mode}/{index}: duplicate event path")
            distinct.add(digest)
            total_weight += weight
            weighted += weight * payout
            hit_weight += weight * (payout > 0)
            trigger_weight += weight * metrics["triggered"]
            steal_weight += weight * (metrics["steals"] > 0)
            cap_weight += weight * (payout == T.MAX_WIN_AMOUNT)
            heat[metrics["maxHeatLevel"]] += weight
        require(total_weight == T.LOOKUP_SCALE, f"{mode}: lookup total")
        mean = Fraction(weighted, total_weight * T.BOOK_SCALE)
        rtp = mean / T.MODE_COSTS[mode]
        if abs(rtp - T.MODE_RTPS[mode]) > Fraction(1, 100_000):
            blockers.append(f"{mode}: RTP {float(rtp):.6%} != {float(T.MODE_RTPS[mode]):.6%}")
        if Fraction(cap_weight, total_weight) != T.MAX_WIN_RATE:
            blockers.append(f"{mode}: max-win probability mismatch")
        if mode in T.NATURAL_TRIGGER_RATES and trigger_weight != round(T.NATURAL_TRIGGER_RATES[mode] * total_weight):
            blockers.append(f"{mode}: trigger-rate mismatch")
        if mode in T.BASE_HIT_RATES and Fraction(hit_weight, total_weight) != T.BASE_HIT_RATES[mode]:
            blockers.append(f"{mode}: hit-rate mismatch")
        if mode in T.BASE_HIT_RATES and Fraction(steal_weight, total_weight) != T.BASE_STEAL_VISIBLE_RATE:
            blockers.append(f"{mode}: steal visible-rate mismatch")
        thresholds = {}
        if mode == "superspin":
            threshold10 = Fraction(sum(weight for book, (_, weight, _) in zip(books, lookup)
                                       if book["payoutMultiplier"] >= 1_000), total_weight)
            threshold100 = Fraction(sum(weight for book, (_, weight, _) in zip(books, lookup)
                                        if book["payoutMultiplier"] >= 10_000), total_weight)
            thresholds = {"payoutAtLeast10x": float(threshold10), "payoutAtLeast100x": float(threshold100)}
            if threshold10 != T.SUPERSPIN_BANDS["10to100"] + T.SUPERSPIN_BANDS["100plus"]:
                blockers.append("superspin: >=10x probability mismatch")
            if threshold100 != T.SUPERSPIN_BANDS["100plus"]:
                blockers.append("superspin: >=100x probability mismatch")
        results[mode] = {"books": len(books), "uniqueEventPaths": len(distinct), "meanX": float(mean),
                         "rtp": float(rtp), "exactRtp": str(rtp),
                         "hitRate": hit_weight / total_weight, "triggerRate": trigger_weight / total_weight,
                         "stealVisibleRate": steal_weight / total_weight,
                         "maxWinProbability": cap_weight / total_weight,
                         "heatLevelProbabilities": {str(level): weight / total_weight for level, weight in sorted(heat.items())},
                         **thresholds}
    passed_status = f"weighted_math_gates_passed_preliminary_{expected_count}_books_per_mode"
    return {"status": "math_gates_failed" if blockers else passed_status,
            "modelVersion": T.MODEL_VERSION, "modes": results, "blockers": blockers,
            "notice": f"{expected_count} candidates per mode are integration artifacts, not statistical sign-off."}
