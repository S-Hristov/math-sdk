from game_config import GameConfig
from game_optimization import OptimizationSetup
from math_data import ENTRY_MAX_STEPS, MULTIPLIER_LADDER, PAYLINES, PAYTABLE, WHEEL_OUTCOMES


def test_paytable_is_exact_and_unscaled():
    config = GameConfig()
    assert config.paytable is PAYTABLE
    assert len(config.paytable) == 30
    assert config.paytable[(3, "H1")] == 0.5
    assert config.paytable[(5, "H1")] == 5.0
    assert config.paytable[(3, "L5")] == 0.1
    assert config.paytable[(5, "L5")] == 1.0
    assert 0.7 not in config.paytable.values()


def test_fifty_unique_valid_paylines():
    assert len(PAYLINES) == 50
    assert len(set(PAYLINES.values())) == 50
    assert set(PAYLINES) == set(range(1, 51))
    assert all(len(line) == 5 for line in PAYLINES.values())
    assert all(0 <= row < 5 for line in PAYLINES.values() for row in line)


def test_multiplier_and_wheel_contract():
    assert MULTIPLIER_LADDER[0] == 1
    assert MULTIPLIER_LADDER[-1] == 1000
    assert len(MULTIPLIER_LADDER) == 31
    assert WHEEL_OUTCOMES == ((6, 3), (8, 4), (10, 5), (12, 6), (15, 8), (20, 10), (30, 15))
    assert ENTRY_MAX_STEPS == {3: 15, 4: 30}


def test_mode_targets():
    config = GameConfig()
    targets = {mode.get_name(): mode for mode in config.bet_modes}
    assert {name: mode.get_cost() for name, mode in targets.items()} == {
        "base": 1.0,
        "enhancer1": 2.0,
        "featureSpin": 20.0,
        "bonus1": 100.0,
        "bonus2": 500.0,
    }
    assert all(mode.get_wincap() == 25000.0 for mode in targets.values())
    assert all(mode.get_rtp() == 0.9651 for mode in targets.values())


def test_bonus_entry_contract():
    config = GameConfig()
    modes = {mode.get_name(): mode for mode in config.bet_modes}
    bonus1 = {item.get_criteria(): item for item in modes["bonus1"].get_distributions()}["main"]._conditions
    bonus2 = {item.get_criteria(): item for item in modes["bonus2"].get_distributions()}["main"]._conditions
    feature_spin = {
        item.get_criteria(): item for item in modes["featureSpin"].get_distributions()
    }["main"]._conditions
    assert bonus1["bonus_entry_weights"] == {3: 1}
    assert bonus2["bonus_entry_weights"] == {4: 1}
    assert feature_spin["force_lock_feature"] is True


def test_every_mode_has_reachable_wincap_fence():
    config = GameConfig()
    OptimizationSetup(config)
    for mode in config.bet_modes:
        distributions = {item.get_criteria(): item for item in mode.get_distributions()}
        assert set(distributions) == {"main", "wincap"}
        assert distributions["wincap"].get_win_criteria() == 25000.0
        conditions = distributions["wincap"]._conditions
        assert conditions["force_wincap"] is True
        assert conditions["direct_bonus"] is True
        assert conditions["bonus_entry_weights"] == {4: 1}
        assert conditions["wheel_weights"] == {WHEEL_OUTCOMES[-1]: 1}
        wincap_rtp = config.opt_params[mode.get_name()]["conditions"]["wincap"]["rtp"]
        hit_rate = mode.get_wincap() / wincap_rtp / mode.get_cost()
        assert hit_rate == 5_000_000


def test_super_bonus_tail_controls():
    config = GameConfig()
    mode = {item.get_name(): item for item in config.bet_modes}["bonus2"]
    bonus2 = {item.get_criteria(): item for item in mode.get_distributions()}["main"]._conditions
    assert bonus2["multiplier_step_weights"] == {1: 90, 2: 8, 3: 2}
    assert bonus2["main_win_ceiling"] == 9999.99
    weights = bonus2["wheel_weights"]
    assert weights[WHEEL_OUTCOMES[0]] > weights[WHEEL_OUTCOMES[1]]
    assert weights[WHEEL_OUTCOMES[1]] > weights[WHEEL_OUTCOMES[2]]
    assert weights[WHEEL_OUTCOMES[-1]] == 1
