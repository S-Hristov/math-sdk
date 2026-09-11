"""Fast deterministic contract checks for Veggie Salad math."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from math_targets import (
    BASE_TRIGGER_RATE,
    CHANCE_TRIGGER_RATE,
    MAX_WIN_AMOUNT,
    MODE_GROUP_TARGET_MEANS,
    MODE_TARGET_MEANS,
    TIER_TARGET_MEANS,
)
from game_config import GameConfig
from veggie_math import (
    GRID_SIZES,
    MULTIPLIER_CAP,
    PAYTABLE,
    evaluate_clusters,
    generate_round_for_mode,
    get_clusters,
    pay_for_cluster,
    position,
    retrigger_spins_for_scatter_count,
    tier_for_scatter_count,
)


def board(size: int, fill: str = "ONION"):
    # Checker-like background prevents accidental large connected components.
    names = (fill, "PEPPER", "CARROT", "EGGPLANT")
    return [[{"name": names[(reel + row) % len(names)]} for row in range(size)] for reel in range(size)]


# Exact paytable and 15+ clamp.
assert PAYTABLE["BROCCOLI"][5] == 1.00
assert PAYTABLE["BROCCOLI"][15] == 150.00
assert PAYTABLE["ONION"][5] == 0.20
assert PAYTABLE["ONION"][15] == 20.00
assert pay_for_cluster("BROCCOLI", 99) == 15_000

# Orthogonal five pays; diagonal-only five does not connect.
orthogonal = board(7)
for reel, row in ((1, 1), (1, 2), (1, 3), (2, 2), (3, 2)):
    orthogonal[reel][row] = {"name": "BROCCOLI"}
clusters = [item for item in get_clusters(orthogonal) if item["symbol"] == "BROCCOLI"]
assert len(clusters) == 1 and len(clusters[0]["positions"]) == 5

diagonal = board(7)
for reel, row in ((0, 0), (1, 1), (2, 2), (3, 3), (4, 4)):
    diagonal[reel][row] = {"name": "BROCCOLI"}
assert not [item for item in get_clusters(diagonal) if item["symbol"] == "BROCCOLI"]

# Separate same-symbol blocks remain separate.
separate = board(10)
for offset in (0, 5):
    for reel, row in ((offset, 0), (offset, 1), (offset, 2), (offset + 1, 1), (offset + 2, 1)):
        separate[reel][row] = {"name": "TOMATO"}
tomato_clusters = [item for item in get_clusters(separate) if item["symbol"] == "TOMATO"]
assert sorted(len(item["positions"]) for item in tomato_clusters) == [5, 5]

# Multipliers multiply, never add, and clamp at 256x.
multiplier_board = board(7)
positions = [position(0, row) for row in range(5)]
for item in positions:
    multiplier_board[item["reel"]][item["row"]] = {"name": "BROCCOLI", "multiplier": 4}
win = evaluate_clusters(
    multiplier_board,
    [{"symbol": "BROCCOLI", "positions": positions}],
    MAX_WIN_AMOUNT,
)[0]
assert win["rawMultiplier"] == 4**5
assert win["appliedMultiplier"] == MULTIPLIER_CAP
assert win["amount"] == 100 * 256

# Locked grids, tier mapping and retriggers.
assert GRID_SIZES == {"basegame": 7, "feature": 7, "normal": 8, "super": 9, "hidden": 10}
assert [tier_for_scatter_count(count) for count in (2, 3, 4, 5, 8)] == [None, "normal", "super", "hidden", "hidden"]
assert [retrigger_spins_for_scatter_count(count) for count in (2, 3, 4, 5, 6, 7, 9)] == [0, 10, 11, 12, 13, 14, 14]

# Feature Spin always starts with a qualifying cluster; all mode max books reach exactly 25,000x.
for seed in range(100):
    feature = generate_round_for_mode("FEATURE", seed, "feature")
    first_reveal = next(event for event in feature["events"] if event["type"] == "reveal")
    assert get_clusters(first_reveal["board"])
    assert feature["final_amount"] > 0

for mode in ("BASE", "CHANCE", "FEATURE", "BONUS", "MYSTERY", "SUPER"):
    result = generate_round_for_mode(mode, 0, "max")
    assert result["final_amount"] == MAX_WIN_AMOUNT
    assert any(event["type"] == "maxWinReached" for event in result["events"])

# Seeds are replay-stable; tail fences keep each paid bonus target bracketed.
assert generate_round_for_mode("BASE", 4242, "basegame") == generate_round_for_mode(
    "BASE", 4242, "basegame"
)
for mode, criteria, minimum in (
    ("BONUS", "tail_normal", 9_610),
    ("SUPER", "tail_super", 38_440),
    ("MYSTERY", "tail_hidden", 115_320),
):
    assert generate_round_for_mode(mode, 9, criteria)["final_amount"] >= minimum

# Every natural tier and direct tier has the locked dimensions and trigger route.
for criteria, expected_size in (("normal", 8), ("super", 9), ("hidden", 10)):
    result = generate_round_for_mode("BASE", 100 + expected_size, criteria)
    trigger = next(event for event in result["events"] if event["type"] == "freeSpinTrigger")
    assert trigger["tier"] == criteria and trigger["gridSize"] == expected_size

# Economic locks and exact Extra Chance relationship.
assert abs(CHANCE_TRIGGER_RATE / BASE_TRIGGER_RATE - 3.0) < 1e-12
assert TIER_TARGET_MEANS == {"normal": 96.10, "super": 384.40, "hidden": 1_153.20}
assert abs(MODE_TARGET_MEANS["MYSTERY"] - 288.30) < 1e-12
assert MODE_GROUP_TARGET_MEANS["FEATURE"]["feature"] == 19.22

config = GameConfig()
assert config.freespin_triggers[config.basegame_type][3] == 10
assert config.freespin_triggers[config.basegame_type][49] == 10

print("Veggie Salad math contract: PASS")
