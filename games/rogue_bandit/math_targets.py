"""Locked Rogue Bandit product targets and proposal controls.

Book/event money uses integer hundredths: 100 == 1.00x base bet.
Candidate quotas are stratification only. Published probabilities live in LUTs.
"""

from fractions import Fraction

GAME_ID = "rogue_bandit"
MODEL_VERSION = "rogue-bandit-v2-unified-96-rtp"
BOOK_SCALE = 100
COLS = 6
ROWS = 8
ROW_OFFSET = 1
MIN_CLUSTER = 5
MAX_WIN_X = 10_000
MAX_WIN_AMOUNT = MAX_WIN_X * BOOK_SCALE
MAX_CASCADES = 256
MAX_FREE_SPINS = 100

SYMBOLS = ("H1", "H2", "H3", "L1", "L2", "L3", "L4", "L5")
SCATTER = "S"
ALL_SYMBOLS = SYMBOLS + (SCATTER,)
HEAT = (1, 2, 3, 5, 10, 25, 50, 100)
PAYOUT_BANDS = ((5, 5), (6, 6), (7, 7), (8, 8), (9, 10), (11, 12), (13, 15), (16, 48))
PAYTABLE_X = {
    "H1": (1.0, 1.5, 2.5, 4.0, 7.5, 15.0, 35.0, 100.0),
    "H2": (0.8, 1.0, 1.5, 2.5, 5.0, 10.0, 25.0, 75.0),
    "H3": (0.5, 0.8, 1.0, 2.0, 4.0, 7.5, 15.0, 50.0),
    "L1": (0.4, 0.5, 0.8, 1.0, 2.0, 4.0, 10.0, 25.0),
    "L2": (0.3, 0.4, 0.6, 0.8, 1.5, 3.0, 7.5, 20.0),
    "L3": (0.2, 0.3, 0.5, 0.6, 1.2, 2.5, 6.0, 15.0),
    "L4": (0.2, 0.3, 0.4, 0.5, 1.0, 2.0, 5.0, 12.5),
    "L5": (0.1, 0.2, 0.3, 0.4, 0.8, 1.5, 4.0, 10.0),
}
PAYTABLE = {symbol: tuple(round(value * BOOK_SCALE) for value in values)
            for symbol, values in PAYTABLE_X.items()}

SYMBOL_WEIGHTS = {"L1": 17, "L2": 17, "L3": 16, "L4": 16, "L5": 15,
                  "H1": 7, "H2": 9, "H3": 11, SCATTER: 1.4}

MODE_COSTS = {"base": Fraction(1), "ante": Fraction(3, 2), "superspin": Fraction(25),
              "bonus": Fraction(100), "superbonus": Fraction(500)}
TARGET_RTP = Fraction(24, 25)
MODE_RTPS = {mode: TARGET_RTP for mode in MODE_COSTS}
MODE_TARGET_MEANS = {mode: MODE_COSTS[mode] * MODE_RTPS[mode] for mode in MODE_COSTS}

MODE_RULES = {
    "base": {"steal_prob": .40, "max_steals": 1, "heat_start": 0, "scatter_factor": 1.0},
    "ante": {"steal_prob": .40, "max_steals": 1, "heat_start": 0, "scatter_factor": 1.3},
    "superspin": {"steal_prob": 1.0, "max_steals": 3, "heat_start": 2, "scatter_factor": .35},
    "freegame": {"steal_prob": .30, "max_steals": 2, "heat_start": None, "scatter_factor": .65},
    "superfreegame": {"steal_prob": 1.0, "max_steals": 1, "heat_start": None, "scatter_factor": .65},
}
FREE_SPINS = 10
RETRIGGER_SPINS = 5
BASE_TRIGGER_SCATTERS = 4
SUPER_BUY_SCATTERS = 5

# Published behavioral constraints.
BASE_HIT_RATES = {"base": Fraction(325, 1000), "ante": Fraction(335, 1000)}
BASE_STEAL_VISIBLE_RATE = Fraction(1, 4)
NATURAL_TRIGGER_RATES = {"base": Fraction(1, 225), "ante": Fraction(1, 100)}
MAX_WIN_RATE = Fraction(1, 10_000_000)
SUPERSPIN_BANDS = {"under10": Fraction(575, 1000), "10to100": Fraction(375, 1000),
                   "100plus": Fraction(50, 1000)}
LOOKUP_SCALE = 10**12

# Candidate coverage only; never interpreted as live probability.
GENERATION_QUOTAS = {
    "base": {"0": .30, "basegame": .46, "freegame": .22, "wincap": .02},
    "ante": {"0": .28, "basegame": .43, "freegame": .27, "wincap": .02},
    "superspin": {"under10": .28, "10to100": .34, "100plus": .36, "wincap": .02},
    "bonus": {"ordinary": .65, "hot": .33, "wincap": .02},
    "superbonus": {"ordinary": .55, "hot": .43, "wincap": .02},
}


def check_targets() -> None:
    assert len(SYMBOLS) == 8 and len(PAYTABLE) == 8
    assert PAYOUT_BANDS[0][0] == MIN_CLUSTER and PAYOUT_BANDS[-1][1] == COLS * ROWS
    assert all(len(values) == len(PAYOUT_BANDS) for values in PAYTABLE.values())
    assert all(sum(quotas.values()) == 1 for quotas in GENERATION_QUOTAS.values())
    assert sum(SUPERSPIN_BANDS.values()) == 1
    assert all(0 < rtp < 1 for rtp in MODE_RTPS.values())
    assert set(MODE_RTPS.values()) == {TARGET_RTP}
