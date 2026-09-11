"""Shared Theme Park math targets."""

from __future__ import annotations

TARGET_RTP = 0.961
TARGET_BASE_HIT_RATE = 0.28
LOOKUP_SCALE = 10_000_000

# PRD RTP contribution shares. These are shares of the 96.10% total RTP,
# not standalone RTP values: 49.972% + 38.440% + 7.688% = 96.10%.
TARGET_BASE_RTP_SHARE = 0.52
TARGET_FREESPIN_RTP_SHARE = 0.40
TARGET_BONUS_RTP_SHARE = 0.08
TARGET_RTP_SHARES = {
    'base': TARGET_BASE_RTP_SHARE,
    'freespin': TARGET_FREESPIN_RTP_SHARE,
    'bonus': TARGET_BONUS_RTP_SHARE,
}

MODE_COSTS = {
    'BASE': 1.0,
    'ANTE': 3.0,
    'FSPIN1': 20.0,
    'FSPIN2': 60.0,
    'DUCK': 100.0,
    'ROLLER': 200.0,
    'COASTER': 500.0,
}

MODE_TARGET_MEANS = {
    mode: TARGET_RTP * cost
    for mode, cost in MODE_COSTS.items()
}

# Natural feature rates derive from bought-feature means while preserving the 52/40/8 RTP split.
# This lets natural Duck/Roller/Coaster conditional averages match bought modes without exceeding
# the 96.1% total RTP target.
_DUCK_RATE = TARGET_RTP * TARGET_BONUS_RTP_SHARE / MODE_TARGET_MEANS['DUCK']
# Lookup weights are integer units at 1e-7 resolution. Choose the nearest
# integer quotas whose 192.2x / 480.5x feature means produce the 40% split
# exactly: 6,745 roller + 5,302 coaster units.
_ROLLER_RATE = 6_745 / LOOKUP_SCALE
_COASTER_RATE = 5_302 / LOOKUP_SCALE
_DUCKCOLLECT_RATE = 1 / 40
# All feature criteria are positive outcomes. Keep natural BASE hit rate at 28%.
_BASE_HIT_QUOTA = TARGET_BASE_HIT_RATE - _DUCKCOLLECT_RATE - _DUCK_RATE - _ROLLER_RATE - _COASTER_RATE

BASE_RATES = {
    'basegame': _BASE_HIT_QUOTA,
    'duckcollect': _DUCKCOLLECT_RATE,
    'duck': _DUCK_RATE,
    'roller': _ROLLER_RATE,
    'coaster': _COASTER_RATE,
}
BASE_RATES['0'] = 1.0 - sum(BASE_RATES.values())

# ANTE cost is 3x BASE; use 3x natural feature rates to preserve the same RTP split.
ANTE_RATES = {
    'basegame': _BASE_HIT_QUOTA,
    'duckcollect': _DUCKCOLLECT_RATE,
	'duck': 3 * _DUCK_RATE,
	'roller': 3 * _ROLLER_RATE,
	'coaster': 3 * _COASTER_RATE,
}
ANTE_RATES['0'] = 1.0 - sum(ANTE_RATES.values())
