"""Deterministic Veggie Salad cluster, tumble, multiplier and bonus model.

Amounts use Stake book units: 100 == 1x selected base stake.
"""

from __future__ import annotations

import random
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from math_targets import MAX_WIN_AMOUNT, MAX_WIN_X

PAY_SYMBOLS = (
    "BROCCOLI",
    "CORN",
    "TOMATO",
    "EGGPLANT",
    "CARROT",
    "PEPPER",
    "ONION",
)
SCATTER = "SCATTER"

# Exact locked GDD paytable, expressed in x base stake.
PAYTABLE = {
    "BROCCOLI": {5: 1.00, 6: 1.50, 7: 1.75, 8: 2.00, 9: 2.50, 10: 5.00, 11: 7.50, 12: 15.00, 13: 35.00, 14: 70.00, 15: 150.00},
    "CORN": {5: 0.75, 6: 1.00, 7: 1.25, 8: 1.50, 9: 2.00, 10: 4.00, 11: 6.00, 12: 12.50, 13: 30.00, 14: 60.00, 15: 100.00},
    "TOMATO": {5: 0.50, 6: 0.75, 7: 1.00, 8: 1.25, 9: 1.50, 10: 3.00, 11: 4.50, 12: 10.00, 13: 25.00, 14: 50.00, 15: 90.00},
    "EGGPLANT": {5: 0.40, 6: 0.50, 7: 0.75, 8: 1.00, 9: 1.25, 10: 2.00, 11: 3.00, 12: 5.00, 13: 20.00, 14: 40.00, 15: 80.00},
    "CARROT": {5: 0.30, 6: 0.40, 7: 0.50, 8: 0.75, 9: 1.00, 10: 1.50, 11: 2.50, 12: 3.50, 13: 15.00, 14: 30.00, 15: 60.00},
    "PEPPER": {5: 0.25, 6: 0.30, 7: 0.40, 8: 0.50, 9: 0.75, 10: 1.25, 11: 2.00, 12: 3.00, 13: 10.00, 14: 20.00, 15: 40.00},
    "ONION": {5: 0.20, 6: 0.25, 7: 0.30, 8: 0.40, 9: 0.50, 10: 1.00, 11: 1.50, 12: 2.50, 13: 5.00, 14: 10.00, 15: 20.00},
}

GRID_SIZES = {"basegame": 7, "feature": 7, "normal": 8, "super": 9, "hidden": 10}
# Scatters that trigger each tier. A bought bonus lands exactly these on its entry spin, which is
# also how a MYSTERY buy announces the tier it rolled: the player counts the Scatters.
TRIGGER_SCATTERS = {"normal": 3, "super": 4, "hidden": 5}
STARTING_FREE_SPINS = 10
RETRIGGER_SPINS = {3: 10, 4: 11, 5: 12, 6: 13, 7: 14}
MAX_TUMBLES = 80
MAX_FREE_SPINS = 100
MULTIPLIER_CAP = 256

# TUNABLE prototype weights. Locked values/rules live above; these are intentionally isolated.
MODE_SETTINGS = {
    "basegame": {
        "symbol_weights": (8, 10, 11, 12, 14, 16, 18),
        "scatter_probability": 0.0050,
        "multiplier_probability": 0.012,
        "multiplier_values": (2,),
        "multiplier_weights": (1,),
    },
    "feature": {
        "symbol_weights": (8, 10, 11, 12, 14, 16, 18),
        "scatter_probability": 0.0,
        "multiplier_probability": 0.075,
        "multiplier_values": (2,),
        "multiplier_weights": (1,),
    },
    "normal": {
        "symbol_weights": (4, 6, 8, 10, 12, 14, 28),
        "scatter_probability": 0.0040,
        "multiplier_probability": 0.240,
        "multiplier_values": (2, 4),
        "multiplier_weights": (4, 1),
    },
    "super": {
        "symbol_weights": (4, 6, 8, 10, 12, 14, 28),
        "scatter_probability": 0.0037,
        "multiplier_probability": 0.240,
        "multiplier_values": (2, 4),
        "multiplier_weights": (4, 1),
    },
    "hidden": {
        "symbol_weights": (4, 6, 8, 10, 12, 14, 28),
        "scatter_probability": 0.0034,
        "multiplier_probability": 0.240,
        "multiplier_values": (2, 4),
        "multiplier_weights": (4, 1),
    },
}

Position = dict[str, int]
RawSymbol = dict[str, Any]
Board = list[list[RawSymbol]]


@dataclass
class SettleResult:
    board: Board
    amount: int
    max_scatter_count: int
    scatter_positions: list[Position]
    tumbles: int
    capped: bool


def position(reel: int, row: int) -> Position:
    return {"reel": reel, "row": row}


def position_key(item: Position) -> tuple[int, int]:
    return int(item["reel"]), int(item["row"])


def append_event(events: list[dict], event_type: str, **payload: Any) -> None:
    events.append({"index": len(events), "type": event_type, **payload})


def clone_board(board: Board) -> Board:
    return deepcopy(board)


def neighbours(reel: int, row: int, size: int) -> Iterable[tuple[int, int]]:
    for next_reel, next_row in ((reel - 1, row), (reel + 1, row), (reel, row - 1), (reel, row + 1)):
        if 0 <= next_reel < size and 0 <= next_row < size:
            yield next_reel, next_row


def get_clusters(board: Board) -> list[dict[str, Any]]:
    size = len(board)
    visited: set[tuple[int, int]] = set()
    clusters: list[dict[str, Any]] = []
    for reel in range(size):
        for row in range(size):
            name = str(board[reel][row]["name"])
            start = (reel, row)
            if name not in PAY_SYMBOLS or start in visited:
                continue
            queue = [start]
            visited.add(start)
            component: list[Position] = []
            while queue:
                current_reel, current_row = queue.pop(0)
                component.append(position(current_reel, current_row))
                for next_reel, next_row in neighbours(current_reel, current_row, size):
                    key = (next_reel, next_row)
                    if key in visited or board[next_reel][next_row]["name"] != name:
                        continue
                    visited.add(key)
                    queue.append(key)
            if len(component) >= 5:
                clusters.append({"symbol": name, "positions": component})
    return sorted(
        clusters,
        key=lambda item: (PAY_SYMBOLS.index(item["symbol"]), position_key(item["positions"][0])),
    )


def scatter_positions(board: Board) -> list[Position]:
    return [
        position(reel, row)
        for reel, column in enumerate(board)
        for row, cell in enumerate(column)
        if cell["name"] == SCATTER
    ]


def tier_for_scatter_count(count: int) -> Optional[str]:
    if count >= 5:
        return "hidden"
    if count == 4:
        return "super"
    if count == 3:
        return "normal"
    return None


def retrigger_spins_for_scatter_count(count: int) -> int:
    if count < 3:
        return 0
    return RETRIGGER_SPINS[min(count, 7)]


def pay_for_cluster(symbol: str, cluster_size: int) -> int:
    tier = min(max(5, cluster_size), 15)
    return int(round(PAYTABLE[symbol][tier] * 100))


def assign_cluster_multipliers(
    rng: random.Random,
    board: Board,
    clusters: list[dict[str, Any]],
    mode: str,
) -> None:
    settings = MODE_SETTINGS[mode]
    probability = float(settings["multiplier_probability"])
    for cluster in clusters:
        for item in cluster["positions"]:
            reel, row = position_key(item)
            cell = board[reel][row]
            if "multiplier" in cell or rng.random() >= probability:
                continue
            cell["multiplier"] = rng.choices(
                settings["multiplier_values"],
                weights=settings["multiplier_weights"],
                k=1,
            )[0]


def evaluate_clusters(board: Board, clusters: list[dict[str, Any]], remaining_cap: int) -> list[dict[str, Any]]:
    wins: list[dict[str, Any]] = []
    remaining = max(0, remaining_cap)
    for cluster_id, cluster in enumerate(clusters, start=1):
        if remaining <= 0:
            break
        multipliers = []
        for item in cluster["positions"]:
            reel, row = position_key(item)
            value = int(board[reel][row].get("multiplier", 1))
            if value > 1:
                multipliers.append(value)
        raw_multiplier = 1
        for value in multipliers:
            raw_multiplier *= value
        applied_multiplier = min(MULTIPLIER_CAP, raw_multiplier)
        raw_amount = pay_for_cluster(cluster["symbol"], len(cluster["positions"]))
        amount = min(remaining, raw_amount * applied_multiplier)
        if amount <= 0:
            continue
        wins.append(
            {
                "clusterId": f"cluster-{cluster_id}",
                "symbol": cluster["symbol"],
                "size": len(cluster["positions"]),
                "positions": deepcopy(cluster["positions"]),
                "rawAmount": raw_amount,
                "multiplierValues": multipliers,
                "rawMultiplier": raw_multiplier,
                "appliedMultiplier": applied_multiplier,
                "amount": amount,
            }
        )
        remaining -= amount
    return wins


def _pick_pay_symbol(rng: random.Random, mode: str) -> str:
    return rng.choices(PAY_SYMBOLS, weights=MODE_SETTINGS[mode]["symbol_weights"], k=1)[0]


def _new_symbol(rng: random.Random, mode: str, allow_scatter: bool = True) -> RawSymbol:
    if allow_scatter and rng.random() < float(MODE_SETTINGS[mode]["scatter_probability"]):
        return {"name": SCATTER, "scatter": True}
    return {"name": _pick_pay_symbol(rng, mode)}


def make_board(
    rng: random.Random,
    mode: str,
    *,
    allow_scatter: bool = True,
    forced_scatter_count: int = 0,
) -> Board:
    size = GRID_SIZES[mode]
    board = [
        [_new_symbol(rng, mode, allow_scatter=allow_scatter and forced_scatter_count == 0) for _ in range(size)]
        for _ in range(size)
    ]
    if forced_scatter_count:
        chosen = rng.sample(range(size * size), forced_scatter_count)
        for index in chosen:
            reel, row = divmod(index, size)
            board[reel][row] = {"name": SCATTER, "scatter": True}
    return board


def connected_positions(rng: random.Random, size: int, count: int) -> list[Position]:
    start = (rng.randrange(size), rng.randrange(size))
    selected = {start}
    frontier = set(neighbours(*start, size))
    while len(selected) < count:
        choice = rng.choice(sorted(frontier))
        frontier.remove(choice)
        selected.add(choice)
        frontier.update(item for item in neighbours(*choice, size) if item not in selected)
    return [position(reel, row) for reel, row in sorted(selected)]


def force_connected_cluster(rng: random.Random, board: Board, mode: str, count: Optional[int] = None) -> None:
    size = len(board)
    cluster_size = count if count is not None else rng.choices((5, 6, 7, 8, 9, 10), (35, 25, 16, 10, 8, 6), k=1)[0]
    symbol = rng.choices(PAY_SYMBOLS, weights=MODE_SETTINGS[mode]["symbol_weights"], k=1)[0]
    for item in connected_positions(rng, size, cluster_size):
        reel, row = position_key(item)
        board[reel][row] = {"name": symbol}


def tumble_board(rng: random.Random, board: Board, removed: list[Position], mode: str) -> Board:
    removed_keys = {position_key(item) for item in removed}
    size = len(board)
    next_board: Board = []
    for reel, column in enumerate(board):
        survivors = [cell for row, cell in enumerate(column) if (reel, row) not in removed_keys]
        missing = size - len(survivors)
        next_board.append([_new_symbol(rng, mode) for _ in range(missing)] + deepcopy(survivors))
    return next_board


def settle_grid(
    rng: random.Random,
    events: list[dict],
    board: Board,
    mode: str,
    round_total_before: int,
) -> SettleResult:
    sequence_amount = 0
    max_scatters = 0
    max_scatter_positions: list[Position] = []
    tumbles = 0

    while True:
        clusters = get_clusters(board)
        assign_cluster_multipliers(rng, board, clusters, mode)
        current_scatter_positions = scatter_positions(board)
        if len(current_scatter_positions) > max_scatters:
            max_scatters = len(current_scatter_positions)
            max_scatter_positions = deepcopy(current_scatter_positions)

        append_event(
            events,
            "reveal",
            board=clone_board(board),
            gridSize=len(board),
            cascadeIndex=tumbles,
            gameType=mode,
            paddingPositions=[],
            anticipation=[0] * len(board),
        )

        if not clusters:
            break

        remaining_cap = MAX_WIN_AMOUNT - round_total_before - sequence_amount
        wins = evaluate_clusters(board, clusters, remaining_cap)
        step_amount = sum(win["amount"] for win in wins)
        if step_amount <= 0:
            break

        sequence_amount += step_amount
        append_event(
            events,
            "clusterWin",
            cascadeIndex=tumbles,
            wins=wins,
            totalWin=step_amount,
        )
        append_event(events, "setTotalWin", amount=round_total_before + sequence_amount)

        if round_total_before + sequence_amount >= MAX_WIN_AMOUNT:
            append_event(
                events,
                "maxWinReached",
                precapTotal=sum(win["rawAmount"] * win["appliedMultiplier"] for win in wins),
                awardedTotal=MAX_WIN_AMOUNT,
            )
            return SettleResult(board, sequence_amount, max_scatters, max_scatter_positions, tumbles, True)

        removed = [item for win in wins for item in win["positions"]]
        append_event(events, "tumbleRemove", positions=deepcopy(removed), cascadeIndex=tumbles)
        board = tumble_board(rng, board, removed, mode)
        tumbles += 1
        if tumbles >= MAX_TUMBLES:
            append_event(events, "cascadeSafetyStop", limit=MAX_TUMBLES)
            break

    return SettleResult(board, sequence_amount, max_scatters, max_scatter_positions, tumbles, False)


def _break_clusters(rng: random.Random, board: Board) -> None:
    """Repaint cells until no orthogonal 5+ cluster remains.

    The bonus-entry spin exists for presentation only, so it must not pay: any win it produced
    would land outside the mode's RTP model, which is built from the free spins alone.
    """
    size = len(board)
    for _ in range(200):
        clusters = get_clusters(board)
        if not clusters:
            return
        for cluster in clusters:
            reel, row = position_key(cluster["positions"][len(cluster["positions"]) // 2])
            banned = {board[next_reel][next_row]["name"] for next_reel, next_row in neighbours(reel, row, size)}
            options = [name for name in PAY_SYMBOLS if name not in banned]
            board[reel][row] = {"name": rng.choice(options or list(PAY_SYMBOLS))}


def _bonus_entry_spin(rng: random.Random, events: list[dict], tier: str) -> list[Position]:
    """One ordinary base-game reveal that lands the Scatters which trigger `tier`.

    A bought bonus used to open on the trigger event with no board behind it, so the front end had
    to invent one — the round jumped straight to the placard and the player never saw the Scatters
    they had paid for. This emits the spin that would have triggered the bonus naturally: same
    7x7 base board, exactly TRIGGER_SCATTERS[tier] Scatters, and no paying cluster, so the round's
    payout is still the free spins alone.
    """
    count = TRIGGER_SCATTERS[tier]
    board = make_board(rng, "basegame", allow_scatter=False, forced_scatter_count=count)
    _break_clusters(rng, board)
    positions = scatter_positions(board)
    append_event(
        events,
        "reveal",
        board=clone_board(board),
        gridSize=len(board),
        cascadeIndex=0,
        gameType="basegame",
        paddingPositions=[],
        anticipation=[0] * len(board),
    )
    return positions


def _feature_trigger_event(
    events: list[dict], tier: str, source: str, scatter_count: int, positions: list[Position]
) -> None:
    append_event(
        events,
        "freeSpinTrigger",
        tier=tier,
        source=source,
        scatterCount=scatter_count,
        positions=deepcopy(positions),
        totalFs=STARTING_FREE_SPINS,
        gridSize=GRID_SIZES[tier],
    )


def play_bonus(
    rng: random.Random,
    events: list[dict],
    tier: str,
    round_total_before: int,
) -> tuple[int, bool, int]:
    bonus_amount = 0
    spins_total = STARTING_FREE_SPINS
    spin_index = 0
    total_tumbles = 0
    capped = False

    while spin_index < spins_total and spin_index < MAX_FREE_SPINS:
        append_event(
            events,
            "updateFreeSpin",
            amount=spin_index,
            total=spins_total,
            tier=tier,
        )
        board = make_board(rng, tier)
        settled = settle_grid(rng, events, board, tier, round_total_before + bonus_amount)
        bonus_amount += settled.amount
        total_tumbles += settled.tumbles
        capped = settled.capped
        if capped:
            break

        added_spins = retrigger_spins_for_scatter_count(settled.max_scatter_count)
        if added_spins:
            spins_total += added_spins
            append_event(
                events,
                "retrigger",
                tier=tier,
                scatterCount=settled.max_scatter_count,
                spinsAdded=added_spins,
                total=spins_total,
                positions=deepcopy(settled.scatter_positions),
            )
        spin_index += 1

    if spin_index >= MAX_FREE_SPINS and spin_index < spins_total:
        append_event(events, "freeSpinSafetyStop", limit=MAX_FREE_SPINS)
    append_event(
        events,
        "freeSpinEnd",
        tier=tier,
        amount=round_total_before + bonus_amount,
        spinsPlayed=min(spin_index + int(capped), spins_total),
        totalSpinsAwarded=spins_total,
    )
    return bonus_amount, capped, total_tumbles


def _win_level(amount: int) -> int:
    value = amount / 100
    if value <= 0:
        return 1
    for level, threshold in enumerate((2, 5, 10, 20, 50, 100, 250, 1_000), start=2):
        if value < threshold:
            return level
    return 10


def _finalize(events: list[dict], amount: int) -> None:
    append_event(events, "setWin", amount=amount, winLevel=_win_level(amount))
    append_event(events, "finalWin", amount=amount)


def _generate_natural_round(rng: random.Random, forced_tier: Optional[str] = None) -> dict[str, Any]:
    forced_scatter_count = TRIGGER_SCATTERS[forced_tier] if forced_tier else 0
    board = make_board(
        rng,
        "basegame",
        allow_scatter=True,
        forced_scatter_count=forced_scatter_count,
    )
    events: list[dict] = []
    settled = settle_grid(rng, events, board, "basegame", 0)
    basegame_win = settled.amount
    trigger_tier = tier_for_scatter_count(settled.max_scatter_count)
    freegame_win = 0
    total_tumbles = settled.tumbles
    if trigger_tier and not settled.capped:
        _feature_trigger_event(
            events,
            trigger_tier,
            "natural",
            settled.max_scatter_count,
            settled.scatter_positions,
        )
        freegame_win, _capped, bonus_tumbles = play_bonus(rng, events, trigger_tier, basegame_win)
        total_tumbles += bonus_tumbles
    final_amount = min(MAX_WIN_AMOUNT, basegame_win + freegame_win)
    _finalize(events, final_amount)
    return {
        "events": events,
        "final_amount": final_amount,
        "basegame_win": basegame_win,
        "freegame_win": freegame_win,
        "trigger_tier": trigger_tier,
        "tumbles": total_tumbles,
    }


def _generate_feature_spin(rng: random.Random) -> dict[str, Any]:
    events: list[dict] = []
    append_event(events, "featureSpinStart", cost=20, gridSize=7)
    board = make_board(rng, "feature", allow_scatter=False)
    force_connected_cluster(rng, board, "feature")
    settled = settle_grid(rng, events, board, "feature", 0)
    _finalize(events, settled.amount)
    return {
        "events": events,
        "final_amount": settled.amount,
        "basegame_win": settled.amount,
        "freegame_win": 0,
        "trigger_tier": "feature",
        "tumbles": settled.tumbles,
    }


def _generate_direct_bonus(rng: random.Random, tier: str, source: str) -> dict[str, Any]:
    events: list[dict] = []
    # Entry spin first: the Scatters land, and only then is the tier named. For MYSTERY that order
    # matters — the count IS the reveal of what was rolled, so mysterySelect carries the same
    # Scatter payload the trigger does and the front end can celebrate it before the placard.
    positions = _bonus_entry_spin(rng, events, tier)
    if source == "mystery":
        append_event(
            events,
            "mysterySelect",
            tier=tier,
            gridSize=GRID_SIZES[tier],
            scatterCount=len(positions),
            positions=deepcopy(positions),
        )
    _feature_trigger_event(events, tier, source, len(positions), positions)
    freegame_win, _capped, tumbles = play_bonus(rng, events, tier, 0)
    _finalize(events, freegame_win)
    return {
        "events": events,
        "final_amount": freegame_win,
        "basegame_win": 0,
        "freegame_win": freegame_win,
        "trigger_tier": tier,
        "tumbles": tumbles,
    }


def _max_win_round(mode: str, tier_override: Optional[str] = None) -> dict[str, Any]:
    tier = tier_override or {
        "BONUS": "normal",
        "SUPER": "super",
        "MYSTERY": "hidden",
    }.get(mode)
    game_type = tier or ("feature" if mode == "FEATURE" else "basegame")
    size = GRID_SIZES[game_type]
    background_symbols = PAY_SYMBOLS[1:]
    board = [
        [
            {"name": background_symbols[(reel + row * 2) % len(background_symbols)]}
            for row in range(size)
        ]
        for reel in range(size)
    ]
    cluster_positions = [position(reel, row) for reel in range(3) for row in range(5)]
    for item in cluster_positions:
        reel, row = position_key(item)
        board[reel][row] = {"name": "BROCCOLI"}
    multiplier_values = (4, 4, 4, 4) if tier else (2,) * 8
    for item, multiplier in zip(cluster_positions, multiplier_values):
        reel, row = position_key(item)
        board[reel][row]["multiplier"] = multiplier

    events: list[dict] = []
    if mode == "MYSTERY":
        append_event(events, "mysterySelect", tier=tier, gridSize=GRID_SIZES[tier])
    if tier:
        source = "mystery" if mode == "MYSTERY" else ("natural" if mode in ("BASE", "CHANCE") else "buy")
        _feature_trigger_event(events, tier, source, 0, [])
        append_event(events, "updateFreeSpin", amount=0, total=10, tier=tier)
    elif mode == "FEATURE":
        append_event(events, "featureSpinStart", cost=20, gridSize=7)

    append_event(
        events,
        "reveal",
        board=board,
        gridSize=size,
        cascadeIndex=0,
        gameType=game_type,
        paddingPositions=[],
        anticipation=[0] * size,
    )
    raw_multiplier = 256
    append_event(
        events,
        "clusterWin",
        cascadeIndex=0,
        wins=[
            {
                "clusterId": "cluster-1",
                "symbol": "BROCCOLI",
                "size": 15,
                "positions": cluster_positions,
                "rawAmount": 15_000,
                "multiplierValues": list(multiplier_values),
                "rawMultiplier": raw_multiplier,
                "appliedMultiplier": MULTIPLIER_CAP,
                "amount": MAX_WIN_AMOUNT,
            }
        ],
        totalWin=MAX_WIN_AMOUNT,
    )
    append_event(events, "setTotalWin", amount=MAX_WIN_AMOUNT)
    append_event(
        events,
        "maxWinReached",
        precapTotal=15_000 * raw_multiplier,
        awardedTotal=MAX_WIN_AMOUNT,
    )
    if tier:
        append_event(events, "freeSpinEnd", tier=tier, amount=MAX_WIN_AMOUNT, spinsPlayed=1, totalSpinsAwarded=10)
    _finalize(events, MAX_WIN_AMOUNT)
    return {
        "events": events,
        "final_amount": MAX_WIN_AMOUNT,
        "basegame_win": 0 if tier else MAX_WIN_AMOUNT,
        "freegame_win": MAX_WIN_AMOUNT if tier else 0,
        "trigger_tier": tier or ("feature" if mode == "FEATURE" else None),
        "tumbles": 0,
    }


def _matches_criteria(result: dict[str, Any], criteria: str) -> bool:
    tier = result["trigger_tier"]
    if criteria == "0":
        return tier is None and result["final_amount"] == 0
    if criteria == "basegame":
        return tier is None and result["basegame_win"] > 0
    if criteria in ("normal", "super", "hidden"):
        return tier == criteria
    if criteria == "feature":
        return tier == "feature" and result["basegame_win"] > 0
    return True


def generate_round_for_mode(mode: str, seed: int, criteria: str) -> dict[str, Any]:
    if criteria == "max":
        return _max_win_round(mode)

    tail_tier = criteria.removeprefix("tail_") if criteria.startswith("tail_") else None
    target_amount = {
        "normal": 9_610,
        "super": 38_440,
        "hidden": 115_320,
    }.get(tail_tier)

    for attempt in range(10_000 if tail_tier else 2_000):
        rng = random.Random(seed + attempt * 1_000_003)
        if mode in ("BASE", "CHANCE"):
            forced_tier = tail_tier or (criteria if criteria in ("normal", "super", "hidden") else None)
            result = _generate_natural_round(rng, forced_tier)
        elif mode == "FEATURE":
            result = _generate_feature_spin(rng)
        elif mode == "BONUS":
            result = _generate_direct_bonus(rng, "normal", "buy")
        elif mode == "SUPER":
            result = _generate_direct_bonus(rng, "super", "buy")
        elif mode == "MYSTERY":
            tier = tail_tier or (criteria if criteria in ("normal", "super", "hidden") else "normal")
            result = _generate_direct_bonus(rng, tier, "mystery")
        else:
            raise ValueError(f"unsupported mode: {mode}")
        if tail_tier and result["trigger_tier"] == tail_tier and result["final_amount"] >= target_amount:
            result["criteria"] = criteria
            return result
        if not tail_tier and _matches_criteria(result, criteria):
            result["criteria"] = criteria
            return result
    raise RuntimeError(f"could not generate {mode}/{criteria} after 2000 deterministic attempts")


assert MAX_WIN_AMOUNT == MAX_WIN_X * 100
