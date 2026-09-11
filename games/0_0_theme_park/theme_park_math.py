"""Theme Park math engine for math-sdk.

Pure-python round generator (magnetic-style custom pipeline, no Rust optimizer).
All win amounts are integer cents of bet (100 = 1.00x). Boards are emitted with
7 rows per reel (1 pad top, 5 visible, 1 pad bottom); every event position uses
VISIBLE coordinates {reel: 0-4, row: 0-4}.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from math_targets import ANTE_RATES, BASE_RATES

BOARD_REELS = 5
VISIBLE_ROWS = 5
PADDED_ROWS = 7
ROW_OFFSET = 1

MAX_WIN_X = 25000
MAX_WIN_AMOUNT = MAX_WIN_X * 100  # 2,500,000 cents

TOTAL_FS = 10
TOTAL_PICKS = 10
DUCK_POND_SIZE = 25

WILD = 'W'
DC = 'DC'
S_DUCK = 'S_DUCK'
S_ROLLER = 'S_ROLLER'
S_COASTER = 'S_COASTER'
SCATTER_SYMBOLS = (S_DUCK, S_ROLLER, S_COASTER)
SCATTER_FOR_FEATURE = {'duck': S_DUCK, 'roller': S_ROLLER, 'coaster': S_COASTER}
BONUS_TYPE_FOR_FEATURE = {'roller': 'roller', 'coaster': 'coaster'}

PREMIUMS = ['H1', 'H2', 'H3', 'H4', 'H5']
LOWS = ['L1', 'L2', 'L3', 'L4', 'L5']
PAY_SYMBOLS = PREMIUMS + LOWS

PAYTABLE: Dict[str, Dict[int, float]] = {
    'H1': {3: 2, 4: 10, 5: 20},
    'H2': {3: 1, 4: 5, 5: 10},
    'H3': {3: 1, 4: 5, 5: 10},
    'H4': {3: 0.5, 4: 2.5, 5: 5},
    'H5': {3: 0.5, 4: 2.5, 5: 5},
    'L1': {3: 0.1, 4: 0.5, 5: 1},
    'L2': {3: 0.1, 4: 0.5, 5: 1},
    'L3': {3: 0.1, 4: 0.5, 5: 1},
    'L4': {3: 0.1, 4: 0.5, 5: 1},
    'L5': {3: 0.1, 4: 0.5, 5: 1},
}

# 15 fixed paylines (1-based keys, row index per reel, visible coords).
# Source of truth: client "Paylines Table" asset (5 straights + 2 diagonals + 8 zigzags).
PAYLINES: Dict[int, List[int]] = {
    1: [0, 0, 0, 0, 0],
    2: [1, 1, 1, 1, 1],
    3: [2, 2, 2, 2, 2],
    4: [3, 3, 3, 3, 3],
    5: [4, 4, 4, 4, 4],
    6: [0, 1, 2, 3, 4],
    7: [4, 3, 2, 1, 0],
    8: [0, 1, 0, 1, 0],
    9: [1, 0, 1, 0, 1],
    10: [1, 2, 1, 2, 1],
    11: [2, 1, 2, 1, 2],
    12: [2, 3, 2, 3, 2],
    13: [3, 2, 3, 2, 3],
    14: [3, 4, 3, 4, 3],
    15: [4, 3, 4, 3, 4],
}

# ---------------------------------------------------------------------------
# Duck pools (value: weight). "mult" adds value*100 cents, "multmult" multiplies
# the running total. First flip/pick is always "mult".
# ---------------------------------------------------------------------------
MM_RATE = 0.12

# Base-game duck collect (design doc pools).
BASE_DUCK_DIRECT_POOL: List[Tuple[int, float]] = [
    (2, 300), (3, 250), (5, 200), (10, 120), (15, 80),
    (25, 40), (50, 15), (100, 5), (250, 2), (500, 0.5),
]
BASE_DUCK_MM_POOL: List[Tuple[int, float]] = [
    (2, 500), (3, 250), (5, 150), (10, 70), (25, 20), (50, 8), (100, 2),
]

# Duck Your Luck bonus pools — tuned so the 10-pick lump sum EV lands near
# 96x (0.961 * 100x mode cost). Same value sets, different weights.
DUCK_BONUS_DIRECT_POOL: List[Tuple[int, float]] = [
    (2, 460), (3, 300), (5, 195), (10, 80), (15, 30),
    (25, 12), (50, 4), (100, 1.3), (250, 0.4), (500, 0.15),
]
DUCK_BONUS_MM_POOL: List[Tuple[int, float]] = [
    (2, 700), (3, 220), (5, 60), (10, 15), (25, 3), (50, 0.8), (100, 0.2),
]

# FSPIN1 (20x buy): at least one DC is guaranteed and every board count 1-25
# remains possible. Same prize value sets as the base pools.
FSPIN1_DIRECT_POOL: List[Tuple[int, float]] = [
    (2, 120), (3, 150), (5, 220), (10, 220), (15, 140),
    (25, 90), (50, 40), (100, 15), (250, 4), (500, 1),
]
FSPIN1_MM_POOL: List[Tuple[int, float]] = list(BASE_DUCK_MM_POOL)
FSPIN1_DUCK_COUNT_DIST: List[Tuple[int, float]] = [
    (1, 50), (2, 25), (3, 12), (4, 6), (5, 3), (6, 1.5),
    (7, 0.75), (8, 0.4), (9, 0.2), (10, 0.1), (11, 0.05),
    (12, 0.025),
    *[(count, 0.01) for count in range(13, 26)],
]

# Base-game duck collect symbol-count distribution (max 1 DC per reel).
BASE_DC_COUNT_DIST: List[Tuple[int, float]] = [(1, 70), (2, 20), (3, 7), (4, 2.5), (5, 0.5)]

# ---------------------------------------------------------------------------
# Roller wild pools
# ---------------------------------------------------------------------------
ROLLER_MULT_POOL: List[Tuple[int, float]] = [
    (2, 400), (3, 250), (5, 150), (10, 60), (25, 15), (50, 4), (100, 1),
]
# One transformed reel now rolls exactly one plaque value. The previous presentation could emit
# sparse row plaques and sum them, including a neutral 1x when none landed. Its mean was 4.226x;
# this single-roll pool is 4.225x, preserving feature contribution while matching the new gameplay.
ROLLER_SINGLE_MULT_POOL: List[Tuple[int, float]] = [
    (2, 400), (3, 250), (5, 150), (10, 60), (25, 15), (50, 4), (100, 2.5),
]
# Per-spin full-wild-reel count during the Roller Wilds bonus (design Q4).
ROLLER_COUNT_DIST: List[Tuple[int, float]] = [
    (0, 55), (1, 30), (2, 10), (3, 4), (4, 0.9), (5, 0.1),
]
# Rare base-game roller wild event (1-2 reels).
BASE_ROLLER_COUNT_DIST: List[Tuple[int, float]] = [(1, 80), (2, 20)]

# FSPIN2 (60x buy, single spin, guaranteed 1+ wild reels).
FSPIN2_COUNT_DIST: List[Tuple[int, float]] = [(1, 62), (2, 26), (3, 9), (4, 2.6), (5, 0.4)]

# ---------------------------------------------------------------------------
# Mega Coaster setup
# ---------------------------------------------------------------------------
COASTER_PUKE_COUNT_DIST: List[Tuple[int, float]] = [
    (4, 1.5), (5, 16), (6, 21), (7, 22), (8, 18), (9, 11.5), (10, 6.5), (11, 3.5), (12, 1.5),
]
COASTER_MAX_DISTINCT_TILES = 10
COASTER_MAX_TILE_MULT = 1024

# Hot rail: rare escalation where the cart keeps hitting the same tile, doubling it up to
# the target below. Uniform puke placement alone tops out near 16x-32x per tile, which
# capped natural COASTER books at ~11,300x; this tail makes the 25,000x max win reachable
# (raw cap rate ~1/5,000 rounds). The count-dist above is trimmed slightly so the added
# tail keeps raw COASTER RTP at the pre-change level before lookup weighting.
COASTER_HOT_RAIL_RATE = 1 / 360
COASTER_HOT_RAIL_TARGET_DIST: List[Tuple[int, float]] = [
    (64, 40), (128, 26), (256, 16), (512, 10), (1024, 8),
]

# ---------------------------------------------------------------------------
# Mode feature rates (per-round probabilities in BASE/ANTE natural generation).
# ANTE = 3x scatter trigger rates.
# ---------------------------------------------------------------------------
MODE_SETTINGS = {
    'BASE': {
        'duck_rate': BASE_RATES['duck'],
        'roller_rate': BASE_RATES['roller'],
        'coaster_rate': BASE_RATES['coaster'],
        'duckcollect_rate': BASE_RATES['duckcollect'],
        'base_rollerwild_rate': 1 / 250,
        'teaser_scatter_rate': 0.10,
    },
    'ANTE': {
        'duck_rate': ANTE_RATES['duck'],
        'roller_rate': ANTE_RATES['roller'],
        'coaster_rate': ANTE_RATES['coaster'],
        'duckcollect_rate': ANTE_RATES['duckcollect'],
        'base_rollerwild_rate': 1 / 250,
        'teaser_scatter_rate': 0.16,
    },
}

TRIGGER_SCATTER_COUNT_DIST: List[Tuple[int, float]] = [(3, 100)]

# ---------------------------------------------------------------------------
# Reelstrips — weighted, deterministic (module-level fixed seed so every
# process/thread sees identical strips). Strips contain pay symbols only;
# DC / scatters / wilds are placed procedurally to hit exact rates.
# ---------------------------------------------------------------------------
BASE_STRIP_WEIGHTS = {
    'L5': 24, 'L4': 19, 'L3': 14, 'L2': 11, 'L1': 9,
    'H5': 6, 'H4': 5, 'H3': 4, 'H2': 4, 'H1': 3,
}
ROLLER_STRIP_WEIGHTS = {
    'L5': 24, 'L4': 19, 'L3': 14, 'L2': 11, 'L1': 9,
    'H5': 6, 'H4': 5, 'H3': 4, 'H2': 4, 'H1': 3,
}
COASTER_STRIP_WEIGHTS = {
    'L5': 6, 'L4': 6, 'L3': 6, 'L2': 5, 'L1': 5,
    'H5': 10, 'H4': 10, 'H3': 11, 'H2': 11, 'H1': 11,
}
FSPIN2_STRIP_WEIGHTS = {
    'L5': 12, 'L4': 12, 'L3': 12, 'L2': 12, 'L1': 12,
    'H5': 5, 'H4': 5, 'H3': 4, 'H2': 3, 'H1': 3,
}

STRIP_LENGTH = 200
BASE_STACK_PROB = 0.18
FREEGAME_STACK_PROB = 0.22
FSPIN2_STACK_PROB = 0.15


def weighted_choice(rng: random.Random, entries: List[Tuple[object, float]]):
    total = sum(weight for _, weight in entries)
    roll = rng.random() * total
    for value, weight in entries:
        roll -= weight
        if roll < 0:
            return value
    return entries[-1][0]


def _build_strips(weights: Dict[str, float], stack_prob: float, seed: int, length: int = STRIP_LENGTH) -> List[List[str]]:
    entries = list(weights.items())
    strips = []
    for reel in range(BOARD_REELS):
        rng = random.Random(seed + reel * 101)
        strip: List[str] = []
        while len(strip) < length:
            symbol = str(weighted_choice(rng, entries))
            run = 1
            if rng.random() < stack_prob:
                run = 2 if rng.random() < 0.75 else 3
            for _ in range(min(run, length - len(strip))):
                strip.append(symbol)
        strips.append(strip)
    return strips


BASE_STRIPS = _build_strips(BASE_STRIP_WEIGHTS, BASE_STACK_PROB, 20260718)
ROLLER_STRIPS = _build_strips(ROLLER_STRIP_WEIGHTS, FREEGAME_STACK_PROB, 20260719)
COASTER_STRIPS = _build_strips(COASTER_STRIP_WEIGHTS, FREEGAME_STACK_PROB, 20260720)
FSPIN2_STRIPS = _build_strips(FSPIN2_STRIP_WEIGHTS, FSPIN2_STACK_PROB, 20260721)

# Padding reels shown by the frontend before a reveal (config file only).
BASE_PADDING_REELS = [
    ['L1', 'H1', 'L4', 'S_DUCK', 'H3', 'L2', 'DC', 'L5', 'H4', 'L3', 'S_ROLLER', 'L1'],
    ['L2', 'L5', 'H2', 'L3', 'S_COASTER', 'H5', 'L1', 'DC', 'H3', 'L4', 'H1', 'L2'],
    ['L3', 'L1', 'H4', 'S_ROLLER', 'L4', 'H1', 'L5', 'H2', 'L2', 'DC', 'H5', 'L3'],
    ['L4', 'H3', 'L2', 'L5', 'S_DUCK', 'H4', 'L1', 'H5', 'L3', 'H1', 'DC', 'L4'],
    ['L5', 'H5', 'L1', 'L2', 'S_COASTER', 'H1', 'L3', 'H2', 'L4', 'H3', 'DC', 'L5'],
]
FREEGAME_PADDING_REELS = [
    ['H1', 'L1', 'L4', 'H2', 'W', 'L2', 'H3', 'L5', 'H4', 'L3', 'H5', 'H1'],
    ['L2', 'H1', 'H2', 'L3', 'W', 'H5', 'L1', 'H4', 'H3', 'L4', 'H1', 'L2'],
    ['L3', 'H2', 'H4', 'W', 'L4', 'H1', 'L5', 'H2', 'L2', 'H3', 'H5', 'L3'],
    ['H4', 'H3', 'L2', 'L5', 'W', 'H4', 'L1', 'H5', 'L3', 'H1', 'H2', 'L4'],
    ['L5', 'H5', 'H1', 'L2', 'W', 'H1', 'L3', 'H2', 'L4', 'H3', 'H2', 'L5'],
]


# ---------------------------------------------------------------------------
# Board helpers
# ---------------------------------------------------------------------------
def _cell(name: str) -> dict:
    out: dict = {'name': name}
    if name == WILD:
        out['wild'] = True
    elif name in SCATTER_SYMBOLS:
        out['scatter'] = True
    elif name == DC:
        out['duck'] = True
    return out


def _wild_cell(multiplier: int = 0, persistent: bool = False, reel_multiplier: Optional[int] = None) -> dict:
    out: dict = {'name': WILD, 'wild': True}
    if multiplier > 0:
        out['multiplier'] = int(multiplier)
    if reel_multiplier is not None:
        out['reelMultiplier'] = max(1, int(reel_multiplier))
    if persistent:
        out['persistent'] = True
    return out


def spin_board(rng: random.Random, strips: List[List[str]]) -> List[List[dict]]:
    """Return a padded 5x7 board of cell dicts (row 0 = pad top, rows 1-5 visible, row 6 = pad bottom)."""
    board = []
    for strip in strips:
        stop = rng.randrange(len(strip))
        board.append([_cell(strip[(stop + i) % len(strip)]) for i in range(PADDED_ROWS)])
    return board


def uniform_board(symbol: str) -> List[List[dict]]:
    return [[_cell(symbol) for _ in range(PADDED_ROWS)] for _ in range(BOARD_REELS)]


NO_WIN_CYCLE = ['L1', 'L2', 'L3', 'L4', 'L5']


def no_win_board() -> List[List[dict]]:
    """Board guaranteed to have zero line wins: reel r shows only NO_WIN_CYCLE[r]."""
    return [[_cell(NO_WIN_CYCLE[r]) for _ in range(PADDED_ROWS)] for r in range(BOARD_REELS)]


def set_visible(board: List[List[dict]], reel: int, row: int, cell: dict) -> None:
    board[reel][row + ROW_OFFSET] = cell


def get_visible(board: List[List[dict]], reel: int, row: int) -> dict:
    return board[reel][row + ROW_OFFSET]


def apply_wild_reel(board: List[List[dict]], reel: int, multiplier: int) -> None:
    """Apply one multiplier to the complete transformed reel."""
    reel_multiplier = max(1, int(multiplier))
    for row in range(VISIBLE_ROWS):
        set_visible(board, reel, row, _wild_cell(reel_multiplier=reel_multiplier))


def place_wild_reel_triggers(board: List[List[dict]], wild_reels: List[dict]) -> None:
    """Show one landing wild per future transformed reel before the animation."""
    for entry in wild_reels:
        row = int(entry.get('triggerRow', 2))
        trigger = _wild_cell()
        trigger['rollerTrigger'] = True
        set_visible(board, int(entry['reel']), row, trigger)


def apply_persistent_tiles(board: List[List[dict]], tiles: List[dict]) -> None:
    for tile in tiles:
        set_visible(board, tile['reel'], tile['row'], _wild_cell(tile['multiplier'], persistent=True))


def place_scatters(rng: random.Random, board: List[List[dict]], scatter_symbol: str, count: int) -> List[dict]:
    reels = sorted(rng.sample(range(BOARD_REELS), count))
    positions = []
    for reel in reels:
        row = rng.randrange(VISIBLE_ROWS)
        set_visible(board, reel, row, _cell(scatter_symbol))
        positions.append({'reel': reel, 'row': row})
    return positions


def place_teaser_scatters(rng: random.Random, board: List[List[dict]]) -> None:
    """Place one non-triggering scatter.

    Exact two-scatter terminal boards are forbidden: seeing a second scatter is
    reserved for a real 3+ scatter feature result, so the later landing is
    guaranteed to complete the trigger.
    """
    reel = rng.randrange(BOARD_REELS)
    symbol = SCATTER_SYMBOLS[rng.randrange(len(SCATTER_SYMBOLS))]
    set_visible(board, reel, rng.randrange(VISIBLE_ROWS), _cell(symbol))


def place_dc_symbols(rng: random.Random, board: List[List[dict]], count: int,
                     one_per_reel: bool = True) -> List[dict]:
    """Place DC symbols and return their visible positions in board order."""
    if one_per_reel:
        cells = [(reel, rng.randrange(VISIBLE_ROWS)) for reel in sorted(rng.sample(range(BOARD_REELS), count))]
    else:
        cells = sorted(rng.sample(
            [(reel, row) for reel in range(BOARD_REELS) for row in range(VISIBLE_ROWS)],
            count,
        ))
    positions = []
    for reel, row in cells:
        set_visible(board, reel, row, _cell(DC))
        positions.append({'reel': reel, 'row': row})
    return positions


# ---------------------------------------------------------------------------
# Line evaluation
# ---------------------------------------------------------------------------
def evaluate_board(board: List[List[dict]]) -> dict:
    """Left-to-right line evaluation with wild substitution.

    Multiplier-bearing wilds crossed by a winning line SUM to form the line
    multiplier. Wilds substitute regular symbols but never pay by themselves.
    """
    wins = []
    total = 0
    for line_key, line in PAYLINES.items():
        best = None
        for symbol in PAY_SYMBOLS:
            count = 0
            positions = []
            mult_sum = 0
            has_literal_symbol = False
            for reel in range(BOARD_REELS):
                row = line[reel]
                cell = get_visible(board, reel, row)
                name = cell['name']
                if name == symbol or (name == WILD and cell.get('wild')):
                    count += 1
                    positions.append({'reel': reel, 'row': row})
                    has_literal_symbol = has_literal_symbol or name == symbol
                    if name == WILD:
                        # Full-reel plaques apply to every line crossing that reel,
                        # independent of which rows display the plaques. Different
                        # wild reels then add naturally into this line total.
                        mult_sum += max(0, int(cell.get('reelMultiplier', cell.get('multiplier', 0))))
                    continue
                break
            pay_x = PAYTABLE[symbol].get(count, 0)
            # Wilds substitute regular symbols. Three/four Wilds need a literal symbol to
            # complete; five Wilds form the special 20x H1 line and take Wild multipliers.
            if pay_x <= 0 or (not has_literal_symbol and count != 5):
                continue
            base_amount = int(round(pay_x * 100))
            line_mult = mult_sum if mult_sum > 0 else 1
            win_amount = base_amount * line_mult
            if best is None or win_amount > best['win']:
                best = {
                    'symbol': symbol,
                    'kind': count,
                    'win': win_amount,
                    'positions': positions,
                    'meta': {
                        'lineIndex': line_key - 1,
                        'multiplier': line_mult,
                        'winWithoutMult': base_amount,
                        'lineMultiplier': line_mult,
                    },
                }
        if best is not None:
            wins.append(best)
            total += best['win']
    return {'wins': wins, 'totalWinAmount': total}


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


# ---------------------------------------------------------------------------
# Round context / event emission
# ---------------------------------------------------------------------------
class RoundCtx:
    def __init__(self) -> None:
        self.events: List[dict] = []
        self.total = 0
        self.base_win = 0
        self.free_win = 0
        self.capped = False
        self._wincap_emitted = False

    def emit(self, payload: dict) -> None:
        event = dict(payload)
        event['index'] = len(self.events)
        self.events.append(event)

    def award(self, amount: int, bucket: str) -> int:
        allowed = max(0, min(int(amount), MAX_WIN_AMOUNT - self.total))
        self.total += allowed
        if bucket == 'base':
            self.base_win += allowed
        else:
            self.free_win += allowed
        if self.total >= MAX_WIN_AMOUNT:
            self.capped = True
        return allowed

    def remaining(self) -> int:
        return MAX_WIN_AMOUNT - self.total

    def emit_wincap_if_needed(self) -> None:
        if self.capped and not self._wincap_emitted:
            self.emit({'type': 'wincap', 'amount': MAX_WIN_AMOUNT})
            self._wincap_emitted = True


def calc_padding_positions(rng: random.Random) -> List[int]:
    base = 1 if rng.randrange(2) == 0 else 2
    return [base, base + 2, base + 4, base + 6, base + 8]


def _scatter_anticipation(board: List[List[dict]]) -> List[int]:
    best = [0] * BOARD_REELS
    for symbol in SCATTER_SYMBOLS:
        flags = [
            any(get_visible(board, reel, row)['name'] == symbol for row in range(VISIBLE_ROWS))
            for reel in range(BOARD_REELS)
        ]
        if sum(flags) < 2:
            continue
        out = [0] * BOARD_REELS
        counter = 0
        for reel in range(BOARD_REELS):
            if sum(flags[:reel]) >= 2:
                counter += 1
                out[reel] = counter
        if sum(out) > sum(best):
            best = out
    return best


def emit_reveal(ctx: RoundCtx, rng: random.Random, board: List[List[dict]], game_type: str) -> None:
    ctx.emit({
        'type': 'reveal',
        'board': [[dict(cell) for cell in reel] for reel in board],
        'paddingPositions': calc_padding_positions(rng),
        'anticipation': _scatter_anticipation(board),
        'gameType': game_type,
    })


def emit_line_wins(ctx: RoundCtx, eval_result: dict, bucket: str) -> int:
    """Emit winInfo (if any wins) and award to the round; returns awarded amount."""
    wins = eval_result['wins']
    if not wins:
        return 0
    total = sum(win['win'] for win in wins)
    ctx.emit({
        'type': 'winInfo',
        'totalWin': total,
        'wins': [
            {
                'symbol': win['symbol'],
                'kind': win['kind'],
                'win': win['win'],
                'positions': [dict(p) for p in win['positions']],
                'meta': dict(win['meta']),
            }
            for win in wins
        ],
    })
    return ctx.award(total, bucket)


# ---------------------------------------------------------------------------
# Duck mechanics
# ---------------------------------------------------------------------------
def roll_duck_sequence(rng: random.Random, count: int, direct_pool, mm_pool) -> List[Tuple[str, int]]:
    seq: List[Tuple[str, int]] = []
    for i in range(count):
        if i == 0 or rng.random() >= MM_RATE:
            seq.append(('mult', int(weighted_choice(rng, direct_pool))))
        else:
            seq.append(('multmult', int(weighted_choice(rng, mm_pool))))
    return seq


def run_duck_collect(ctx: RoundCtx, positions: List[dict], sequence: List[Tuple[str, int]]) -> None:
    """Base-game / FSPIN1 duck collect. Emits start/reveal/end, awards to base bucket."""
    ctx.emit({'type': 'duckCollectStart', 'positions': [dict(p) for p in positions]})
    remaining_cap = ctx.remaining()
    running = 0
    for position, (kind, value) in zip(positions, sequence):
        if kind == 'mult':
            running += value * 100
        else:
            running *= value
        ctx.emit({
            'type': 'duckReveal',
            'position': dict(position),
            'kind': kind,
            'value': value,
            'runningTotal': min(running, remaining_cap),
        })
        if running >= remaining_cap:
            break
    paid = ctx.award(running, 'base')
    ctx.emit({'type': 'duckCollectEnd', 'amount': paid})
    ctx.emit_wincap_if_needed()


def run_duck_pick_bonus(
    ctx: RoundCtx,
    pool: List[Tuple[str, int]],
    trigger_positions: List[dict],
) -> None:
    """Duck Your Luck: 25 shown prizes, 10 picked outcomes, lump sum award.

    The first ten pool entries are assigned to the player's ten selections in
    click order. The remaining fifteen are reveal-only alternatives. This keeps
    the RGS book deterministic while allowing the client to choose any pond
    positions. All ten pick events are emitted even after the win cap is met so
    the manual-pick contract can always complete.
    """
    if len(pool) != DUCK_POND_SIZE:
        raise ValueError(f'Duck Your Luck pool must contain {DUCK_POND_SIZE} prizes')
    ctx.emit({
        'type': 'duckPickStart',
        'totalPicks': TOTAL_PICKS,
        'pool': [{'kind': kind, 'value': value} for kind, value in pool],
        # Explicit positions let the client hold and animate the three landed
        # Duck Your Luck scatters before replacing the reels with the pond.
        'positions': [dict(position) for position in trigger_positions],
    })
    remaining_cap = ctx.remaining()
    running = 0
    for pick_index, (kind, value) in enumerate(pool[:TOTAL_PICKS]):
        if kind == 'mult':
            running += value * 100
        else:
            running *= value
        running = min(running, remaining_cap)
        ctx.emit({
            'type': 'duckPick',
            'pickIndex': pick_index,
            'kind': kind,
            'value': value,
            'runningTotal': running,
        })
    paid = ctx.award(running, 'free')
    ctx.emit({'type': 'duckPickEnd', 'amount': paid})
    ctx.emit({'type': 'setTotalWin', 'amount': ctx.total})
    ctx.emit_wincap_if_needed()


# ---------------------------------------------------------------------------
# Roller wilds
# ---------------------------------------------------------------------------
def roll_wild_reels(rng: random.Random, count_dist, mult_pool) -> List[dict]:
    count = int(weighted_choice(rng, count_dist))
    if count <= 0:
        return []
    reels = sorted(rng.sample(range(BOARD_REELS), count))
    results = []
    for reel in reels:
        multiplier = max(1, int(weighted_choice(rng, mult_pool)))
        fake_pool = [
            (value, weight)
            for value, weight in mult_pool
            if max(1, int(value)) != multiplier
        ]
        fake_multiplier = max(1, int(weighted_choice(rng, fake_pool)))
        results.append({
            'reel': reel,
            'triggerRow': rng.randrange(VISIBLE_ROWS),
            # Presentation-only first face. Guaranteed distinct and never used for payout.
            'fakeMultiplier': fake_multiplier,
            'multiplier': multiplier,
        })
    return results


def transformed_wild_board(board: List[List[dict]], wild_reels: List[dict]) -> List[List[dict]]:
    transformed = [[dict(cell) for cell in reel] for reel in board]
    for entry in wild_reels:
        apply_wild_reel(
            transformed,
            int(entry['reel']),
            int(entry['multiplier']),
        )
    return transformed


def complete_wild_reel_entries(wild_reels: List[dict]) -> List[dict]:
    """Upgrade deterministic/legacy entries to fake + real plaque values per transformed reel."""
    completed = []
    for index, raw in enumerate(wild_reels):
        entry = dict(raw)
        entry.setdefault('triggerRow', (int(entry['reel']) + index) % VISIBLE_ROWS)
        # Legacy forced inputs may still carry the obsolete sparse plaque array. Collapse it once,
        # then emit only the final reel value under the new event contract.
        if 'multipliers' in entry:
            legacy_total = sum(int(item['multiplier']) for item in entry.pop('multipliers'))
            if legacy_total > 0:
                entry['multiplier'] = legacy_total
        entry['multiplier'] = max(1, int(entry['multiplier']))
        entry.setdefault(
            'fakeMultiplier',
            next(
                max(1, int(value))
                for value, _weight in ROLLER_SINGLE_MULT_POOL
                if max(1, int(value)) != entry['multiplier']
            ),
        )
        entry['fakeMultiplier'] = max(1, int(entry['fakeMultiplier']))
        completed.append(entry)
    return completed


def run_roller_freegame(ctx: RoundCtx, rng: random.Random, trigger_positions: List[dict]) -> None:
    ctx.emit({'type': 'freeSpinTrigger', 'totalFs': TOTAL_FS, 'positions': [dict(p) for p in trigger_positions], 'bonusType': 'roller'})
    for spin in range(TOTAL_FS):
        ctx.emit({'type': 'updateFreeSpin', 'amount': spin, 'total': TOTAL_FS})
        board = spin_board(rng, ROLLER_STRIPS)
        wild_reels = roll_wild_reels(rng, ROLLER_COUNT_DIST, ROLLER_SINGLE_MULT_POOL)
        presentation_board = [[dict(cell) for cell in reel] for reel in board]
        place_wild_reel_triggers(presentation_board, wild_reels)
        transformed_board = transformed_wild_board(board, wild_reels)
        emit_reveal(ctx, rng, presentation_board, 'freegame')
        if wild_reels:
            ctx.emit({'type': 'rollerWildsApply', 'reels': [dict(e) for e in wild_reels]})
        awarded = emit_line_wins(ctx, evaluate_board(transformed_board), 'free')
        if awarded > 0:
            ctx.emit({'type': 'setTotalWin', 'amount': ctx.total})
        if ctx.capped:
            ctx.emit_wincap_if_needed()
            break
    ctx.emit({'type': 'freeSpinEnd', 'amount': ctx.total, 'winLevel': win_level_from_amount(ctx.total)})


# ---------------------------------------------------------------------------
# Mega Coaster
# ---------------------------------------------------------------------------
def roll_coaster_setup(rng: random.Random) -> Tuple[List[dict], List[dict]]:
    puke_count = int(weighted_choice(rng, COASTER_PUKE_COUNT_DIST))
    tiles: Dict[Tuple[int, int], int] = {}
    pukes: List[dict] = []
    for _ in range(puke_count):
        cell = (rng.randrange(BOARD_REELS), rng.randrange(VISIBLE_ROWS))
        if cell not in tiles and len(tiles) >= COASTER_MAX_DISTINCT_TILES:
            existing = sorted(tiles.keys())
            cell = existing[rng.randrange(len(existing))]
        if cell in tiles:
            tiles[cell] = min(tiles[cell] * 2, COASTER_MAX_TILE_MULT)
        else:
            tiles[cell] = 2
        pukes.append({'reel': cell[0], 'row': cell[1], 'multiplier': tiles[cell]})
    if tiles and rng.random() < COASTER_HOT_RAIL_RATE:
        hot_cells = sorted(tiles.keys())
        hot_cell = hot_cells[rng.randrange(len(hot_cells))]
        target = int(weighted_choice(rng, COASTER_HOT_RAIL_TARGET_DIST))
        while tiles[hot_cell] < target and tiles[hot_cell] < COASTER_MAX_TILE_MULT:
            tiles[hot_cell] = min(tiles[hot_cell] * 2, COASTER_MAX_TILE_MULT)
            pukes.append({'reel': hot_cell[0], 'row': hot_cell[1], 'multiplier': tiles[hot_cell]})
    tile_list = [
        {'reel': reel, 'row': row, 'multiplier': mult}
        for (reel, row), mult in sorted(tiles.items())
    ]
    return pukes, tile_list


def run_coaster_freegame(ctx: RoundCtx, rng: random.Random, trigger_positions: List[dict],
                         pukes: Optional[List[dict]] = None, tiles: Optional[List[dict]] = None,
                         spin_boards: Optional[List[List[List[dict]]]] = None) -> None:
    ctx.emit({'type': 'freeSpinTrigger', 'totalFs': TOTAL_FS, 'positions': [dict(p) for p in trigger_positions], 'bonusType': 'coaster'})
    if pukes is None or tiles is None:
        pukes, tiles = roll_coaster_setup(rng)
    ctx.emit({
        'type': 'coasterSetup',
        'pukes': [dict(p) for p in pukes],
        'tiles': [dict(t) for t in tiles],
    })
    for spin in range(TOTAL_FS):
        ctx.emit({'type': 'updateFreeSpin', 'amount': spin, 'total': TOTAL_FS})
        if spin_boards is not None:
            board = [[dict(cell) for cell in reel] for reel in spin_boards[spin]]
        else:
            board = spin_board(rng, COASTER_STRIPS)
        apply_persistent_tiles(board, tiles)
        emit_reveal(ctx, rng, board, 'freegame')
        awarded = emit_line_wins(ctx, evaluate_board(board), 'free')
        if awarded > 0:
            ctx.emit({'type': 'setTotalWin', 'amount': ctx.total})
        if ctx.capped:
            ctx.emit_wincap_if_needed()
            break
    ctx.emit({'type': 'freeSpinEnd', 'amount': ctx.total, 'winLevel': win_level_from_amount(ctx.total)})


# ---------------------------------------------------------------------------
# Round builders
# ---------------------------------------------------------------------------
def _finalize(ctx: RoundCtx, trigger_mode: str) -> dict:
    ctx.emit_wincap_if_needed()
    if ctx.total > 0:
        ctx.emit({'type': 'setWin', 'amount': ctx.total, 'winLevel': win_level_from_amount(ctx.total)})
    ctx.emit({'type': 'finalWin', 'amount': ctx.total})
    return {
        'events': ctx.events,
        'final_amount': ctx.total,
        'basegame_win': ctx.base_win,
        'freegame_win': ctx.free_win,
        'trigger_mode': trigger_mode,
    }


def _roll_base_feature(rng: random.Random, mode: str) -> Optional[str]:
    settings = MODE_SETTINGS[mode]
    roll = rng.random()
    edge = settings['coaster_rate']
    if roll < edge:
        return 'coaster'
    edge += settings['roller_rate']
    if roll < edge:
        return 'roller'
    edge += settings['duck_rate']
    if roll < edge:
        return 'duck'
    edge += settings['base_rollerwild_rate']
    if roll < edge:
        return 'base_rollerwild'
    edge += settings['duckcollect_rate']
    if roll < edge:
        return 'duckcollect'
    return None


def build_base_round(rng: random.Random, mode: str, forced_feature: Optional[str] = None) -> dict:
    ctx = RoundCtx()
    settings = MODE_SETTINGS.get(mode, MODE_SETTINGS['BASE'])
    feature = forced_feature if forced_feature is not None else _roll_base_feature(rng, mode)

    board = spin_board(rng, BASE_STRIPS)
    scatter_positions: List[dict] = []
    dc_positions: List[dict] = []
    wild_reels: List[dict] = []

    if feature in ('duck', 'roller', 'coaster'):
        count = int(weighted_choice(rng, TRIGGER_SCATTER_COUNT_DIST))
        scatter_positions = place_scatters(rng, board, SCATTER_FOR_FEATURE[feature], count)
    elif feature == 'duckcollect':
        dc_count = int(weighted_choice(rng, BASE_DC_COUNT_DIST))
        dc_positions = place_dc_symbols(rng, board, dc_count)
    elif feature == 'base_rollerwild':
        wild_reels = roll_wild_reels(rng, BASE_ROLLER_COUNT_DIST, ROLLER_SINGLE_MULT_POOL)
    else:
        if rng.random() < settings['teaser_scatter_rate']:
            place_teaser_scatters(rng, board)

    transformed_board = transformed_wild_board(board, wild_reels)
    presentation_board = [[dict(cell) for cell in reel] for reel in board]
    place_wild_reel_triggers(presentation_board, wild_reels)
    emit_reveal(ctx, rng, presentation_board, 'basegame')

    if dc_positions:
        sequence = roll_duck_sequence(rng, len(dc_positions), BASE_DUCK_DIRECT_POOL, BASE_DUCK_MM_POOL)
        run_duck_collect(ctx, dc_positions, sequence)

    if wild_reels:
        ctx.emit({'type': 'rollerWildsApply', 'reels': [dict(e) for e in wild_reels]})

    # Scatter-triggered bonuses have no standalone base-game payout. Their
    # event payout starts inside the feature, keeping natural and bought
    # feature averages directly comparable.
    if feature not in ('duck', 'roller', 'coaster'):
        emit_line_wins(ctx, evaluate_board(transformed_board), 'base')
    ctx.emit({'type': 'setTotalWin', 'amount': ctx.total})
    ctx.emit_wincap_if_needed()

    if not ctx.capped:
        if feature == 'duck':
            pool = roll_duck_sequence(rng, DUCK_POND_SIZE, DUCK_BONUS_DIRECT_POOL, DUCK_BONUS_MM_POOL)
            run_duck_pick_bonus(ctx, pool, scatter_positions)
        elif feature == 'roller':
            run_roller_freegame(ctx, rng, scatter_positions)
        elif feature == 'coaster':
            run_coaster_freegame(ctx, rng, scatter_positions)

    if feature in ('duck', 'roller', 'coaster', 'duckcollect'):
        trigger_mode = feature
    elif ctx.total > 0:
        trigger_mode = 'basegame'
    else:
        trigger_mode = '0'
    return _finalize(ctx, trigger_mode)


def build_fspin1_round(rng: random.Random) -> dict:
    """FSPIN1 (20x): single spin, guaranteed 1+ DC symbols, no scatters or roller wilds."""
    ctx = RoundCtx()
    board = spin_board(rng, BASE_STRIPS)
    dc_count = int(weighted_choice(rng, FSPIN1_DUCK_COUNT_DIST))
    dc_positions = place_dc_symbols(rng, board, dc_count, one_per_reel=False)
    emit_reveal(ctx, rng, board, 'basegame')
    sequence = roll_duck_sequence(rng, dc_count, FSPIN1_DIRECT_POOL, FSPIN1_MM_POOL)
    run_duck_collect(ctx, dc_positions, sequence)
    emit_line_wins(ctx, evaluate_board(board), 'base')
    ctx.emit({'type': 'setTotalWin', 'amount': ctx.total})
    return _finalize(ctx, 'duckcollect')


def build_fspin2_round(rng: random.Random) -> dict:
    """FSPIN2 (60x): single spin, guaranteed 1+ full-wild reels, no scatters, no DC."""
    ctx = RoundCtx()
    board = spin_board(rng, FSPIN2_STRIPS)
    wild_reels = roll_wild_reels(rng, FSPIN2_COUNT_DIST, ROLLER_SINGLE_MULT_POOL)
    presentation_board = [[dict(cell) for cell in reel] for reel in board]
    place_wild_reel_triggers(presentation_board, wild_reels)
    transformed_board = transformed_wild_board(board, wild_reels)
    emit_reveal(ctx, rng, presentation_board, 'basegame')
    ctx.emit({'type': 'rollerWildsApply', 'reels': [dict(e) for e in wild_reels]})
    emit_line_wins(ctx, evaluate_board(transformed_board), 'base')
    ctx.emit({'type': 'setTotalWin', 'amount': ctx.total})
    return _finalize(ctx, 'rollerwild')


def build_buy_round(rng: random.Random, feature: str) -> dict:
    """DUCK / ROLLER / COASTER buys: base reveal with the trigger scatters, then the feature."""
    return build_base_round(rng, 'BASE', forced_feature=feature)


def generate_round_for_mode(mode: str = 'BASE', seed: Optional[int] = None) -> dict:
    normalized_mode = str(mode or 'BASE').upper()
    rng = random.Random((seed if seed is not None else random.randrange(1 << 30)) + 1)
    if normalized_mode in ('BASE', 'ANTE'):
        return build_base_round(rng, normalized_mode)
    if normalized_mode == 'FSPIN1':
        return build_fspin1_round(rng)
    if normalized_mode == 'FSPIN2':
        return build_fspin2_round(rng)
    if normalized_mode == 'DUCK':
        return build_buy_round(rng, 'duck')
    if normalized_mode == 'ROLLER':
        return build_buy_round(rng, 'roller')
    if normalized_mode == 'COASTER':
        return build_buy_round(rng, 'coaster')
    raise ValueError(f'unknown mode: {mode}')


# ---------------------------------------------------------------------------
# Forced coverage rounds (deterministic near-cap / cap entries per mode)
# ---------------------------------------------------------------------------
_FORCED_SEED = 0x7EED_BA5E


def _forced_h1_board() -> List[List[dict]]:
    return uniform_board('H1')


def _forced_scatter_board(rng: random.Random, scatter_symbol: str) -> Tuple[List[List[dict]], List[dict]]:
    board = no_win_board()
    positions = place_scatters(rng, board, scatter_symbol, 3)
    return board, positions


def _forced_duck_collect_round(rng: random.Random, dc_count: int, sequence: List[Tuple[str, int]]) -> dict:
    """FSPIN1-style forced coverage: no-win board + DC symbols with a forced flip sequence."""
    ctx = RoundCtx()
    board = no_win_board()
    positions = []
    for reel in range(dc_count):
        row = 2
        set_visible(board, reel, row, _cell(DC))
        positions.append({'reel': reel, 'row': row})
    emit_reveal(ctx, rng, board, 'basegame')
    run_duck_collect(ctx, positions, sequence)
    emit_line_wins(ctx, evaluate_board(board), 'base')
    ctx.emit({'type': 'setTotalWin', 'amount': ctx.total})
    return _finalize(ctx, 'duckcollect')


def _forced_fspin2_round(rng: random.Random, wild_reels: List[dict]) -> dict:
    ctx = RoundCtx()
    board = _forced_h1_board()
    wild_reels = complete_wild_reel_entries(wild_reels)
    presentation_board = [[dict(cell) for cell in reel] for reel in board]
    place_wild_reel_triggers(presentation_board, wild_reels)
    transformed_board = transformed_wild_board(board, wild_reels)
    emit_reveal(ctx, rng, presentation_board, 'basegame')
    ctx.emit({'type': 'rollerWildsApply', 'reels': [dict(e) for e in wild_reels]})
    emit_line_wins(ctx, evaluate_board(transformed_board), 'base')
    ctx.emit({'type': 'setTotalWin', 'amount': ctx.total})
    return _finalize(ctx, 'rollerwild')


def _forced_duck_bonus_round(rng: random.Random, sequence: List[Tuple[str, int]]) -> dict:
    ctx = RoundCtx()
    board, positions = _forced_scatter_board(rng, S_DUCK)
    emit_reveal(ctx, rng, board, 'basegame')
    emit_line_wins(ctx, evaluate_board(board), 'base')
    ctx.emit({'type': 'setTotalWin', 'amount': ctx.total})
    filler = roll_duck_sequence(
        rng,
        DUCK_POND_SIZE - len(sequence),
        DUCK_BONUS_DIRECT_POOL,
        DUCK_BONUS_MM_POOL,
    )
    run_duck_pick_bonus(ctx, list(sequence) + filler, positions)
    return _finalize(ctx, 'duck')


def _forced_roller_round(rng: random.Random, wild_reels: List[dict]) -> dict:
    """Roller bonus where spin 1 is an all-H1 board with the given wild reels; the rest pay 0."""
    ctx = RoundCtx()
    wild_reels = complete_wild_reel_entries(wild_reels)
    board, positions = _forced_scatter_board(rng, S_ROLLER)
    emit_reveal(ctx, rng, board, 'basegame')
    ctx.emit({'type': 'setTotalWin', 'amount': ctx.total})
    ctx.emit({'type': 'freeSpinTrigger', 'totalFs': TOTAL_FS, 'positions': [dict(p) for p in positions], 'bonusType': 'roller'})
    for spin in range(TOTAL_FS):
        ctx.emit({'type': 'updateFreeSpin', 'amount': spin, 'total': TOTAL_FS})
        if spin == 0:
            spin_board_cells = _forced_h1_board()
            presentation_board = [[dict(cell) for cell in reel] for reel in spin_board_cells]
            place_wild_reel_triggers(presentation_board, wild_reels)
            transformed_board = transformed_wild_board(spin_board_cells, wild_reels)
        else:
            spin_board_cells = no_win_board()
            presentation_board = spin_board_cells
            transformed_board = spin_board_cells
        emit_reveal(ctx, rng, presentation_board, 'freegame')
        if spin == 0 and wild_reels:
            ctx.emit({'type': 'rollerWildsApply', 'reels': [dict(e) for e in wild_reels]})
        awarded = emit_line_wins(ctx, evaluate_board(transformed_board), 'free')
        if awarded > 0:
            ctx.emit({'type': 'setTotalWin', 'amount': ctx.total})
        if ctx.capped:
            ctx.emit_wincap_if_needed()
            break
    ctx.emit({'type': 'freeSpinEnd', 'amount': ctx.total, 'winLevel': win_level_from_amount(ctx.total)})
    return _finalize(ctx, 'roller')


def _pukes_for_tiles(tiles: List[Tuple[int, int, int]]) -> List[dict]:
    """Build a valid puke sequence that produces the given tiles by doubling."""
    pukes = []
    for reel, row, mult in tiles:
        value = 2
        while True:
            pukes.append({'reel': reel, 'row': row, 'multiplier': value})
            if value >= mult:
                break
            value *= 2
    return pukes


def _forced_coaster_round(rng: random.Random, tiles: List[Tuple[int, int, int]], big_spins: int) -> dict:
    """Coaster bonus with fixed persistent tiles; the first `big_spins` spins are all-H1 boards."""
    ctx = RoundCtx()
    board, positions = _forced_scatter_board(rng, S_COASTER)
    emit_reveal(ctx, rng, board, 'basegame')
    ctx.emit({'type': 'setTotalWin', 'amount': ctx.total})
    tile_list = [{'reel': reel, 'row': row, 'multiplier': mult} for reel, row, mult in tiles]
    spin_boards = []
    for spin in range(TOTAL_FS):
        spin_boards.append(_forced_h1_board() if spin < big_spins else no_win_board())
    run_coaster_freegame(ctx, rng, positions, pukes=_pukes_for_tiles(tiles), tiles=tile_list, spin_boards=spin_boards)
    return _finalize(ctx, 'coaster')


# Coaster tile/spin variants. Tiles are on reels >= 2 so no-win filler boards stay
# win-free. Big-spin value with a single tile at (2,2) mult M: 3 lines cross the tile
# (lines 3/6/7) -> 2000*(3M+12) cents per big spin.
#   (32, 7)  -> 15,120x   (32, 8)  -> 17,280x   (32, 9)  -> 19,440x   (32, 10) -> 21,600x
#   (64, 4)  -> 16,320x   (64, 5)  -> 20,400x   (64, 6)  -> 24,480x   (1024,1) -> capped 25,000x
_FORCED_COASTER_VARIANTS: List[Tuple[List[Tuple[int, int, int]], int]] = [
    ([(2, 2, 32)], 7),
    ([(2, 2, 64)], 4),
    ([(2, 2, 32)], 8),
    ([(2, 2, 32)], 9),
    ([(2, 2, 64)], 5),
    ([(2, 2, 32)], 10),
    ([(2, 2, 64)], 6),
    ([(2, 2, 1024)], 1),
]

# BASE-only band fill for 10,000x-15,000x (distribution verification found BASE had
# zero books in that band). Two-tile variant: line 3 crosses both tiles (mult 32+4=36),
# lines 6/7 cross (2,2) (32), lines 8/9/14/15 cross (3,2) (4), 8 plain lines
# -> 2000*(36 + 2*32 + 4*4 + 8) = 248,000 cents = 2,480x per big spin.
#   ([32@(2,2)], 5) -> 10,800x   ([32@(2,2)], 6) -> 12,960x   ([32@(2,2), 4@(3,2)], 6) -> 14,880x
_FORCED_COASTER_BAND_FILL_VARIANTS: List[Tuple[List[Tuple[int, int, int]], int]] = [
    ([(2, 2, 32)], 5),
    ([(2, 2, 32)], 6),
    ([(2, 2, 32), (3, 2, 4)], 6),
]

# Wild-reel variants (all-H1 board): total = 15 lines * 20x * S = 300*S x bet,
# where S = sum of the wild-reel multipliers (every line crosses every reel).
#   S=50 -> 15,000x  S=55 -> 16,500x  S=60 -> 18,000x  S=70 -> 21,000x
#   S=75 -> 22,500x  S=80 -> 24,000x  S=100 -> capped 25,000x
_FORCED_WILD_REEL_VARIANTS: List[List[Tuple[int, int]]] = [
    [(0, 50)],
    [(0, 50), (4, 5)],
    [(0, 50), (4, 10)],
    [(0, 50), (2, 10), (4, 10)],
    [(0, 50), (2, 25)],
    [(0, 50), (2, 25), (4, 5)],
    [(0, 100)],
]

# FSPIN1 forced coverage uses valid two-duck outcomes from the 1-25 contract.
_FORCED_FSPIN1_VARIANTS: List[List[Tuple[str, int]]] = [
    [('mult', 500), ('multmult', 25)],
    [('mult', 500), ('multmult', 50)],
    [('mult', 250), ('multmult', 100)],
    [('mult', 500), ('multmult', 100)],
]

# No additional band-fill variants are required.
_FORCED_FSPIN1_BAND_FILL_VARIANTS: List[List[Tuple[str, int]]] = []

# DUCK forced 10-pick sequences (first pick always 'mult'). Cap-crossing picks end
# the sequence early (contract: skip remaining picks).
#   A=15,021  B=16,500  C=18,764  D=20,018  E=22,250  F=23,000  G=25,000 exact  H=capped
_FORCED_DUCK_VARIANTS: List[List[Tuple[str, int]]] = [
    [('mult', 500), ('mult', 100), ('multmult', 25)] + [('mult', 3)] * 7,
    [('mult', 500), ('multmult', 25)] + [('mult', 500)] * 8,
    [('mult', 500), ('mult', 250), ('multmult', 25)] + [('mult', 2)] * 7,
    [('mult', 500), ('mult', 500), ('multmult', 10), ('multmult', 2)] + [('mult', 3)] * 6,
    [('mult', 500), ('mult', 250), ('multmult', 25)] + [('mult', 500)] * 7,
    [('mult', 500), ('mult', 500), ('multmult', 2), ('multmult', 10)] + [('mult', 500)] * 6,
    [('mult', 500), ('mult', 250), ('mult', 250), ('multmult', 25)] + [('mult', 2)] * 6,
    [('mult', 500), ('mult', 500), ('multmult', 100)] + [('mult', 2)] * 7,
]


def generate_forced_coverage_rounds(mode: str) -> List[dict]:
    """Deterministic near-cap/cap rounds for `mode`, spanning ~15,000x .. 25,000x with
    at least one entry paying exactly MAX_WIN_AMOUNT. Output dicts match
    generate_round_for_mode."""
    normalized_mode = str(mode or 'BASE').upper()
    results: List[dict] = []

    if normalized_mode in ('BASE', 'ANTE', 'COASTER'):
        variants = list(_FORCED_COASTER_VARIANTS)
        if normalized_mode == 'BASE':
            variants += _FORCED_COASTER_BAND_FILL_VARIANTS
        for variant_idx, (tiles, big_spins) in enumerate(variants):
            rng = random.Random(_FORCED_SEED + variant_idx)
            results.append(_forced_coaster_round(rng, tiles, big_spins))

    elif normalized_mode == 'FSPIN1':
        variants = _FORCED_FSPIN1_VARIANTS + _FORCED_FSPIN1_BAND_FILL_VARIANTS
        for variant_idx, sequence in enumerate(variants):
            rng = random.Random(_FORCED_SEED + 1000 + variant_idx)
            results.append(_forced_duck_collect_round(rng, len(sequence), sequence))

    elif normalized_mode == 'FSPIN2':
        for variant_idx, reels in enumerate(_FORCED_WILD_REEL_VARIANTS):
            rng = random.Random(_FORCED_SEED + 2000 + variant_idx)
            wild_reels = [{'reel': reel, 'multiplier': mult} for reel, mult in reels]
            results.append(_forced_fspin2_round(rng, wild_reels))

    elif normalized_mode == 'DUCK':
        for variant_idx, sequence in enumerate(_FORCED_DUCK_VARIANTS):
            rng = random.Random(_FORCED_SEED + 3000 + variant_idx)
            results.append(_forced_duck_bonus_round(rng, sequence))

    elif normalized_mode == 'ROLLER':
        for variant_idx, reels in enumerate(_FORCED_WILD_REEL_VARIANTS):
            rng = random.Random(_FORCED_SEED + 4000 + variant_idx)
            wild_reels = [{'reel': reel, 'multiplier': mult} for reel, mult in reels]
            results.append(_forced_roller_round(rng, wild_reels))

    return results
