"""McSchmutzo weighting targets.

Why this file exists
--------------------
McSchmutzo's lookup tables come from the Rust optimizer, which solves one weighting per mode
against that mode's RTP. Nothing in that process targets the *shape* of a mode, and the audit of
the shipped tables showed what that costs:

  base        99% of non-bonus spins pay 0.40x or less (p90 = p99 = 0.40x); the natural bonus
              holds 71% of the mode's RTP and pays 196.23x at 1 in 286
  enhancer1   natural bonus mean 117.70x but MEDIAN 0.80x — half of them pay nothing worth seeing
  bonus1      a 100x purchase has a median of 31.70x and p90 of 47.90x, so ~90% of buys return
              under half their cost while the mean is carried by a thin tail. Buying is strictly
              worse than waiting for a natural trigger.

None of that is a content problem. The book pools are rich — base averages 910x raw, bonus1
averages 3,035x with 35.7% of its books between 200x and 1000x. The material to build a good
distribution is already there; only the selection weights need to change, which is why this is a
re-weight and not a re-simulation.

Everything below is a knob. Change a number, run reweight_only.py, no new books.
"""

from __future__ import annotations

TARGET_RTP = 0.9651
MAX_WIN_X = 25_000

# math_spec.md: "Each mode contains an exact 25,000x optimization fence targeted at 1 in 5,000,000
# rounds." The optimizer honours it — the two modes never reweighted measure 1 in 5,000,020
# (bonus2) and 1 in 5,000,055 (featureSpin). It has to be an explicit target here too: an
# exponential tilt gives a 25,000x book effectively no weight, and merely forcing weight >= 1
# lands at ~1 in 10^15 against LOOKUP_SCALE, which is what the first version of this file did.
MAX_WIN_HIT_RATE = 5_000_000

# Total weight per lookup table. The optimizer's tables sit just under 2^50; matching that keeps
# the resolution (100k books, ~11 billion units each) so the tilt is never limited by rounding.
LOOKUP_SCALE = 1_125_899_906_842_624

MODE_COSTS = {
    'base': 1.0,
    'enhancer1': 2.0,
    'featureSpin': 20.0,
    'bonus1': 100.0,
    'bonus2': 500.0,
}

MODE_TARGET_MEANS = {mode: TARGET_RTP * cost for mode, cost in MODE_COSTS.items()}

# Tilt width per mode. Larger = flatter selection = higher median for the same mean. Use
# preview_weighting.py to see the effect before writing tables.
TARGET_SCALES = {
    'base': 40.0,
    'enhancer1': 55.0,
    'featureSpin': 30.0,
    'bonus1': 120.0,
    'bonus2': 300.0,
}

# ── natural feature design ───────────────────────────────────────────────────
# A wheel round can be entered two ways, and each one has a matching purchase:
#
#   3 scatters -> the same feature bonus1 sells for 100x  (returns 96.51x)
#   4 scatters -> the same feature bonus2 sells for 500x  (returns 482.54x)
#
# The shipped tables got both wrong, in opposite directions: a natural 3-scatter bonus paid
# 172.62x (179% of what its buy returns) while a natural 4-scatter bonus paid 254.93x (53% of
# its buy). In enhancer1 the 4-scatter bonus paid 132.39x against a 482.54x buy — 27%.
#
# These entries put the two on parity with their buys: triggering is worth exactly what buying
# the same thing returns. The price of parity is rarity. A 482.54x event cannot be handed out
# every 103 spins the way enhancer1 does today — at its true value that alone would cost 256% of
# the mode's entire RTP, which is only possible because natural supers are currently underpaid.
# So supers get materially rarer, and the RTP that frees up goes back into base-game pays, which
# roughly double.
#
# frequency = one in this many spins. mean = what it pays on average when it lands.
NATURAL_FEATURE_DESIGN = {
    'base': {
        # Share of spins that pay something at all (today ~72%).
        'paying_share': 0.7202,
        'features': {
            'feature3': {'frequency': 400, 'mean': 96.51},
            'feature4': {'frequency': 3000, 'mean': 482.54},
        },
    },
    'enhancer1': {
        'paying_share': 0.8524,
        # enhancer1 costs 2x and still earns it: 2.7x the normal-bonus rate of base and 3x the
        # super rate.
        'features': {
            'feature3': {'frequency': 150, 'mean': 96.51},
            'feature4': {'frequency': 1000, 'mean': 482.54},
        },
    },
}

# A 0x outcome stays possible, but rare. Keyed by group name ('feature', 'basegame') for natural
# modes and by mode name for the bought ones.
ZERO_WEIGHT_CAP = {
    'feature3': 0.02,
    'feature4': 0.02,
    'bonus1': 0.02,
    'bonus2': 0.02,
    'featureSpin': 0.02,
}
