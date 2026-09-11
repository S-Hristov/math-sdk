"""Magnetic 2 Mothership provisional math targets.

The sequel inherits Magnetic 1's 96.10% target until its PAR sheet is approved.
Feature frequencies and values below are tuning inputs, not final sign-off data.
"""

from __future__ import annotations

TARGET_RTP = 0.961
TARGET_BASE_HIT_RATE = 0.30
# Higher resolution gives low-frequency natural tiers enough integer weight
# granularity to hit exact target means while retaining a positive max-win row.
LOOKUP_SCALE = 1_000_000_000

MODE_COSTS = {
    'BASE': 1.0,
    'CHANCE': 2.0,
    'FEATURE': 50.0,
    'BONUS': 100.0,
    'MYSTERY': 300.0,
    'SUPER': 500.0,
}

MODE_TARGET_MEANS = {
    mode: TARGET_RTP * cost
    for mode, cost in MODE_COSTS.items()
}

# Book-pool quotas, not production odds - the lookup weights define those. The
# hidden quotas are deliberately far above the natural trigger rate: that group
# has to average HIDDEN_TARGET_MEAN on a very small slice of lookup weight, and
# with only ~500 books the integer weights are too coarse to land it.
BASE_RATES = {
    '0': 0.5536,
    'basegame': 0.407,
    'bonus': 0.0254,
    'super': 0.008,
    'hidden': 0.006,
}

CHANCE_RATES = {
    '0': 0.497,
    'basegame': 0.39,
    'bonus': 0.078,
    'super': 0.027,
    'hidden': 0.008,
}

for _label, _rates in (('BASE', BASE_RATES), ('CHANCE', CHANCE_RATES)):
    if abs(sum(_rates.values()) - 1.0) > 1e-9:
        raise ValueError(f'{_label} book quotas must sum to 1, got {sum(_rates.values())}')

# A criteria/tier group that misses its own target mean by more than this has its
# residual silently absorbed by the mode-level RTP correction, which lands as a
# skew in some other group. Fail loudly instead.
GROUP_MEAN_TOLERANCE = 0.01

# ── Mystery Bonus Buy ────────────────────────────────────────────────────────
# The buy hands the player one of the three real bonuses, so its price is the
# weighted price of those three and the advertised odds are a contract. The
# lookup weighting holds these shares and these per-tier means exactly; left to
# a single mode-wide RTP tilt the pool drifted to 66/29/5 with Mystery's Normal
# Bonus paying 264x against a bought Normal Bonus's 96x.
MYSTERY_MIX = {'BONUS': 0.70, 'SUPER': 0.25, 'HIDDEN': 0.05}

# Hidden is the rarest tier (5 scatters) so it has to pay the most. The figure is
# not a free choice: it is whatever makes the advertised 300x Mystery price
# honest once BONUS and SUPER are pinned to their own bought-mode means.
HIDDEN_TARGET_MEAN = (
    MODE_TARGET_MEANS['MYSTERY']
    - MYSTERY_MIX['BONUS'] * MODE_TARGET_MEANS['BONUS']
    - MYSTERY_MIX['SUPER'] * MODE_TARGET_MEANS['SUPER']
) / MYSTERY_MIX['HIDDEN']

if HIDDEN_TARGET_MEAN <= MODE_TARGET_MEANS['SUPER']:
    raise ValueError(
        'Hidden Bonus is rarer than Super Bonus but would pay less '
        f'({HIDDEN_TARGET_MEAN:.1f}x vs {MODE_TARGET_MEANS["SUPER"]:.1f}x); '
        'raise the Mystery price or reweight MYSTERY_MIX'
    )

# One source of truth for what each bonus is worth, however the player reached
# it. A natural 3-scatter Gravity Breach, a bought one and a Mothership Protocol
# roll into one must all average the same, or the buy prices lie and hunting the
# feature naturally becomes the wrong or the right play by accident.
BONUS_TIER_MEANS = {
    'bonus': MODE_TARGET_MEANS['BONUS'],
    'super': MODE_TARGET_MEANS['SUPER'],
    'hidden': HIDDEN_TARGET_MEAN,
}

MYSTERY_TIER_MEANS = {
    'BONUS': BONUS_TIER_MEANS['bonus'],
    'SUPER': BONUS_TIER_MEANS['super'],
    'HIDDEN': BONUS_TIER_MEANS['hidden'],
}

# Which bet mode sells each tier outright, for the natural/bought parity check.
BOUGHT_MODE_FOR_TIER = {'bonus': 'BONUS', 'super': 'SUPER'}

# ── natural (non-bought) feature design ──────────────────────────────────────
# Natural feature tiers now use the same mean payout as their purchased counterpart, like Veggie
# Salad. Frequencies use an approximately 1/300 BASE trigger rate and 3x CHANCE trigger rate;
# the base-game group absorbs the remaining RTP.
NATURAL_FEATURE_DESIGN = {
    'BASE': {
        'basegame_share': 0.331491,
        'bonus': {'frequency': 353, 'mean': BONUS_TIER_MEANS['bonus']},
        'super': {'frequency': 2143, 'mean': BONUS_TIER_MEANS['super']},
        'hidden': {'frequency': 30000, 'mean': BONUS_TIER_MEANS['hidden']},
    },
    'CHANCE': {
        'basegame_share': 0.357143,
        'bonus': {'frequency': 118, 'mean': BONUS_TIER_MEANS['bonus']},
        'super': {'frequency': 714, 'mean': BONUS_TIER_MEANS['super']},
        'hidden': {'frequency': 10000, 'mean': BONUS_TIER_MEANS['hidden']},
    },
}

# A 0x feature stays possible, but rare: at most this share of a group's weight may sit on
# zero-payout books. The pools only contain 1.5-3% zero books, so the old 9% / 36% zero rates were
# manufactured by the weighting piling weight onto them. Four 0x features in a row is what makes
# players quit, and this is the knob that controls it.
ZERO_WEIGHT_CAP = {'bonus': 0.02, 'super': 0.02, 'hidden': 0.01}
