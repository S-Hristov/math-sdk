"""Shared Magnetic proto math targets."""

from __future__ import annotations

TARGET_RTP = 0.961
TARGET_BASE_HIT_RATE = 0.30
LOOKUP_SCALE = 10_000_000

MODE_COSTS = {
    'BASE': 1.0,
    'CHANCE': 2.0,
    'FEATURE': 50.0,
    'BONUS': 100.0,
    'SUPER': 500.0,
}

MODE_TARGET_MEANS = {
    mode: TARGET_RTP * cost
    for mode, cost in MODE_COSTS.items()
}

BASE_RATES = {
    '0': 0.5596,
    'basegame': 0.407,
    'bonus': 0.0254,
    'super': 0.008,
}

CHANCE_RATES = {
    '0': 0.505,
    'basegame': 0.39,
    'bonus': 0.078,
    'super': 0.027,
}

# ── natural (non-bought) feature design ──────────────────────────────────────
# Nothing used to pin the value of a NATURALLY triggered bonus. The weighting solved a single
# tilt for the whole mode against MODE_TARGET_MEANS, which crushed the bonus books (they average
# ~450x raw) down to almost no weight and piled what was left on the weakest ones. Result: a
# natural bonus paid 7.2x on average against 96.1x for the bought one, and a natural SUPER paid
# nothing 36% of the time. These entries make the natural feature an explicit design target:
# how often it triggers, and what it is worth when it does. The base game absorbs the remainder
# of the mode's RTP.
NATURAL_FEATURE_DESIGN = {
    'BASE': {
        # Share of spins that land a paying base-game board (unchanged from the shipped table).
        'basegame_share': 0.331491,
        'bonus': {'frequency': 400, 'mean': 49.3},
        'super': {'frequency': 900, 'mean': 68.0},
    },
    'CHANCE': {
        'basegame_share': 0.357143,
        # CHANCE keeps its ~3.3x trigger advantage over BASE at the same value per feature.
        'bonus': {'frequency': 121, 'mean': 49.3},
        'super': {'frequency': 273, 'mean': 68.0},
    },
}

# A 0x feature stays possible, but rare: at most this share of a group's weight may sit on
# zero-payout books. The pools only contain 1.5-3% zero books, so the old 9% / 36% zero rates were
# manufactured by the weighting piling weight onto them. Four 0x features in a row is what makes
# players quit, and this is the knob that controls it.
ZERO_WEIGHT_CAP = {'bonus': 0.02, 'super': 0.02}
