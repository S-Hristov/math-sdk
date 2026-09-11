"""Locked product values and prototype tuning targets for Veggie Salad."""

from __future__ import annotations

TARGET_RTP = 0.961
MAX_WIN_X = 25_000
MAX_WIN_AMOUNT = MAX_WIN_X * 100
LOOKUP_SCALE = 300_000_000

MODE_COSTS = {
    "BASE": 1.0,
    "CHANCE": 2.0,
    "FEATURE": 20.0,
    "BONUS": 100.0,
    "MYSTERY": 300.0,
    "SUPER": 400.0,
}

MODE_TARGET_MEANS = {mode: TARGET_RTP * cost for mode, cost in MODE_COSTS.items()}

# Tunable prototype assumption: one natural feature per 300 Standard spins.
# Extra Chance is locked to exactly 3x that probability.
BASE_TRIGGER_RATE = 1 / 300
CHANCE_TRIGGER_RATE = 3 * BASE_TRIGGER_RATE
NATURAL_TIER_MIX = {"normal": 0.85, "super": 0.14, "hidden": 0.01}
TARGET_BASEGAME_WIN_RATE = 0.30

# Direct-buy EVs and the Hidden EV implied by the locked 300x 60/30/10 Mystery mix.
TIER_TARGET_MEANS = {
    "normal": MODE_TARGET_MEANS["BONUS"],
    "super": MODE_TARGET_MEANS["SUPER"],
    "hidden": 1_153.20,
}


def _natural_group_weights(trigger_rate: float) -> dict[str, int]:
    trigger_total = round(LOOKUP_SCALE * trigger_rate)
    normal = round(trigger_total * NATURAL_TIER_MIX["normal"])
    super_ = round(trigger_total * NATURAL_TIER_MIX["super"])
    hidden = trigger_total - normal - super_
    basegame = round(LOOKUP_SCALE * TARGET_BASEGAME_WIN_RATE)
    zero = LOOKUP_SCALE - trigger_total - basegame
    return {
        "0": zero,
        "basegame": basegame,
        "normal": normal,
        "super": super_,
        "hidden": hidden,
    }


MODE_GROUP_WEIGHTS = {
    "BASE": _natural_group_weights(BASE_TRIGGER_RATE),
    "CHANCE": _natural_group_weights(CHANCE_TRIGGER_RATE),
    "FEATURE": {"feature": LOOKUP_SCALE},
    "BONUS": {"normal": LOOKUP_SCALE},
    "MYSTERY": {
        "normal": round(LOOKUP_SCALE * 0.60),
        "super": round(LOOKUP_SCALE * 0.30),
        "hidden": round(LOOKUP_SCALE * 0.10),
    },
    "SUPER": {"super": LOOKUP_SCALE},
}


def _natural_group_targets(mode: str) -> dict[str, float]:
    weights = MODE_GROUP_WEIGHTS[mode]
    target_sum_x = MODE_TARGET_MEANS[mode] * LOOKUP_SCALE
    feature_sum_x = sum(weights[tier] * TIER_TARGET_MEANS[tier] for tier in TIER_TARGET_MEANS)
    basegame_mean = (target_sum_x - feature_sum_x) / weights["basegame"]
    return {
        "0": 0.0,
        "basegame": basegame_mean,
        **TIER_TARGET_MEANS,
    }


MODE_GROUP_TARGET_MEANS = {
    "BASE": _natural_group_targets("BASE"),
    "CHANCE": _natural_group_targets("CHANCE"),
    "FEATURE": {"feature": MODE_TARGET_MEANS["FEATURE"]},
    "BONUS": {"normal": TIER_TARGET_MEANS["normal"]},
    "MYSTERY": dict(TIER_TARGET_MEANS),
    "SUPER": {"super": TIER_TARGET_MEANS["super"]},
}


def validate_targets() -> None:
    assert abs(CHANCE_TRIGGER_RATE / BASE_TRIGGER_RATE - 3.0) < 1e-12
    assert sum(MODE_GROUP_WEIGHTS["MYSTERY"].values()) == LOOKUP_SCALE
    mystery_mean = sum(
        MODE_GROUP_WEIGHTS["MYSTERY"][tier] * TIER_TARGET_MEANS[tier]
        for tier in ("normal", "super", "hidden")
    ) / LOOKUP_SCALE
    assert abs(mystery_mean - MODE_TARGET_MEANS["MYSTERY"]) < 1e-9
    for mode, weights in MODE_GROUP_WEIGHTS.items():
        assert sum(weights.values()) == LOOKUP_SCALE, mode


validate_targets()
