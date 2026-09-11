"""Magnetic 2: Mothership prototype math engine for math-sdk."""

from __future__ import annotations

from copy import deepcopy
import math
import random
from typing import Dict, List, Optional, Tuple

BOARD_REELS = 7
BOARD_ROWS = 7
TOTAL_FS = 10
FEATURE_FS = 1
MAX_WIN_X = 20000
MAX_WIN_AMOUNT = MAX_WIN_X * 100
MAX_SEQUENCE_RESPINS_SAFETY = 64
MAGNET_MIN_CLUSTER_SIZE = 5  # magnet cluster must reach this to lock and pay
POLARITY_DIRECTIONS = ('LEFT', 'RIGHT', 'UP', 'DOWN')
MYSTERY_BONUS_WEIGHTS = (('BONUS', 70), ('SUPER', 25), ('HIDDEN', 5))

PAY_SYMBOLS = ['H1', 'H2', 'H3', 'H4', 'L1', 'L2', 'L3', 'L4']
SYMBOL_WEIGHTS = [('L4', 12), ('L3', 12), ('L2', 12), ('L1', 11), ('H4', 11), ('H3', 10), ('H2', 10), ('H1', 10)]
MAGNET_MULTIPLIER_VALUES = {
    # More multiplier reveals, lower conditional mix.  Keeps feel up while lookup
    # weighting holds RTP / broad payout distribution near target.
    'BASE':    [(2, 55), (3, 30), (4, 10), (5, 4), (7, 1)],
    'CHANCE':  [(2, 54), (3, 30), (4, 11), (5, 4), (7, 1)],
    'FEATURE': [(2, 52), (3, 30), (4, 12), (5, 5), (7, 1)],
    'BONUS':   [(2, 52), (3, 30), (4, 12), (5, 5), (7, 1)],
    'SUPER':   [(2, 46), (3, 28), (4, 14), (5, 8), (7, 3), (10, 1)],
    'HIDDEN':  [(2, 42), (3, 29), (4, 15), (5, 9), (7, 4), (10, 1)],
}
PAYTABLE_BANDS: Dict[str, List[Tuple[int, int, float]]] = {
    'H1': [(5, 5, 0.5), (6, 6, 1), (7, 7, 2), (8, 8, 4), (9, 9, 8), (10, 11, 15), (12, 14, 30), (15, 19, 75), (20, 24, 200), (25, 29, 500), (30, 32, 1000), (33, 49, 2000)],
    'H2': [(5, 5, 0.4), (6, 6, 0.8), (7, 7, 1.5), (8, 8, 3), (9, 9, 6), (10, 11, 12), (12, 14, 25), (15, 19, 60), (20, 24, 150), (25, 29, 350), (30, 32, 750), (33, 49, 1500)],
    'H3': [(5, 5, 0.3), (6, 6, 0.6), (7, 7, 1.2), (8, 8, 2.5), (9, 9, 5), (10, 11, 10), (12, 14, 20), (15, 19, 45), (20, 24, 120), (25, 29, 275), (30, 32, 600), (33, 49, 1200)],
    'H4': [(5, 5, 0.2), (6, 6, 0.5), (7, 7, 1), (8, 8, 2), (9, 9, 4), (10, 11, 8), (12, 14, 15), (15, 19, 35), (20, 24, 90), (25, 29, 200), (30, 32, 450), (33, 49, 900)],
    'L1': [(5, 5, 0.15), (6, 6, 0.3), (7, 7, 0.6), (8, 8, 1.2), (9, 9, 2.5), (10, 11, 5), (12, 14, 10), (15, 19, 25), (20, 24, 60), (25, 29, 125), (30, 32, 250), (33, 49, 500)],
    'L2': [(5, 5, 0.12), (6, 6, 0.25), (7, 7, 0.5), (8, 8, 1), (9, 9, 2), (10, 11, 4), (12, 14, 8), (15, 19, 20), (20, 24, 50), (25, 29, 100), (30, 32, 200), (33, 49, 400)],
    'L3': [(5, 5, 0.1), (6, 6, 0.2), (7, 7, 0.4), (8, 8, 0.8), (9, 9, 1.6), (10, 11, 3), (12, 14, 6), (15, 19, 15), (20, 24, 40), (25, 29, 80), (30, 32, 150), (33, 49, 300)],
    'L4': [(5, 5, 0.08), (6, 6, 0.15), (7, 7, 0.3), (8, 8, 0.6), (9, 9, 1.2), (10, 11, 2.5), (12, 14, 5), (15, 19, 12), (20, 24, 30), (25, 29, 60), (30, 32, 120), (33, 49, 250)],
}
MODE_SETTINGS = {
    'BASE': {'trigger_bonus_rate': 0.0004, 'trigger_super_rate': 0.00015, 'trigger_hidden_rate': 0.00003, 'magnet_spin_rate': 0.035, 'magnet_respin_rate': 0.025, 'magnet_multiplier_rate': 0.250, 'polarity_respin_rate': 0.035, 'target_boost': 0.015, 'scatter_range': (0, 2), 'wild_rate': 0.0},
    'CHANCE': {'trigger_bonus_rate': 0.0012, 'trigger_super_rate': 0.00045, 'trigger_hidden_rate': 0.00009, 'magnet_spin_rate': 0.050, 'magnet_respin_rate': 0.035, 'magnet_multiplier_rate': 0.300, 'polarity_respin_rate': 0.050, 'target_boost': 0.02, 'scatter_range': (0, 2), 'wild_rate': 0.0},
    # Every feature spin is forced to contain a paying cluster. Half start as a
    # magnet pull; half land as a natural cluster so the feature is not visually
    # or mathematically dependent on a WILD every time.
    'FEATURE': {'magnet_spin_rate': 0.5, 'magnet_respin_rate': 0.035, 'magnet_multiplier_rate': 0.200, 'polarity_respin_rate': 0.060, 'target_boost': 0.015, 'scatter_range': (0, 0), 'wild_rate': 0.0},
    'BONUS': {'magnet_spin_rate': 0.160, 'magnet_respin_rate': 0.045, 'magnet_multiplier_rate': 0.220, 'polarity_respin_rate': 0.060, 'target_boost': 0.04, 'scatter_range': (0, 0), 'wild_rate': 0.0},
    'SUPER': {'magnet_spin_rate': 0.180, 'magnet_respin_rate': 0.014, 'magnet_multiplier_rate': 0.280, 'polarity_respin_rate': 0.075, 'target_boost': -0.12, 'scatter_range': (0, 0), 'wild_rate': 0.0},
    'HIDDEN': {'magnet_spin_rate': 0.200, 'magnet_respin_rate': 0.018, 'magnet_multiplier_rate': 0.320, 'polarity_respin_rate': 0.090, 'target_boost': -0.10, 'scatter_range': (0, 0), 'wild_rate': 0.0},
}

# Base-game scatters collect only while a real cluster sequence is producing
# respins. CHANCE keeps its advertised stronger feature frequency.
RESPIN_SCATTER_RATES = {
    'BASE': 0.10,
    'CHANCE': 0.30,
}


Position = Dict[str, int]
RawSymbol = Dict[str, object]
Series = Dict[str, object]


def pos(reel: int, row: int) -> Position:
    return {'reel': reel, 'row': row}


def pos_key(position: Position) -> str:
    return f"{position['reel']}:{position['row']}"


def clone_positions(positions: List[Position]) -> List[Position]:
    return [dict(position) for position in positions]


def uniq_positions(positions: List[Position]) -> List[Position]:
    seen = set()
    out = []
    for position in positions:
        key = pos_key(position)
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(position))
    return out


def weighted_choice(rng: random.Random, entries: List[Tuple[object, float]]):
    total = sum(weight for _, weight in entries)
    roll = rng.random() * total
    for value, weight in entries:
        roll -= weight
        if roll < 0:
            return value
    return entries[-1][0]


def make_pay_symbol(name: str) -> RawSymbol:
    return {'name': name}


def make_scatter() -> RawSymbol:
    return {'name': 'SCATTER', 'scatter': True}


def make_magnet(multiplier: int = 1) -> RawSymbol:
    out: RawSymbol = {'name': 'WILD', 'magnet': True, 'wild': True}
    if multiplier > 1:
        out['multiplier'] = multiplier
    return out


def make_wild(multiplier: int = 1) -> RawSymbol:
    out: RawSymbol = {'name': 'WILD', 'wild': True}
    if multiplier > 1:
        out['multiplier'] = multiplier
    return out


def make_polarity() -> RawSymbol:
    return {'name': 'POLARITY', 'polarity': True}


def empty_board() -> List[List[RawSymbol]]:
    return [[make_pay_symbol('L4') for _ in range(BOARD_ROWS)] for _ in range(BOARD_REELS)]


def clone_board(board: List[List[RawSymbol]]) -> List[List[RawSymbol]]:
    return [[dict(cell) for cell in reel] for reel in board]


def neighbors(position: Position) -> List[Position]:
    reel = position['reel']
    row = position['row']
    out = []
    if reel > 0:
        out.append(pos(reel - 1, row))
    if reel < BOARD_REELS - 1:
        out.append(pos(reel + 1, row))
    if row > 0:
        out.append(pos(reel, row - 1))
    if row < BOARD_ROWS - 1:
        out.append(pos(reel, row + 1))
    return out


def all_positions() -> List[Position]:
    return [pos(reel, row) for reel in range(BOARD_REELS) for row in range(BOARD_ROWS)]


ALL_POSITIONS = all_positions()


def sample_positions(rng: random.Random, count: int, blocked: set[str]) -> List[Position]:
    pool = [position for position in ALL_POSITIONS if pos_key(position) not in blocked]
    out = []
    for _ in range(min(count, len(pool))):
        index = rng.randrange(len(pool))
        out.append(pool.pop(index))
    return out


def random_pay_symbol(rng: random.Random, target_symbol: Optional[str] = None, boost: float = 0.0) -> str:
    entries = []
    for symbol, weight in SYMBOL_WEIGHTS:
        if symbol == target_symbol and boost != 0:
            entries.append((symbol, weight * max(0.05, 1 + boost * 4)))
        else:
            entries.append((symbol, weight))
    return str(weighted_choice(rng, entries))


def random_scatter_count(rng: random.Random, mode: str) -> int:
    low, high = MODE_SETTINGS[mode]['scatter_range']
    return rng.randint(low, high)


def maybe_collect_respin_scatter(
    rng: random.Random,
    board: List[List[RawSymbol]],
    sticky_symbols: Dict[str, RawSymbol],
    blocked_keys: set,
    rate: float,
    max_scatter_count: int,
) -> Optional[Position]:
    """Land at most one new sticky scatter during an active cluster respin."""
    if (
        not sticky_symbols
        or len(sticky_symbols) >= max_scatter_count
        or rate <= 0
        or rng.random() >= rate
    ):
        return None

    candidates = []
    for reel in range(BOARD_REELS):
        for row in range(BOARD_ROWS):
            position = pos(reel, row)
            key = pos_key(position)
            cell = board[reel][row]
            if key in blocked_keys:
                continue
            if cell.get('scatter') or cell.get('magnet') or cell.get('wild'):
                continue
            candidates.append(position)
    if not candidates:
        return None

    position = candidates[rng.randrange(len(candidates))]
    scatter = make_scatter()
    board[position['reel']][position['row']] = scatter
    sticky_symbols[pos_key(position)] = dict(scatter)
    return position


def random_magnet_count(rng: random.Random, rate: float) -> int:
    return 1 if rng.random() < rate else 0


def random_wild_count(rng: random.Random, rate: float) -> int:
    if rng.random() >= rate:
        return 0
    return 2 if rng.random() < min(0.45, rate * 4) else 1


def random_magnet_multiplier_value(rng: random.Random, mode: str) -> int:
    return int(weighted_choice(rng, MAGNET_MULTIPLIER_VALUES[mode]))


def make_random_magnet(rng: random.Random, mode: str, force_multiplier: bool = False) -> RawSymbol:
    multiplier_rate = float(MODE_SETTINGS[mode].get('magnet_multiplier_rate', 0.0))
    multiplier = random_magnet_multiplier_value(rng, mode) if mode in MAGNET_MULTIPLIER_VALUES and (force_multiplier or rng.random() < multiplier_rate) else 1
    return make_magnet(multiplier)


def create_board(
    rng: random.Random,
    mode: str,
    scatter_count: int = 0,
    magnet_count: int = 0,
    locked_map: Optional[Dict[str, RawSymbol]] = None,
    target_symbol: Optional[str] = None,
    target_boost: float = 0.0,
    polarity_count: int = 0,
    force_multiplier_magnet: bool = False,
) -> List[List[RawSymbol]]:
    locked_map = locked_map or {}
    settings = MODE_SETTINGS[mode]
    board = empty_board()
    for reel in range(BOARD_REELS):
        for row in range(BOARD_ROWS):
            key = f'{reel}:{row}'
            if key in locked_map:
                board[reel][row] = dict(locked_map[key])
            else:
                board[reel][row] = make_pay_symbol(random_pay_symbol(rng, target_symbol, target_boost))
    scatter_positions = sample_positions(rng, scatter_count, set(locked_map.keys()))
    for position in scatter_positions:
        board[position['reel']][position['row']] = make_scatter()
    blocked = set(locked_map.keys()) | {pos_key(p) for p in scatter_positions}
    for position in sample_positions(rng, magnet_count, blocked):
        board[position['reel']][position['row']] = make_random_magnet(rng, mode, force_multiplier_magnet)
    blocked |= {pos_key(p) for p in get_magnet_positions(board)}
    for position in sample_positions(rng, polarity_count, blocked):
        board[position['reel']][position['row']] = make_polarity()
    blocked |= {pos_key(p) for p in get_polarity_positions(board)}
    for position in sample_positions(rng, random_wild_count(rng, float(settings['wild_rate'])), blocked):
        board[position['reel']][position['row']] = make_wild()
    return board


def force_scatters(board: List[List[RawSymbol]], positions: List[Position]) -> List[List[RawSymbol]]:
    out = clone_board(board)
    for position in positions:
        out[position['reel']][position['row']] = make_scatter()
    return out


def get_symbol_at(board: List[List[RawSymbol]], position: Position) -> str:
    return str(board[position['reel']][position['row']]['name'])


def compute_pull_positions(
    board: List[List[RawSymbol]],
    magnet_positions: List[Position],
    count: int,
    excluded_keys: Optional[set] = None,
    traversable_excluded_keys: Optional[set] = None,
) -> List[Position]:
    """BFS from magnet(s) outward — return the closest 'count' non-special, non-excluded positions."""
    excluded_keys = excluded_keys or set()
    traversable_excluded_keys = traversable_excluded_keys or set()
    if not magnet_positions or count == 0:
        return []
    visited: set = {pos_key(p) for p in magnet_positions}
    queue: List[Position] = list(magnet_positions)
    result: List[Position] = []
    while queue and len(result) < count:
        current = queue.pop(0)
        for neighbor in neighbors(current):
            nkey = pos_key(neighbor)
            if nkey in visited:
                continue
            visited.add(nkey)
            cell = board[neighbor['reel']][neighbor['row']]
            if cell.get('scatter') or cell.get('magnet') or cell.get('polarity') or cell.get('name') == 'POLARITY':
                # Hard obstacle.  Traversing through it can place a target on the
                # far side, producing a visually disconnected/diagonal cluster.
                continue
            if nkey in excluded_keys:
                # A magnet already absorbed into a persistent SUPER cluster must
                # be able to search through that cluster to reach its open edge.
                # Excluded cells remain unavailable as destinations.
                if nkey in traversable_excluded_keys:
                    queue.append(neighbor)
                continue
            result.append(neighbor)
            queue.append(neighbor)
    return result[:count]


def apply_magnet_pull(
    rng: random.Random,
    board: List[List[RawSymbol]],
    magnet_positions: List[Position],
    target_symbol: str,
    excluded_keys: Optional[set] = None,
    traversable_excluded_keys: Optional[set] = None,
) -> Tuple[List[List[RawSymbol]], List[Position], List[Position]]:
    """Pull target symbols toward the magnet; magnet cell stays as WILD.

    Returns (new_board, anchor_positions, bfs_positions).
    - anchor_positions: magnet cells (remain WILD in the board).
    - bfs_positions: cells filled with target_symbol adjacent to the magnet.
    - excluded_keys: positions that must not be claimed (adjacent to existing clusters).
    """
    excluded_keys = excluded_keys or set()
    original_positions: List[Position] = [
        pos(reel, row) for reel in range(BOARD_REELS) for row in range(BOARD_ROWS)
        if board[reel][row]['name'] == target_symbol and pos_key(pos(reel, row)) not in excluded_keys
    ]
    if not original_positions:
        return board, list(magnet_positions), []
    if not magnet_positions:
        return board, [], original_positions

    bfs_positions = compute_pull_positions(
        board,
        magnet_positions,
        len(original_positions),
        excluded_keys,
        traversable_excluded_keys,
    )
    if not bfs_positions:
        return board, list(magnet_positions), []

    new_board = clone_board(board)
    bfs_keys = {pos_key(p) for p in bfs_positions}
    magnet_keys = {pos_key(p) for p in magnet_positions}
    cluster_keys = bfs_keys | magnet_keys
    other_symbols = [sym for sym, _ in SYMBOL_WEIGHTS if sym != target_symbol]

    # Clear original scattered positions that didn't end up in the cluster
    for p in original_positions:
        if pos_key(p) not in cluster_keys:
            new_board[p['reel']][p['row']] = make_pay_symbol(other_symbols[rng.randrange(len(other_symbols))])

    # Fill BFS positions with target symbol; magnet positions are NOT touched (stay WILD)
    for p in bfs_positions:
        new_board[p['reel']][p['row']] = make_pay_symbol(target_symbol)

    return new_board, list(magnet_positions), bfs_positions


def get_magnet_positions(board: List[List[RawSymbol]]) -> List[Dict[str, int]]:
    out = []
    for reel in range(BOARD_REELS):
        for row in range(BOARD_ROWS):
            cell = board[reel][row]
            if cell.get('magnet'):
                out.append({'reel': reel, 'row': row})
    return out


def get_wild_positions(board: List[List[RawSymbol]]) -> List[Dict[str, int]]:
    out = []
    for reel in range(BOARD_REELS):
        for row in range(BOARD_ROWS):
            cell = board[reel][row]
            if cell['name'] == 'WILD':
                out.append({'reel': reel, 'row': row, 'multiplier': int(cell.get('multiplier', 1))})
    return out


def get_polarity_positions(board: List[List[RawSymbol]]) -> List[Position]:
    return [
        pos(reel, row)
        for reel in range(BOARD_REELS)
        for row in range(BOARD_ROWS)
        if board[reel][row].get('polarity') or board[reel][row].get('name') == 'POLARITY'
    ]


POLARITY_STEPS = {
    'LEFT': (-1, 0),
    'RIGHT': (1, 0),
    'UP': (0, -1),
    'DOWN': (0, 1),
}


def _polarity_lanes(direction: str) -> List[List[Position]]:
    """Travel lanes for a slam, each ordered wall-first.

    A symbol only ever travels along its own lane: rows for LEFT/RIGHT, reels
    for UP/DOWN. That invariant is what makes the slam readable. The previous
    wall-packing order let a single symbol change both reel and row in one step,
    which on screen looked like the board had been reshuffled at random.
    """
    if direction == 'LEFT':
        return [[pos(reel, row) for reel in range(BOARD_REELS)] for row in range(BOARD_ROWS)]
    if direction == 'RIGHT':
        return [[pos(reel, row) for reel in reversed(range(BOARD_REELS))] for row in range(BOARD_ROWS)]
    if direction == 'UP':
        return [[pos(reel, row) for row in range(BOARD_ROWS)] for reel in range(BOARD_REELS)]
    if direction == 'DOWN':
        return [[pos(reel, row) for row in reversed(range(BOARD_ROWS))] for reel in range(BOARD_REELS)]
    raise ValueError(f'unsupported polarity direction: {direction}')


def _polarity_obstacle_keys(board: List[List[RawSymbol]], mover_keys: set) -> set:
    """Cells the slam cannot move or move through.

    Scatters stay put because they are collected in place, the Polarity Shifter
    itself is the machine firing the pulse, and a magnet/wild that is not part of
    the active cluster keeps its cell so its own pull is not silently relocated.
    """
    out = set()
    for position in ALL_POSITIONS:
        key = pos_key(position)
        if key in mover_keys:
            continue
        cell = board[position['reel']][position['row']]
        if (
            cell.get('scatter')
            or cell.get('magnet')
            or cell.get('wild')
            or cell.get('polarity')
            or cell.get('name') == 'POLARITY'
        ):
            out.add(key)
    return out


def _connected_cluster(
    board: List[List[RawSymbol]],
    anchors: List[Position],
    target_symbol: str,
) -> List[Position]:
    """Flood-fill the cluster body outward from its anchors after the slam.

    A slammed symbol joins the cluster only if it actually ends up touching it.
    The old code declared every packed destination locked, so loose symbols that
    merely landed near the wall were paid as part of the cluster.
    """
    def belongs(position: Position) -> bool:
        cell = board[position['reel']][position['row']]
        return bool(cell['name'] == target_symbol or cell.get('wild'))

    seeds = [position for position in anchors if belongs(position)]
    if not seeds:
        return []
    visited = {pos_key(position) for position in seeds}
    queue = list(seeds)
    out = list(seeds)
    while queue:
        current = queue.pop(0)
        for neighbor in neighbors(current):
            key = pos_key(neighbor)
            if key in visited or not belongs(neighbor):
                continue
            visited.add(key)
            out.append(neighbor)
            queue.append(neighbor)
    return out


def apply_polarity_shift(
    board: List[List[RawSymbol]],
    series: List[Series],
    target_symbol: str,
    direction: str,
    rng: Optional[random.Random] = None,
) -> Tuple[List[List[RawSymbol]], List[Series], List[dict]]:
    """Slam the active cluster and every loose matching symbol toward one wall.

    The locked cluster and every loose `target_symbol` cell move together down
    their own lanes and pack wall-first. Non-matching symbols close up behind
    them. Scatter and the firing Polarity Shifter stay fixed during the slam;
    the shifter is consumed immediately afterwards. A magnet already belonging
    to the cluster travels with it and remains a Wild cluster cell.

    Existing symbols are only relocated; the consumed shifter cell alone is
    refilled. The cluster is then rebuilt by connectivity, so a slammed symbol is
    only absorbed when it genuinely ends up adjacent to the cluster.
    """
    if not series or target_symbol not in PAY_SYMBOLS or direction not in POLARITY_STEPS:
        return clone_board(board), [deepcopy(entry) for entry in series], []

    cluster = uniq_positions([
        position
        for entry in series
        for position in entry['lockedPositions']
    ])
    cluster_keys = {pos_key(position) for position in cluster}
    loose_keys = {
        pos_key(position)
        for position in ALL_POSITIONS
        if pos_key(position) not in cluster_keys
        and get_symbol_at(board, position) == target_symbol
    }
    if not cluster:
        return clone_board(board), [deepcopy(entry) for entry in series], []

    obstacle_keys = _polarity_obstacle_keys(board, cluster_keys | loose_keys)

    out = clone_board(board)
    destination_of: Dict[str, Position] = {}
    for key in obstacle_keys:
        reel, row = (int(part) for part in key.split(':'))
        destination_of[key] = pos(reel, row)

    # Cluster + loose matches pack wall-first in every lane. Fixed obstacles split
    # a lane into independent segments; symbols never change row/column lanes.
    other_symbols = [symbol for symbol, _ in SYMBOL_WEIGHTS if symbol != target_symbol]
    for lane in _polarity_lanes(direction):
        size = len(lane)
        taken = [pos_key(cell) in obstacle_keys for cell in lane]
        segment_of_slot = [None] * size
        segments: List[List[int]] = []
        current: Optional[List[int]] = None
        for index in range(size):
            if taken[index]:
                current = None
                continue
            if current is None:
                current = []
                segments.append(current)
            current.append(index)
            segment_of_slot[index] = len(segments) - 1
        movers: List[List[int]] = [[] for _ in segments]
        fillers: List[List[int]] = [[] for _ in segments]
        for index in range(size):
            key = pos_key(lane[index])
            if key in obstacle_keys:
                continue
            bucket = segment_of_slot[index]
            if bucket is None:
                continue
            (movers if key in cluster_keys or key in loose_keys else fillers)[bucket].append(index)
        for bucket, slots in enumerate(segments):
            sources = movers[bucket] + fillers[bucket]
            for slot_index, source_index in zip(slots, sources):
                source = lane[source_index]
                landing = lane[slot_index]
                out[landing['reel']][landing['row']] = dict(board[source['reel']][source['row']])
                destination_of[pos_key(source)] = landing
            for slot_index in slots[len(sources):]:
                # Defensive: a lane should always balance, but never leave a hole.
                landing = lane[slot_index]
                picker = rng.randrange(len(other_symbols)) if rng is not None else 0
                out[landing['reel']][landing['row']] = make_pay_symbol(other_symbols[picker])

    # The machine fires from its original cell, then disappears. Refill only its
    # consumed cells; scatter and unrelated special blockers remain untouched.
    for position in get_polarity_positions(board):
        picker = rng.randrange(len(other_symbols)) if rng is not None else 0
        out[position['reel']][position['row']] = make_pay_symbol(other_symbols[picker])

    def move_kind(key: str) -> str:
        if key in cluster_keys:
            return 'cluster'
        if key in loose_keys:
            return 'symbol'
        return 'filler'

    moves = [
        {
            'from': dict(source),
            'to': dict(destination_of[pos_key(source)]),
            'kind': move_kind(pos_key(source)),
        }
        for source in ALL_POSITIONS
        if pos_key(source) in destination_of
        and pos_key(destination_of[pos_key(source)]) != pos_key(source)
    ]

    anchors = uniq_positions([
        destination_of[pos_key(position)]
        for entry in series
        for position in entry['anchorPositions']
        if pos_key(position) in destination_of
    ])
    shifted = [{
        **deepcopy(series[0]),
        'anchorPositions': clone_positions(anchors),
        'lockedPositions': clone_positions(_connected_cluster(out, anchors, target_symbol)),
        'multiplier': math.prod(int(entry.get('multiplier', 1)) for entry in series),
    }]
    return out, shifted, moves


def magnet_multiplier_product(board: List[List[RawSymbol]]) -> int:
    product = 1
    for reel in range(BOARD_REELS):
        for row in range(BOARD_ROWS):
            cell = board[reel][row]
            if not cell.get('magnet'):
                continue
            product *= max(1, int(cell.get('multiplier', 1)))
    return product


def get_scatter_positions(board: List[List[RawSymbol]]) -> List[Position]:
    out = []
    for reel in range(BOARD_REELS):
        for row in range(BOARD_ROWS):
            if board[reel][row]['name'] == 'SCATTER':
                out.append(pos(reel, row))
    return out


def get_visible_pay_symbols(board: List[List[RawSymbol]]) -> List[str]:
    out = []
    for reel in board:
        for cell in reel:
            if cell['name'] in PAY_SYMBOLS:
                out.append(str(cell['name']))
    return out


def choose_magnet_target_symbol(rng: random.Random, board: List[List[RawSymbol]]) -> str:
    symbols = get_visible_pay_symbols(board)
    if not symbols:
        return str(weighted_choice(rng, SYMBOL_WEIGHTS))
    return symbols[rng.randrange(len(symbols))]


def get_pay_for_size(symbol: str, size: int) -> float:
    for start, end, value in PAYTABLE_BANDS[symbol]:
        if start <= size <= end:
            return value
    return PAYTABLE_BANDS[symbol][-1][2] if size >= PAYTABLE_BANDS[symbol][-1][0] else 0.0


def target_support_positions(board: List[List[RawSymbol]], wild_position: Position, symbol: str) -> List[Position]:
    """Target symbols orthogonally connected to one wild.

    Other wilds are deliberately not traversed.  A new wild must have four
    actual symbols of one kind; wild-to-wild chaining cannot manufacture the
    minimum five-symbol cluster.
    """
    visited = {pos_key(wild_position)}
    queue = [neighbor for neighbor in neighbors(wild_position) if get_symbol_at(board, neighbor) == symbol]
    result: List[Position] = []
    for position in queue:
        visited.add(pos_key(position))
    while queue:
        current = queue.pop(0)
        result.append(current)
        for neighbor in neighbors(current):
            key = pos_key(neighbor)
            if key in visited or get_symbol_at(board, neighbor) != symbol:
                continue
            visited.add(key)
            queue.append(neighbor)
    return result


def wild_qualifies_for_cluster(board: List[List[RawSymbol]], wild_position: Position, symbol: str, existing_locked_keys: set[str]) -> bool:
    """A wild may join orthogonally, or seed with at least four real symbols."""
    key = pos_key(wild_position)
    if key in existing_locked_keys:
        return True
    if any(pos_key(neighbor) in existing_locked_keys for neighbor in neighbors(wild_position)):
        return True
    return len(target_support_positions(board, wild_position, symbol)) >= MAGNET_MIN_CLUSTER_SIZE - 1


def eligible_wild_keys(board: List[List[RawSymbol]], symbol: str, existing_locked_keys: Optional[set[str]] = None) -> set[str]:
    existing_locked_keys = existing_locked_keys or set()
    return {
        pos_key(position)
        for position in get_wild_positions(board)
        if wild_qualifies_for_cluster(board, position, symbol, existing_locked_keys)
    }


def magnets_qualify_for_cluster(board: List[List[RawSymbol]], magnet_positions: List[Position], symbol: str, existing_locked_keys: set[str]) -> bool:
    return bool(magnet_positions) and all(
        wild_qualifies_for_cluster(board, position, symbol, existing_locked_keys)
        for position in magnet_positions
    )


def is_symbol_match(board: List[List[RawSymbol]], position: Position, symbol: str, allowed_wild_keys: Optional[set[str]] = None) -> bool:
    name = get_symbol_at(board, position)
    return name == symbol or (name == 'WILD' and (allowed_wild_keys is None or pos_key(position) in allowed_wild_keys))


def components_for_symbol(board: List[List[RawSymbol]], symbol: str, allowed_wild_keys: Optional[set[str]] = None) -> List[List[Position]]:
    if allowed_wild_keys is None:
        allowed_wild_keys = eligible_wild_keys(board, symbol)
    visited = set()
    components = []
    for reel in range(BOARD_REELS):
        for row in range(BOARD_ROWS):
            position = pos(reel, row)
            key = pos_key(position)
            if key in visited or not is_symbol_match(board, position, symbol, allowed_wild_keys):
                continue
            queue = [position]
            visited.add(key)
            component = []
            while queue:
                current = queue.pop(0)
                component.append(current)
                for neighbor in neighbors(current):
                    neighbor_key = pos_key(neighbor)
                    if neighbor_key in visited or not is_symbol_match(board, neighbor, symbol, allowed_wild_keys):
                        continue
                    visited.add(neighbor_key)
                    queue.append(neighbor)
            components.append(component)
    return components


def qualifying_natural_series(board: List[List[RawSymbol]]) -> List[Tuple[str, List[Position]]]:
    """Return exactly ONE qualifying cluster — the single best-paying connected group.

    Only one cluster is allowed per round to keep the UI unambiguous. Pick the symbol
    whose best single cluster has the highest payout and return only that component.
    """
    best_symbol: Optional[str] = None
    best_payout: float = 0.0
    best_component: Optional[List[Position]] = None

    for symbol in PAY_SYMBOLS:
        for component in components_for_symbol(board, symbol):
            if len(component) < 5:
                continue
            if not any(get_symbol_at(board, p) == symbol for p in component):
                continue
            payout = get_pay_for_size(symbol, len(component))
            if payout > best_payout:
                best_payout = payout
                best_symbol = symbol
                best_component = component

    if best_symbol is None or best_component is None:
        return []
    return [(best_symbol, best_component)]


def visual_cluster_symbols(board: List[List[RawSymbol]]) -> set[str]:
    """Pay-symbol types that visibly form an orthogonal cluster of five or more.

    WILD is excluded here. This guard targets the confusing case where five identical regular
    symbols visibly touch even though the round is locked to a different Magnetic target.
    """
    return {
        symbol
        for symbol in PAY_SYMBOLS
        if any(
            len(component) >= MAGNET_MIN_CLUSTER_SIZE
            for component in components_for_symbol(board, symbol, set())
        )
    }


def suppress_non_target_visual_clusters(
    board: List[List[RawSymbol]], active_symbol: Optional[str]
) -> List[List[RawSymbol]]:
    """Keep the active symbol unchanged while breaking every other visible 5+ cluster.

    Replacement choice is deterministic and consumes no gameplay RNG. Therefore target counts,
    magnet pulls, payouts, and every later random draw remain unchanged; only misleading losing
    symbol layouts are altered.
    """
    out = clone_board(board)
    if active_symbol not in PAY_SYMBOLS:
        return out

    symbol_order = [symbol for symbol, _ in SYMBOL_WEIGHTS]
    max_repairs = BOARD_REELS * BOARD_ROWS * len(PAY_SYMBOLS)
    for _ in range(max_repairs):
        violation: Optional[Tuple[str, List[Position]]] = None
        for symbol in PAY_SYMBOLS:
            if symbol == active_symbol:
                continue
            component = next(
                (
                    candidate
                    for candidate in components_for_symbol(out, symbol, set())
                    if len(candidate) >= MAGNET_MIN_CLUSTER_SIZE
                ),
                None,
            )
            if component is not None:
                violation = (symbol, component)
                break
        if violation is None:
            return out

        original_symbol, component = violation
        best: Optional[Tuple[Tuple[int, int, int, int], Position, str]] = None
        replacements = [
            symbol
            for symbol in symbol_order
            if symbol not in (active_symbol, original_symbol)
        ]
        for position in component:
            for replacement_index, replacement in enumerate(replacements):
                candidate_board = clone_board(out)
                candidate_board[position['reel']][position['row']] = make_pay_symbol(replacement)
                replacement_component_size = max(
                    (
                        len(candidate)
                        for candidate in components_for_symbol(candidate_board, replacement, set())
                        if any(pos_key(cell) == pos_key(position) for cell in candidate)
                    ),
                    default=1,
                )
                if replacement_component_size >= MAGNET_MIN_CLUSTER_SIZE:
                    continue
                remaining_original_size = max(
                    (
                        len(candidate)
                        for candidate in components_for_symbol(
                            candidate_board, original_symbol, set()
                        )
                    ),
                    default=0,
                )
                score = (
                    remaining_original_size,
                    replacement_component_size,
                    position['reel'] * BOARD_ROWS + position['row'],
                    replacement_index,
                )
                if best is None or score < best[0]:
                    best = (score, position, replacement)

        if best is None:
            raise RuntimeError(
                f'cannot break visual {original_symbol} cluster without changing {active_symbol}'
            )
        _, position, replacement = best
        out[position['reel']][position['row']] = make_pay_symbol(replacement)

    raise RuntimeError('visual cluster suppression exceeded deterministic repair limit')


def prepare_board_for_reveal(
    rng: random.Random,
    board: List[List[RawSymbol]],
    target_symbol: Optional[str] = None,
) -> Tuple[List[List[RawSymbol]], Optional[str]]:
    """Select the round's sole active symbol, then remove misleading other-symbol clusters."""
    selected_symbol = target_symbol
    if selected_symbol is None and get_magnet_positions(board):
        selected_symbol = choose_magnet_target_symbol(rng, board)
    if selected_symbol is None:
        natural = qualifying_natural_series(board)
        selected_symbol = str(natural[0][0]) if natural else None
    return suppress_non_target_visual_clusters(board, selected_symbol), selected_symbol


def snapshot_of(series: Series) -> Series:
    return {
        'id': series['id'],
        'symbol': series['symbol'],
        'kind': series['kind'],
        'anchorPositions': clone_positions(series['anchorPositions']),
        'lockedPositions': clone_positions(series['lockedPositions']),
        'multiplier': series['multiplier'],
        'persistent': series['persistent'],
    }


def series_locked_map(series: List[Series]) -> Dict[str, RawSymbol]:
    locked: Dict[str, RawSymbol] = {}
    for entry in series:
        anchor_keys = {pos_key(p) for p in entry['anchorPositions']}
        for position in entry['lockedPositions']:
            key = pos_key(position)
            locked[key] = make_wild() if key in anchor_keys else make_pay_symbol(str(entry['symbol']))
    return locked


def board_fully_locked(series: List[Series]) -> bool:
    return len(series_locked_map(series)) >= BOARD_REELS * BOARD_ROWS


def did_series_grow(previous: List[Series], current: List[Series]) -> bool:
    prev_sizes = {entry['id']: len(entry['lockedPositions']) for entry in previous}
    if len(previous) != len(current):
        return True
    return any(prev_sizes.get(entry['id'], 0) != len(entry['lockedPositions']) for entry in current)


def merge_series_to_one(series: List[Series]) -> List[Series]:
    """Collapse multiple same-symbol entries into a single cluster entry.

    Only one active cluster is allowed at a time so the player always sees one
    coherent cluster. All locked/anchor positions are merged into the first entry.
    """
    if len(series) <= 1:
        return series
    combined_locked = uniq_positions([p for e in series for p in e['lockedPositions']])
    combined_anchors = uniq_positions([p for e in series for p in e['anchorPositions']])
    return [{**series[0], 'anchorPositions': combined_anchors, 'lockedPositions': combined_locked}]


def clusters_are_touching(a: Series, b: Series) -> bool:
    """True if any position in a is orthogonally adjacent to any position in b."""
    b_keys = {pos_key(p) for p in b['lockedPositions']}
    for p in a['lockedPositions']:
        if any(pos_key(n) in b_keys for n in neighbors(p)):
            return True
    return False


def merge_two_clusters(a: Series, b: Series) -> Series:
    """Merge b into a, compounding their multipliers."""
    return {
        **deepcopy(a),
        'anchorPositions': uniq_positions(a['anchorPositions'] + b['anchorPositions']),
        'lockedPositions': uniq_positions(a['lockedPositions'] + b['lockedPositions']),
        'multiplier': int(a['multiplier']) * int(b['multiplier']),
    }


def merge_touching_clusters(series: List[Series]) -> List[Series]:
    """Repeatedly merge any two touching clusters until none are left touching."""
    changed = True
    while changed:
        changed = False
        result: List[Series] = []
        merged_ids: set = set()
        for i, a in enumerate(series):
            if a['id'] in merged_ids:
                continue
            for j in range(i + 1, len(series)):
                b = series[j]
                if b['id'] in merged_ids:
                    continue
                if clusters_are_touching(a, b):
                    a = merge_two_clusters(a, b)
                    merged_ids.add(b['id'])
                    changed = True
            result.append(a)
        series = result
    return series


def reconcile_series_components(previous: List[Series], next_components: List[List[Position]], kind: str, multiplier: int, persistent: bool, allow_new_anchors: bool, symbol: str) -> List[Series]:
    out = []
    serial = 1
    for component in next_components:
        component_keys = {pos_key(position) for position in component}
        matched = [entry for entry in previous if any(pos_key(position) in component_keys for position in entry['lockedPositions'])]
        if not matched and not allow_new_anchors:
            continue
        anchors = uniq_positions([position for entry in matched for position in entry['anchorPositions']] + ([] if matched else component))
        out.append({
            'id': matched[0]['id'] if matched else f'{kind}-new-{serial}',
            'symbol': symbol,
            'kind': kind,
            'anchorPositions': anchors,
            'lockedPositions': uniq_positions(component),
            # A newly connected component may match several previously separate
            # clusters. Preserve every visible multiplier by compounding them.
            'multiplier': (
                math.prod(int(entry['multiplier']) for entry in matched)
                if matched else multiplier
            ),
            'persistent': persistent,
        })
        if not matched:
            serial += 1
    if not allow_new_anchors:
        consumed_ids = {matched_entry['id'] for component in next_components for matched_entry in previous if any(pos_key(position) in {pos_key(p) for p in component} for position in matched_entry['lockedPositions'])}
        preserved_ids = {entry['id'] for entry in out}
        for prev in previous:
            if prev['id'] in consumed_ids or prev['id'] in preserved_ids:
                continue
            out.append({**deepcopy(prev), 'persistent': persistent})
    return sorted(out, key=lambda item: str(item['id']))


def render_series_wins(series: List[Series], total_multiplier: int, kind: str) -> List[dict]:
    wins = []
    for entry in series:
        size = len(entry['lockedPositions'])
        if size < MAGNET_MIN_CLUSTER_SIZE:
            continue
        base_x = get_pay_for_size(str(entry['symbol']), size)
        if base_x <= 0:
            continue
        base_amount = int(round(base_x * 100))
        cluster_mult = int(entry.get('multiplier', total_multiplier))
        wins.append({
            'seriesId': entry['id'],
            'symbol': entry['symbol'],
            'size': size,
            'positions': clone_positions(entry['lockedPositions']),
            'amount': base_amount * cluster_mult,
            'meta': {
                'baseAmount': base_amount,
                'totalMultiplier': cluster_mult,
                'seriesKind': kind,
                'anchors': clone_positions(entry['anchorPositions']),
            },
        })
    return wins


def win_level_from_amount(amount: int) -> int:
    x = amount / 100.0
    if x <= 0:
        return 1
    if x < 2:
        return 2
    if x < 5:
        return 3
    if x < 10:
        return 4
    if x < 20:
        return 5
    if x < 50:
        return 6
    if x < 100:
        return 7
    if x < 250:
        return 8
    if x < 1000:
        return 9
    return 10


def clamp_amount(amount: int) -> int:
    return max(0, min(int(amount), MAX_WIN_AMOUNT))


def cap_wins(wins: List[dict], cap: int) -> List[dict]:
    remaining = max(0, int(cap))
    out = []
    for win in wins:
        if remaining <= 0:
            break
        amount = min(int(win['amount']), remaining)
        if amount <= 0:
            continue
        next_win = deepcopy(win)
        next_win['amount'] = amount
        out.append(next_win)
        remaining -= amount
    return out


def append_event(events: List[dict], payload: dict):
    event = dict(payload)
    event['index'] = len(events)
    events.append(event)


def emit_reveal(events: List[dict], board: List[List[RawSymbol]], game_type: str):
    append_event(events, {'type': 'reveal', 'board': clone_board(board), 'paddingPositions': [1, 3, 5, 7, 9, 11, 13], 'anticipation': [0] * 7, 'gameType': game_type})


def emit_series_update(events: List[dict], series: List[Series], magnet_target_symbol: Optional[str], total_multiplier: int):
    append_event(events, {'type': 'clusterSeriesUpdate', 'series': [snapshot_of(entry) for entry in series], 'magnetTargetSymbol': magnet_target_symbol, 'totalMultiplier': total_multiplier})


def emit_magnet_activated(events: List[dict], series_id: str, symbol: str, positions: List[Position], multiplier: int, total_multiplier: int, persistent: bool):
    append_event(events, {'type': 'magnetActivated', 'seriesId': series_id, 'symbol': symbol, 'positions': clone_positions(positions), 'multiplier': multiplier, 'totalMultiplier': total_multiplier, 'persistent': persistent})


def emit_magnet_target_selected(events: List[dict], symbol: str):
    append_event(events, {'type': 'magnetTargetSelected', 'symbol': symbol})


def emit_polarity_shift(
    events: List[dict],
    direction: str,
    symbol: str,
    shifter_positions: List[Position],
    moves: List[dict],
    board: List[List[RawSymbol]],
    series: List[Series],
):
    append_event(events, {
        'type': 'polarityShift',
        'direction': direction,
        'symbol': symbol,
        'shifterPositions': clone_positions(shifter_positions),
        'moves': deepcopy(moves),
        'board': clone_board(board),
        'series': [snapshot_of(entry) for entry in series],
    })


def emit_series_resolved(events: List[dict], wins: List[dict]):
    for win in wins:
        append_event(events, {'type': 'clusterSeriesResolved', 'seriesId': win['seriesId'], 'symbol': win['symbol'], 'positions': clone_positions(win['positions']), 'amount': win['amount'], 'multiplier': win['meta']['totalMultiplier']})


def emit_win_info(events: List[dict], wins: List[dict]) -> int:
    total = sum(win['amount'] for win in wins)
    append_event(events, {'type': 'winInfo', 'totalWin': total, 'wins': wins})
    return total


def emit_set_total(events: List[dict], amount: int):
    append_event(events, {'type': 'setTotalWin', 'amount': amount})


def emit_set_win(events: List[dict], amount: int):
    append_event(events, {'type': 'setWin', 'amount': amount, 'winLevel': win_level_from_amount(amount)})


def emit_super_carry(events: List[dict], series_list: List[Series], magnet_target_symbol: Optional[str], total_multiplier: int):
    append_event(events, {'type': 'superSeriesCarry', 'series': [snapshot_of(e) for e in series_list], 'magnetTargetSymbol': magnet_target_symbol, 'totalMultiplier': total_multiplier})


def respin_board(rng: random.Random, mode: str, board: List[List[RawSymbol]], locked_map: Dict[str, RawSymbol], target_symbol: Optional[str], target_boost: float, magnet_rate: float) -> List[List[RawSymbol]]:
    settings = MODE_SETTINGS[mode]
    out = clone_board(board)
    for reel in range(BOARD_REELS):
        for row in range(BOARD_ROWS):
            key = f'{reel}:{row}'
            if key in locked_map:
                out[reel][row] = dict(locked_map[key])
            else:
                out[reel][row] = make_pay_symbol(random_pay_symbol(rng, target_symbol, target_boost))
    for position in sample_positions(rng, random_magnet_count(rng, magnet_rate), set(locked_map.keys())):
        out[position['reel']][position['row']] = make_random_magnet(rng, mode)
    blocked = set(locked_map.keys()) | {pos_key(p) for p in get_magnet_positions(out)}
    polarity_rate = float(settings.get('polarity_respin_rate', 0.0))
    if not get_magnet_positions(out) and rng.random() < polarity_rate:
        for position in sample_positions(rng, 1, blocked):
            out[position['reel']][position['row']] = make_polarity()
            blocked.add(pos_key(position))
    for position in sample_positions(rng, random_wild_count(rng, float(settings['wild_rate'])), blocked):
        out[position['reel']][position['row']] = make_wild()
    return out


def create_natural_series(board: List[List[RawSymbol]]) -> List[Series]:
    out = []
    for idx, (symbol, component) in enumerate(qualifying_natural_series(board), start=1):
        out.append({'id': f'natural-{idx}', 'symbol': symbol, 'kind': 'natural', 'anchorPositions': clone_positions(component), 'lockedPositions': clone_positions(component), 'multiplier': 1, 'persistent': False})
    return out


def target_components(board: List[List[RawSymbol]], target_symbol: str, previous: List[Series], allow_new_anchors: bool) -> List[List[Position]]:
    previous_keys = {pos_key(p) for entry in previous for p in entry['lockedPositions']}
    # Reject a landed wild before component discovery unless it is already locked,
    # touches the locked cluster orthogonally, or independently has four real
    # target symbols.  This also prevents a rejected wild being absorbed later in
    # the same respin merely because another symbol bridges toward it.
    components = components_for_symbol(board, target_symbol, eligible_wild_keys(board, target_symbol, previous_keys))
    if not previous_keys:
        # No cluster yet — accept all components to seed it.
        return components
    # Build the one-step border around the current cluster so new symbols can only
    # join from adjacent positions, never from a disconnected patch far away.
    border_keys = {pos_key(n) for entry in previous for lp in entry['lockedPositions'] for n in neighbors(lp)}
    reachable = previous_keys | border_keys
    return [c for c in components if any(pos_key(p) in reachable for p in c)]


def resolve_natural_sequence(
    rng: random.Random,
    board: List[List[RawSymbol]],
    mode: str,
    game_type: str,
    sticky_symbols: Optional[Dict[str, RawSymbol]] = None,
    scatter_collect_rate: float = 0.0,
    max_scatter_count: int = 4,
) -> dict:
    events: List[dict] = []
    series = create_natural_series(board)
    if not series:
        return {'events': events, 'total_win': 0, 'series': [], 'board': board}

    # qualifying_natural_series guarantees exactly one cluster — track its symbol.
    active_symbol = str(series[0]['symbol'])
    series = merge_series_to_one(series)
    emit_series_update(events, series, None, 1)
    current_board = suppress_non_target_visual_clusters(board, active_symbol)
    sticky_symbols = {
        key: dict(symbol)
        for key, symbol in (sticky_symbols or {}).items()
    }
    respins = 0
    while True:
        locked_map = dict(sticky_symbols)
        locked_map.update(series_locked_map(series))
        next_board = respin_board(rng, mode, current_board, locked_map, None, 0.18, 0.0)
        maybe_collect_respin_scatter(
            rng,
            next_board,
            sticky_symbols,
            set(locked_map),
            scatter_collect_rate,
            max_scatter_count,
        )
        next_board = suppress_non_target_visual_clusters(next_board, active_symbol)
        emit_reveal(events, next_board, game_type)
        reconcile_from = series
        polarity_positions = get_polarity_positions(next_board)
        if polarity_positions:
            direction = str(weighted_choice(rng, [(value, 1) for value in POLARITY_DIRECTIONS]))
            next_board, reconcile_from, moves = apply_polarity_shift(
                next_board, series, active_symbol, direction, rng
            )
            emit_polarity_shift(
                events,
                direction,
                active_symbol,
                polarity_positions,
                moves,
                next_board,
                reconcile_from,
            )
        next_series = merge_series_to_one(reconcile_series_components(
            reconcile_from,
            target_components(next_board, active_symbol, reconcile_from, False),
            'natural', 1, False, False, active_symbol,
        ))
        grew = did_series_grow(series, next_series)
        series = next_series
        current_board = next_board
        emit_series_update(events, series, None, 1)
        respins += 1
        if not grew or board_fully_locked(series) or respins >= MAX_SEQUENCE_RESPINS_SAFETY:
            break
    wins = cap_wins(render_series_wins(series, 1, 'natural'), MAX_WIN_AMOUNT)
    emit_series_resolved(events, wins)
    total_win = emit_win_info(events, wins) if wins else 0
    return {'events': events, 'total_win': clamp_amount(total_win), 'series': series, 'board': current_board}


def resolve_magnet_sequence(
    rng: random.Random,
    board: List[List[RawSymbol]],
    mode: str,
    game_type: str,
    target_symbol: Optional[str] = None,
    persistent: bool = False,
    carry_series: Optional[List[Series]] = None,
    carry_multiplier: int = 1,
    sticky_symbols: Optional[Dict[str, RawSymbol]] = None,
    scatter_collect_rate: float = 0.0,
    max_scatter_count: int = 4,
) -> dict:
    events: List[dict] = []
    carry_series = carry_series or []
    sticky_symbols = {
        key: dict(symbol)
        for key, symbol in (sticky_symbols or {}).items()
    }
    kind = 'super' if persistent else 'magnet'
    current_board = clone_board(board)
    target_symbol = target_symbol or choose_magnet_target_symbol(rng, current_board)
    current_board = suppress_non_target_visual_clusters(current_board, target_symbol)
    magnets = get_magnet_positions(current_board)
    initial_multiplier = magnet_multiplier_product(current_board) if mode in MAGNET_MULTIPLIER_VALUES else 1
    series_before_spin = [deepcopy(e) for e in carry_series]
    last_emitted_series: Optional[List[Series]] = None

    # Target selection is a presentation fact, separate from whether the pull
    # reaches the five-cell lock/pay threshold. Always expose it when a magnet
    # landed so the frontend can populate the capsule immediately.
    if magnets:
        emit_magnet_target_selected(events, target_symbol)

    if carry_series:
        # Super carry: first lock any target/wild symbols that landed adjacent
        # on the normal free-spin board. Do this BEFORE magnet pull so a visible
        # target beside the cluster cannot be cleared/rerolled by the magnet step.
        series = [deepcopy(e) for e in carry_series]
        polarity_positions = get_polarity_positions(current_board)
        if polarity_positions:
            direction = str(weighted_choice(rng, [(value, 1) for value in POLARITY_DIRECTIONS]))
            current_board, series, moves = apply_polarity_shift(
                current_board, series, target_symbol, direction, rng
            )
            emit_polarity_shift(
                events,
                direction,
                target_symbol,
                polarity_positions,
                moves,
                current_board,
                series,
            )
            # Polarity can relocate a Magnet/Wild that belongs to the carried
            # cluster. Never run the following pull from its pre-shift cell:
            # doing so turns the ordinary symbol now occupying that cell into
            # another visual/logical magnet.
            magnets = get_magnet_positions(current_board)
        normal_series = merge_touching_clusters(reconcile_series_components(
            series,
            target_components(current_board, target_symbol, series, False),
            kind, 1, persistent, False, target_symbol,
        )) if persistent and series else series
        normal_grew = did_series_grow(series, normal_series)
        series = normal_series
        if normal_grew:
            emit_series_update(events, series, target_symbol, max((int(e['multiplier']) for e in series), default=1))
            last_emitted_series = [deepcopy(e) for e in series]

        # A magnet may create an extra cluster, but no magnet event is emitted
        # when no magnet landed (prevents dim/flash on ordinary super spins).
        if magnets:
            existing_locked = {pos_key(p) for e in series for p in e['lockedPositions']}
            # If this WILD was already absorbed into the carry cluster above, it
            # must pull through the locked cluster to its nearest open edge.
            # Blocking the cluster plus its border trapped the BFS at the WILD,
            # so visible target symbols elsewhere on the board were never moved.
            embedded_magnet = any(pos_key(magnet) in existing_locked for magnet in magnets)
            exclusion_zone = (
                existing_locked
                if embedded_magnet
                else {pos_key(n) for e in series for lp in e['lockedPositions'] for n in neighbors(lp)} | existing_locked
            )
            board_before_pull = clone_board(current_board)
            current_board, new_anchors, new_bfs = apply_magnet_pull(
                rng,
                current_board,
                magnets,
                target_symbol,
                exclusion_zone,
                existing_locked if embedded_magnet else None,
            )
            current_board = suppress_non_target_visual_clusters(current_board, target_symbol)
            new_cluster = uniq_positions(new_anchors + new_bfs)
            magnet_qualifies = magnets_qualify_for_cluster(current_board, new_anchors, target_symbol, existing_locked)
            if magnet_qualifies and new_cluster:
                series.append({
                    'id': f'{kind}-carry-{len(series)+1}',
                    'symbol': target_symbol,
                    'kind': kind,
                    'anchorPositions': new_anchors,
                    'lockedPositions': new_cluster,
                    'multiplier': initial_multiplier if initial_multiplier > 1 else 1,
                    'persistent': persistent,
                })
                series = merge_touching_clusters(series)
                emit_magnet_activated(events, series[0]['id'] if series else f'{kind}-carry-1', target_symbol, [{'reel': m['reel'], 'row': m['row']} for m in magnets], initial_multiplier, max((int(e['multiplier']) for e in series), default=1), persistent)
            else:
                current_board = board_before_pull
    else:
        # Fresh sequence: pull from initial magnet.  If there is no magnet, do not
        # seed a super cluster from random target symbols.
        if not magnets:
            return {'events': events, 'total_win': 0, 'series': [], 'target_symbol': target_symbol, 'total_multiplier': 1, 'board': current_board}
        board_before_pull = clone_board(current_board)
        current_board, anchor_positions, bfs_positions = apply_magnet_pull(rng, current_board, magnets, target_symbol)
        current_board = suppress_non_target_visual_clusters(current_board, target_symbol)
        cluster_positions = uniq_positions(anchor_positions + bfs_positions)
        if not magnets_qualify_for_cluster(current_board, anchor_positions, target_symbol, set()):
            # No activation/highlight/lock for a sub-threshold wild in any mode.
            return {'events': events, 'total_win': 0, 'series': [], 'target_symbol': target_symbol, 'total_multiplier': 1, 'board': board_before_pull}
        series = [{
            'id': f'{kind}-1',
            'symbol': target_symbol,
            'kind': kind,
            'anchorPositions': anchor_positions,
            'lockedPositions': cluster_positions,
            'multiplier': initial_multiplier if initial_multiplier > 1 else 1,
            'persistent': persistent,
        }] if cluster_positions else []
        emit_magnet_activated(events, series[0]['id'] if series else f'{kind}-1', target_symbol, [{'reel': m['reel'], 'row': m['row']} for m in magnets], initial_multiplier, initial_multiplier, persistent)

    # Fresh super sequence can still seed from the initial magnet pull above.
    if persistent and series and not carry_series:
        series = merge_touching_clusters(reconcile_series_components(
            series,
            target_components(current_board, target_symbol, series, False),
            kind, 1, persistent, False, target_symbol,
        ))

    grew_on_spin = did_series_grow(series_before_spin, series)
    total_display_mult = max((int(e['multiplier']) for e in series), default=1)
    should_emit_series_update = bool(series) and (not carry_series or grew_on_spin) and (
        last_emitted_series is None or did_series_grow(last_emitted_series, series)
    )
    if should_emit_series_update:
        emit_series_update(events, series, target_symbol, total_display_mult)

    # Super: if the normal free spin did not add anything, stop here. No respin.
    # Super wins are awarded once at bonus end, not during each spin.
    if persistent and (not grew_on_spin or board_fully_locked(series)):
        return {'events': events, 'total_win': 0, 'series': series, 'target_symbol': target_symbol, 'total_multiplier': total_display_mult, 'board': current_board}

    respins = 0
    while True:
        prev_series = [deepcopy(e) for e in series]
        locked_map = dict(sticky_symbols)
        locked_map.update(series_locked_map(series))
        next_board = respin_board(rng, mode, current_board, locked_map, target_symbol, float(MODE_SETTINGS[mode]['target_boost']), float(MODE_SETTINGS[mode]['magnet_respin_rate']))
        maybe_collect_respin_scatter(
            rng,
            next_board,
            sticky_symbols,
            set(locked_map),
            scatter_collect_rate,
            max_scatter_count,
        )
        next_board = suppress_non_target_visual_clusters(next_board, target_symbol)
        emit_reveal(events, next_board, game_type)

        polarity_positions = get_polarity_positions(next_board)
        if polarity_positions:
            direction = str(weighted_choice(rng, [(value, 1) for value in POLARITY_DIRECTIONS]))
            next_board, series, moves = apply_polarity_shift(
                next_board, series, target_symbol, direction
            )
            emit_polarity_shift(
                events,
                direction,
                target_symbol,
                polarity_positions,
                moves,
                next_board,
                series,
            )

        # Handle new magnet that landed on this respin
        respin_magnets = get_magnet_positions(next_board)
        if respin_magnets:
            respin_mult = magnet_multiplier_product(next_board) if mode in MAGNET_MULTIPLIER_VALUES else 1
            existing_locked = {pos_key(p) for e in series for p in e['lockedPositions']}
            exclusion_zone = {pos_key(n) for e in series for lp in e['lockedPositions'] for n in neighbors(lp)} | existing_locked
            board_before_pull = clone_board(next_board)
            next_board, new_anchors, new_bfs = apply_magnet_pull(rng, next_board, respin_magnets, target_symbol, exclusion_zone)
            next_board = suppress_non_target_visual_clusters(next_board, target_symbol)
            new_cluster = uniq_positions(new_anchors + new_bfs)
            magnet_qualifies = magnets_qualify_for_cluster(next_board, new_anchors, target_symbol, existing_locked)
            if magnet_qualifies and new_cluster:
                new_entry: Series = {
                    'id': f'{kind}-{respins+2}',
                    'symbol': target_symbol,
                    'kind': kind,
                    'anchorPositions': new_anchors,
                    'lockedPositions': new_cluster,
                    'multiplier': respin_mult if respin_mult > 1 else 1,
                    'persistent': persistent,
                }
                series = series + [new_entry]
                emit_magnet_activated(events, series[-1]['id'] if series else f'{kind}-1', target_symbol, [{'reel': m['reel'], 'row': m['row']} for m in respin_magnets], respin_mult if respin_magnets else 1, max((int(e['multiplier']) for e in series), default=1), persistent)
            else:
                next_board = board_before_pull

        # Grow existing clusters with new adjacent target symbols
        next_series = reconcile_series_components(
            series,
            target_components(next_board, target_symbol, series, False),
            kind, 1, persistent, False, target_symbol,
        )

        # Merge touching clusters (compounding their multipliers)
        next_series = merge_touching_clusters(next_series)

        grew = did_series_grow(prev_series, next_series)
        series = next_series
        current_board = next_board
        total_display_mult = max((int(e['multiplier']) for e in series), default=1)
        emit_series_update(events, series, target_symbol, total_display_mult)
        respins += 1
        if not grew or board_fully_locked(series) or respins >= MAX_SEQUENCE_RESPINS_SAFETY:
            break

    total_display_mult = max((int(e['multiplier']) for e in series), default=1)
    if persistent:
        return {'events': events, 'total_win': 0, 'series': series, 'target_symbol': target_symbol, 'total_multiplier': total_display_mult, 'board': current_board}

    # ONE ACTIVE SYMBOL PER ROUND.  Only the magnet's target symbol pays: multiple clusters of
    # that symbol may each pay (series carries one entry per cluster), but a second symbol never
    # does.  Non-target clusters used to pay here as 'side-N' wins; that broke the rule and, being
    # snapshotted before the respin loop, described cells respin_board had already re-rolled.
    target_wins = cap_wins(render_series_wins(series, 1, kind), MAX_WIN_AMOUNT)
    emit_series_resolved(events, target_wins)
    all_wins = target_wins
    total_win = emit_win_info(events, all_wins) if all_wins else 0
    total_display_mult = max((int(e['multiplier']) for e in series), default=1)
    return {'events': events, 'total_win': clamp_amount(total_win), 'series': series, 'target_symbol': target_symbol, 'total_multiplier': total_display_mult, 'board': current_board}


def create_trigger_board(rng: random.Random, bonus_mode: str) -> List[List[RawSymbol]]:
    # Flat-board scatter placement: multiple scatters may land on the same reel.
    # Trigger condition: 3 Gravity Breach, 4 Core Overload, 5 Zero Point Protocol.
    scatter_count = {'BONUS': 3, 'SUPER': 4, 'HIDDEN': 5}[bonus_mode]
    positions = sample_positions(rng, scatter_count, set())
    return force_scatters(create_board(rng, 'BASE'), positions)


def connected_positions(rng: random.Random, count: int) -> List[Position]:
    """Return a random orthogonally connected set of unique board positions."""
    positions = [pos(rng.randrange(BOARD_REELS), rng.randrange(BOARD_ROWS))]
    keys = {pos_key(positions[0])}
    while len(positions) < count:
        frontier = [
            neighbor
            for position in positions
            for neighbor in neighbors(position)
            if pos_key(neighbor) not in keys
        ]
        pick = frontier[rng.randrange(len(frontier))]
        keys.add(pos_key(pick))
        positions.append(pick)
    return positions


def create_guaranteed_feature_board(
    rng: random.Random,
    magnet_cluster: bool,
) -> Tuple[List[List[RawSymbol]], Optional[str]]:
    """Build one FEATURE board with a guaranteed five-cell paying cluster."""
    board = create_board(rng, 'FEATURE', magnet_count=0)
    target_symbol = str(weighted_choice(rng, SYMBOL_WEIGHTS))
    cluster_positions = connected_positions(rng, MAGNET_MIN_CLUSTER_SIZE)
    cluster_keys = {pos_key(position) for position in cluster_positions}
    replacement_symbols = [(symbol, weight) for symbol, weight in SYMBOL_WEIGHTS if symbol != target_symbol]

    # Keep the guaranteed cluster size controlled. Random copies of the chosen
    # symbol elsewhere would all be pulled by a magnet and distort feature RTP.
    for reel in range(BOARD_REELS):
        for row in range(BOARD_ROWS):
            position = pos(reel, row)
            if pos_key(position) not in cluster_keys and board[reel][row]['name'] == target_symbol:
                board[reel][row] = make_pay_symbol(str(weighted_choice(rng, replacement_symbols)))

    if magnet_cluster:
        anchor, *supports = cluster_positions
        board[anchor['reel']][anchor['row']] = make_random_magnet(rng, 'FEATURE')
        for position in supports:
            board[position['reel']][position['row']] = make_pay_symbol(target_symbol)
        return board, target_symbol

    for position in cluster_positions:
        board[position['reel']][position['row']] = make_pay_symbol(target_symbol)
    return board, None


def create_collected_trigger_seed_board(
    rng: random.Random,
    initial_scatter_count: int,
) -> List[List[RawSymbol]]:
    """Build a base reveal with 1-2 scatters and a guaranteed active cluster."""
    board, _ = create_guaranteed_feature_board(rng, False)
    cluster_keys = {
        pos_key(position)
        for _, component in qualifying_natural_series(board)
        for position in component
    }
    scatter_positions = sample_positions(rng, initial_scatter_count, cluster_keys)
    return force_scatters(board, scatter_positions)


def build_base_round(rng: random.Random, mode: str, forced_trigger: Optional[str] = None) -> dict:
    events: List[dict] = []
    total_win = 0
    basegame_win = 0
    trigger_mode: Optional[str] = None

    settings = MODE_SETTINGS[mode]
    collected_trigger_target = {
        'collected_bonus': 3,
        'collected_super': 4,
        'collected_hidden': 5,
    }.get(forced_trigger)
    if collected_trigger_target is not None:
        trigger_hidden = False
        trigger_super = False
        trigger_bonus = False
    elif forced_trigger is not None:
        trigger_hidden = forced_trigger == 'hidden'
        trigger_super = forced_trigger == 'super'
        trigger_bonus = forced_trigger == 'bonus'
    else:
        trigger_roll = rng.random()
        hidden_rate = float(settings.get('trigger_hidden_rate', 0.0))
        super_rate = float(settings['trigger_super_rate'])
        bonus_rate = float(settings['trigger_bonus_rate'])
        trigger_hidden = trigger_roll < hidden_rate
        trigger_super = (not trigger_hidden) and trigger_roll < hidden_rate + super_rate
        trigger_bonus = (not trigger_hidden and not trigger_super) and trigger_roll < hidden_rate + super_rate + bonus_rate

    if collected_trigger_target is not None:
        board = create_collected_trigger_seed_board(rng, rng.randint(1, 2))
    elif trigger_hidden or trigger_super or trigger_bonus:
        trigger_board_mode = 'HIDDEN' if trigger_hidden else 'SUPER' if trigger_super else 'BONUS'
        board = create_trigger_board(rng, trigger_board_mode)
    else:
        board = create_board(
            rng,
            mode,
            scatter_count=random_scatter_count(rng, mode),
            magnet_count=random_magnet_count(rng, float(settings['magnet_spin_rate'])),
        )
    board, active_symbol = prepare_board_for_reveal(rng, board)
    initial_scatter_positions = get_scatter_positions(board)
    # Every landed scatter stays pinned while the active cluster earns respins.
    # Each such respin may add one more scatter; without an active cluster the
    # resolver returns immediately, so no scatter collection can happen.
    sticky_scatters = {
        pos_key(position): dict(board[position['reel']][position['row']])
        for position in initial_scatter_positions
    }
    scatter_collect_rate = float(RESPIN_SCATTER_RATES.get(mode, 0.0))
    max_scatter_count = collected_trigger_target or (5 if not trigger_bonus else 3)
    emit_reveal(events, board, 'basegame')
    has_magnet = bool(get_magnet_positions(board))
    resolved = (
        resolve_magnet_sequence(
            rng,
            board,
            mode,
            'basegame',
            target_symbol=active_symbol,
            sticky_symbols=sticky_scatters,
            scatter_collect_rate=scatter_collect_rate,
            max_scatter_count=max_scatter_count,
        )
        if has_magnet
        else resolve_natural_sequence(
            rng,
            board,
            mode,
            'basegame',
            sticky_symbols=sticky_scatters,
            scatter_collect_rate=scatter_collect_rate,
            max_scatter_count=max_scatter_count,
        )
    )
    events.extend([{**event, 'index': len(events) + idx} for idx, event in enumerate(resolved['events'])])
    total_win = clamp_amount(total_win + int(resolved['total_win']))
    basegame_win = clamp_amount(basegame_win + int(resolved['total_win']))
    emit_set_total(events, total_win)
    if total_win > 0:
        emit_set_win(events, total_win)

    # Resolve the trigger from the board actually visible after the cluster
    # chain. A fourth collected scatter upgrades a natural three-scatter bonus
    # to SUPER. Forced collected books wait for their requested exact threshold.
    trigger_positions = get_scatter_positions(resolved['board'])
    scatter_count = len(trigger_positions)
    if collected_trigger_target is not None and scatter_count < collected_trigger_target:
        trigger_hidden = False
        trigger_super = False
        trigger_bonus = False
    else:
        trigger_hidden = scatter_count >= 5
        trigger_super = scatter_count == 4
        trigger_bonus = scatter_count == 3

    if trigger_hidden:
        trigger_mode = 'hidden'
        bonus = build_bonus_sequence(rng, 'HIDDEN', trigger_positions, total_win, True)
        events.extend([{**event, 'index': len(events) + idx} for idx, event in enumerate(bonus['events'])])
        total_win = bonus['final_amount']
    elif trigger_super:
        trigger_mode = 'superspin'
        bonus = build_bonus_sequence(rng, 'SUPER', trigger_positions, total_win, True)
        events.extend([{**event, 'index': len(events) + idx} for idx, event in enumerate(bonus['events'])])
        total_win = bonus['final_amount']
    elif trigger_bonus:
        trigger_mode = 'freegame'
        bonus = build_bonus_sequence(rng, 'BONUS', trigger_positions, total_win, True)
        events.extend([{**event, 'index': len(events) + idx} for idx, event in enumerate(bonus['events'])])
        total_win = bonus['final_amount']

    append_event(events, {'type': 'finalWin', 'amount': total_win})
    return {'events': events, 'final_amount': total_win, 'basegame_win': basegame_win, 'freegame_win': total_win - basegame_win, 'trigger_mode': trigger_mode}


def build_feature_round(rng: random.Random) -> dict:
    events: List[dict] = []
    append_event(events, {'type': 'freeSpinTrigger', 'totalFs': FEATURE_FS, 'positions': []})
    append_event(events, {'type': 'updateFreeSpin', 'amount': 0, 'total': FEATURE_FS})
    magnet_cluster = rng.random() < float(MODE_SETTINGS['FEATURE']['magnet_spin_rate'])
    board, magnet_target = create_guaranteed_feature_board(rng, magnet_cluster)
    board, active_symbol = prepare_board_for_reveal(rng, board, magnet_target)
    emit_reveal(events, board, 'feature')
    resolved = (
        resolve_magnet_sequence(rng, board, 'FEATURE', 'feature', target_symbol=active_symbol)
        if magnet_cluster
        else resolve_natural_sequence(rng, board, 'FEATURE', 'feature')
    )
    events.extend([{**event, 'index': len(events) + idx} for idx, event in enumerate(resolved['events'])])
    final_amount = clamp_amount(int(resolved['total_win']))
    emit_set_total(events, final_amount)
    if final_amount > 0:
        emit_set_win(events, final_amount)
    append_event(events, {'type': 'freeSpinEnd', 'amount': final_amount, 'winLevel': win_level_from_amount(final_amount)})
    append_event(events, {'type': 'finalWin', 'amount': final_amount})
    return {'events': events, 'final_amount': final_amount, 'basegame_win': 0, 'freegame_win': final_amount, 'trigger_mode': 'feature'}


def build_bonus_sequence(rng: random.Random, mode: str, trigger_positions: List[Position], running_total: int, from_base_trigger: bool) -> dict:
    events: List[dict] = []
    is_persistent = mode in ('SUPER', 'HIDDEN')
    is_hidden = mode == 'HIDDEN'
    game_type = 'hidden' if is_hidden else 'superspin' if mode == 'SUPER' else 'freegame'
    if not from_base_trigger:
        trigger_board = create_trigger_board(rng, mode)
        trigger_board, _ = prepare_board_for_reveal(rng, trigger_board)
        trigger_positions = get_scatter_positions(trigger_board)
        emit_reveal(events, trigger_board, 'basegame')
    append_event(events, {'type': 'freeSpinTrigger', 'totalFs': TOTAL_FS, 'positions': clone_positions(trigger_positions)})

    if not is_persistent:
        for spin in range(TOTAL_FS):
            append_event(events, {'type': 'updateFreeSpin', 'amount': spin, 'total': TOTAL_FS})
            board = create_board(rng, 'BONUS', magnet_count=random_magnet_count(rng, float(MODE_SETTINGS['BONUS']['magnet_spin_rate'])))
            board, active_symbol = prepare_board_for_reveal(rng, board)
            emit_reveal(events, board, 'freegame')
            resolved = resolve_magnet_sequence(rng, board, 'BONUS', 'freegame', target_symbol=active_symbol) if get_magnet_positions(board) else resolve_natural_sequence(rng, board, 'BONUS', 'freegame')
            events.extend([{**event, 'index': len(events) + idx} for idx, event in enumerate(resolved['events'])])
            spin_win = int(resolved['total_win'])
            running_total = clamp_amount(running_total + spin_win)
            emit_set_total(events, running_total)
            if spin_win > 0:
                emit_set_win(events, spin_win)
            if running_total >= MAX_WIN_X * 100:
                break
        append_event(events, {'type': 'freeSpinEnd', 'amount': running_total, 'winLevel': win_level_from_amount(running_total)})
        return {'events': events, 'final_amount': running_total}

    persistent_state = {'target_symbol': None, 'total_multiplier': 1, 'series': []}
    # Persistent bonuses build one cluster for the whole feature. It is valued
    # and paid once, after the final spin—not on every intermediate growth.
    feature_cap = MAX_WIN_AMOUNT - running_total
    for spin in range(TOTAL_FS):
        append_event(events, {'type': 'updateFreeSpin', 'amount': spin, 'total': TOTAL_FS})
        emit_super_carry(events, persistent_state['series'], persistent_state['target_symbol'], int(persistent_state['total_multiplier']))
        magnet_count = 1 if spin == 0 else random_magnet_count(
            rng, float(MODE_SETTINGS[mode]['magnet_spin_rate']) * 0.85
        )
        polarity_count = (
            1
            if spin > 0
            and persistent_state['series']
            and magnet_count == 0
            and rng.random() < float(MODE_SETTINGS[mode]['polarity_respin_rate'])
            else 0
        )
        board = create_board(
            rng,
            mode,
            magnet_count=magnet_count,
            locked_map=series_locked_map(persistent_state['series']),
            target_symbol=persistent_state['target_symbol'],
            target_boost=float(MODE_SETTINGS[mode]['target_boost']),
            polarity_count=polarity_count,
            force_multiplier_magnet=is_hidden and spin == 0,
        )
        board, active_symbol = prepare_board_for_reveal(
            rng, board, persistent_state['target_symbol']
        )
        emit_reveal(events, board, game_type)
        resolved = resolve_magnet_sequence(rng, board, mode, game_type, target_symbol=active_symbol, persistent=True, carry_series=persistent_state['series'], carry_multiplier=int(persistent_state['total_multiplier']))
        events.extend([{**event, 'index': len(events) + idx} for idx, event in enumerate(resolved['events'])])
        persistent_state = {'target_symbol': resolved['target_symbol'], 'total_multiplier': resolved['total_multiplier'], 'series': resolved['series']}
        emit_super_carry(events, persistent_state['series'], persistent_state['target_symbol'], int(persistent_state['total_multiplier']))
    final_wins = cap_wins(render_series_wins(persistent_state['series'], 1, 'super'), feature_cap)
    emit_series_resolved(events, final_wins)
    final_value = sum(win['amount'] for win in final_wins)
    if final_value > 0:
        emit_win_info(events, final_wins)
        running_total = clamp_amount(running_total + final_value)
    emit_set_total(events, running_total)
    if final_value > 0:
        emit_set_win(events, final_value)
    append_event(events, {'type': 'freeSpinEnd', 'amount': running_total, 'winLevel': win_level_from_amount(running_total)})
    return {'events': events, 'final_amount': running_total}


def build_mystery_round(rng: random.Random) -> dict:
    selected_mode = str(weighted_choice(rng, list(MYSTERY_BONUS_WEIGHTS)))
    labels = {
        'BONUS': 'GRAVITY BREACH',
        'SUPER': 'CORE OVERLOAD',
        'HIDDEN': 'ZERO POINT PROTOCOL',
    }
    bonus = build_bonus_sequence(rng, selected_mode, [], 0, False)
    events = list(bonus['events'])
    reveal_index = next(
        (index for index, event in enumerate(events) if event['type'] == 'reveal'),
        -1,
    )
    events.insert(reveal_index + 1, {
        'type': 'mysteryBonusReveal',
        'mode': selected_mode,
        'label': labels[selected_mode],
    })
    events = [{**event, 'index': index} for index, event in enumerate(events)]
    append_event(events, {'type': 'finalWin', 'amount': bonus['final_amount']})
    trigger_mode = {
        'BONUS': 'freegame',
        'SUPER': 'superspin',
        'HIDDEN': 'hidden',
    }[selected_mode]
    return {
        'events': events,
        'final_amount': bonus['final_amount'],
        'basegame_win': 0,
        'freegame_win': bonus['final_amount'],
        'trigger_mode': trigger_mode,
        'mystery_mode': selected_mode,
    }


def _forced_max_win_board(mode: str, mult1: int, mult2: int) -> List[List[RawSymbol]]:
    """Return a 7×7 board with two magnets at corners and all other cells H1."""
    board = empty_board()
    board[0][0] = make_magnet(mult1)
    board[6][6] = make_magnet(mult2)
    for reel in range(BOARD_REELS):
        for row in range(BOARD_ROWS):
            if not board[reel][row].get('magnet'):
                board[reel][row] = make_pay_symbol('H1')
    return board


# Multiplier pairs that produce specific payout levels for each mode.
# pair (m1, m2) → cluster_mult = m1*m2. Amount = 2000x * cluster_mult.
# Entries are sorted ascending so the first variant is the smallest new payout above current max.
_FORCED_PAIRS: Dict[str, List[Tuple[int, int]]] = {
    # H1 33+ pays 2000x. Products 8/9/10 produce 16k/18k/20k.
    'BASE':    [(4, 2), (3, 3), (5, 2)],
    'CHANCE':  [(4, 2), (3, 3), (5, 2)],
    'FEATURE': [(4, 2), (3, 3), (5, 2)],
    'BONUS':   [(4, 2), (3, 3), (5, 2)],
    'MYSTERY': [(4, 2), (3, 3), (5, 2)],
    'SUPER':   [(4, 2), (3, 3), (5, 2)],
}


def generate_forced_coverage_rounds(mode: str) -> List[dict]:
    """Return deterministic forced-win rounds for ``mode`` covering the gap to the 20,000× cap.

    Each returned dict has the same shape as ``generate_round_for_mode`` output and can be
    appended directly to the mode's book file.  The rounds are constructed from a predetermined
    two-magnet board that guarantees the payout reaches MAX_WIN_AMOUNT for high-multiplier pairs
    or lands at a specific intermediate level.
    """
    normalized_mode = str(mode or 'BASE').upper()
    pairs = _FORCED_PAIRS.get(normalized_mode, [])
    if not pairs:
        return []

    results = []
    for variant_idx, (m1, m2) in enumerate(pairs):
        rng = random.Random(0xDEAD_BEEF + variant_idx)
        board = _forced_max_win_board(normalized_mode, m1, m2)

        if normalized_mode in ('BASE', 'CHANCE'):
            events: List[dict] = []
            emit_reveal(events, board, 'basegame')
            resolved = resolve_magnet_sequence(rng, board, normalized_mode, 'basegame')
            events.extend([{**e, 'index': len(events) + i} for i, e in enumerate(resolved['events'])])
            total_win = clamp_amount(int(resolved['total_win']))
            emit_set_total(events, total_win)
            if total_win > 0:
                emit_set_win(events, total_win)
            append_event(events, {'type': 'finalWin', 'amount': total_win})
            results.append({
                'events': events, 'final_amount': total_win,
                'basegame_win': total_win, 'freegame_win': 0, 'trigger_mode': None,
            })

        elif normalized_mode == 'FEATURE':
            events = []
            append_event(events, {'type': 'freeSpinTrigger', 'totalFs': FEATURE_FS, 'positions': []})
            append_event(events, {'type': 'updateFreeSpin', 'amount': 0, 'total': FEATURE_FS})
            emit_reveal(events, board, 'feature')
            resolved = resolve_magnet_sequence(rng, board, 'FEATURE', 'feature')
            events.extend([{**e, 'index': len(events) + i} for i, e in enumerate(resolved['events'])])
            final_amount = clamp_amount(int(resolved['total_win']))
            emit_set_total(events, final_amount)
            if final_amount > 0:
                emit_set_win(events, final_amount)
            append_event(events, {'type': 'freeSpinEnd', 'amount': final_amount, 'winLevel': win_level_from_amount(final_amount)})
            append_event(events, {'type': 'finalWin', 'amount': final_amount})
            results.append({
                'events': events, 'final_amount': final_amount,
                'basegame_win': 0, 'freegame_win': final_amount, 'trigger_mode': 'feature',
            })

        elif normalized_mode == 'BONUS':
            events = []
            trigger_board = create_trigger_board(rng, 'BONUS')
            trigger_positions = get_scatter_positions(trigger_board)
            emit_reveal(events, trigger_board, 'basegame')
            append_event(events, {'type': 'freeSpinTrigger', 'totalFs': TOTAL_FS, 'positions': clone_positions(trigger_positions)})
            running_total = 0
            append_event(events, {'type': 'updateFreeSpin', 'amount': 0, 'total': TOTAL_FS})
            emit_reveal(events, board, 'freegame')
            resolved = resolve_magnet_sequence(rng, board, 'BONUS', 'freegame')
            events.extend([{**e, 'index': len(events) + i} for i, e in enumerate(resolved['events'])])
            spin_win = int(resolved['total_win'])
            running_total = clamp_amount(running_total + spin_win)
            emit_set_total(events, running_total)
            if spin_win > 0:
                emit_set_win(events, spin_win)
            append_event(events, {'type': 'freeSpinEnd', 'amount': running_total, 'winLevel': win_level_from_amount(running_total)})
            append_event(events, {'type': 'finalWin', 'amount': running_total})
            results.append({
                'events': events, 'final_amount': running_total,
                'basegame_win': 0, 'freegame_win': running_total, 'trigger_mode': 'freegame',
            })

        else:  # SUPER / forced MYSTERY coverage via Core Overload
            events = []
            if normalized_mode == 'MYSTERY':
                append_event(events, {
                    'type': 'mysteryBonusReveal',
                    'mode': 'SUPER',
                    'label': 'CORE OVERLOAD',
                })
            trigger_board = create_trigger_board(rng, 'SUPER')
            trigger_positions = get_scatter_positions(trigger_board)
            emit_reveal(events, trigger_board, 'basegame')
            append_event(events, {'type': 'freeSpinTrigger', 'totalFs': TOTAL_FS, 'positions': clone_positions(trigger_positions)})
            persistent_state: dict = {'target_symbol': None, 'total_multiplier': 1, 'series': []}
            running_total = 0
            for spin in range(TOTAL_FS):
                append_event(events, {'type': 'updateFreeSpin', 'amount': spin, 'total': TOTAL_FS})
                emit_super_carry(events, persistent_state['series'], persistent_state['target_symbol'], int(persistent_state['total_multiplier']))
                spin_board = board if spin == 0 else create_board(
                    rng, 'SUPER', magnet_count=0,
                    locked_map=series_locked_map(persistent_state['series']),
                    target_symbol=persistent_state['target_symbol'],
                    target_boost=float(MODE_SETTINGS['SUPER']['target_boost']),
                )
                emit_reveal(events, spin_board, 'superspin')
                resolved = resolve_magnet_sequence(
                    rng, spin_board, 'SUPER', 'superspin',
                    target_symbol=persistent_state['target_symbol'],
                    persistent=True,
                    carry_series=persistent_state['series'],
                    carry_multiplier=int(persistent_state['total_multiplier']),
                )
                events.extend([{**e, 'index': len(events) + i} for i, e in enumerate(resolved['events'])])
                persistent_state = {
                    'target_symbol': resolved['target_symbol'],
                    'total_multiplier': resolved['total_multiplier'],
                    'series': resolved['series'],
                }
                emit_super_carry(events, persistent_state['series'], persistent_state['target_symbol'], int(persistent_state['total_multiplier']))
                emit_set_total(events, running_total)
            final_wins = cap_wins(
                render_series_wins(persistent_state['series'], 1, 'super'),
                MAX_WIN_AMOUNT - running_total,
            )
            emit_series_resolved(events, final_wins)
            final_award = emit_win_info(events, final_wins) if final_wins else 0
            running_total = clamp_amount(running_total + final_award)
            emit_set_total(events, running_total)
            if final_award > 0:
                emit_set_win(events, final_award)
            append_event(events, {'type': 'freeSpinEnd', 'amount': running_total, 'winLevel': win_level_from_amount(running_total)})
            append_event(events, {'type': 'finalWin', 'amount': running_total})
            results.append({
                'events': events, 'final_amount': running_total,
                'basegame_win': 0, 'freegame_win': running_total, 'trigger_mode': 'superspin',
            })

    return results


def generate_round_for_mode(mode: str = 'BASE', seed: Optional[int] = None, forced_criteria: Optional[str] = None) -> dict:
    normalized_mode = str(mode or 'BASE').upper()
    seed_value = seed if seed is not None else random.randrange(1 << 30)
    rng = random.Random(seed_value + 1)
    if normalized_mode == 'FEATURE':
        return build_feature_round(rng)
    if normalized_mode == 'MYSTERY':
        return build_mystery_round(rng)
    if normalized_mode in ('BONUS', 'SUPER'):
        result = build_bonus_sequence(rng, normalized_mode, [], 0, False)
        append_event(result['events'], {'type': 'finalWin', 'amount': result['final_amount']})
        return {'events': result['events'], 'final_amount': result['final_amount'], 'basegame_win': 0, 'freegame_win': result['final_amount'], 'trigger_mode': 'superspin' if normalized_mode == 'SUPER' else 'freegame'}

    if forced_criteria in ('bonus', 'super', 'hidden'):
        # A controlled share of trigger books demonstrates collection from 1-2
        # scatters through real cluster respins. The per-respin addition still
        # uses the configured 10%/30% roll; retrying here only fills the requested
        # lookup criterion and does not alter its production weight.
        collect_rate = float(RESPIN_SCATTER_RATES.get(normalized_mode, 0.0))
        if rng.random() < collect_rate:
            collected_kind = f'collected_{forced_criteria}'
            wanted_mode = {
                'bonus': 'freegame',
                'super': 'superspin',
                'hidden': 'hidden',
            }[forced_criteria]
            for attempt in range(4096):
                attempt_seed = (seed_value + 1) * 1_000_003 + attempt * 97_409
                result = build_base_round(
                    random.Random(attempt_seed),
                    normalized_mode,
                    collected_kind,
                )
                if result['trigger_mode'] == wanted_mode:
                    return result

        return build_base_round(rng, normalized_mode, forced_criteria)

    forced_trigger = forced_criteria if forced_criteria in ('bonus', 'super', 'hidden') else ('none' if forced_criteria in ('0', 'basegame') else None)
    return build_base_round(rng, normalized_mode, forced_trigger)
