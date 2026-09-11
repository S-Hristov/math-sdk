"""McSchmutzo game configuration."""

import os

from math_data import ENTRY_MAX_STEPS, MULTIPLIER_LADDER, PAYLINES, PAYTABLE, PAY_RANK, WHEEL_OUTCOMES
from src.config.betmode import BetMode
from src.config.config import Config
from src.config.distributions import Distribution


class GameConfig(Config):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "0_0_mcschmutzo"
        self.game_name = "mcschmutzo"
        self.working_name = "McSchmutzo"
        self.provider_number = 0
        self.win_type = "lines"
        self.rtp = 0.9651
        self.wincap = 25000.0
        self.construct_paths()

        self.num_reels = 5
        self.num_rows = [5] * self.num_reels
        self.include_padding = True

        # One unscaled paytable is used by every bet mode.
        self.paytable = PAYTABLE
        self.paylines = PAYLINES
        self.pay_rank = PAY_RANK
        self.multiplier_ladder = MULTIPLIER_LADDER
        self.wheel_outcomes = WHEEL_OUTCOMES
        self.entry_max_steps = ENTRY_MAX_STEPS

        self.special_symbols = {
            "wild": ["W"],
            "scatter": ["S"],
            "multiplier": ["M"],
            "locked": [],
        }
        self.freespin_triggers = {
            self.basegame_type: {3: 6, 4: 8},
            self.freegame_type: {},
        }
        self.anticipation_triggers = {
            self.basegame_type: 2,
            self.freegame_type: 99,
            # Lock respins never tease. Anticipation belongs exclusively to the
            # base-game Scatter trigger path.
            "respin": 99,
        }

        reel_files = {
            "BR0": "BR0.csv",
            "RR0": "RR0.csv",
            "RR4": "RR4.csv",
            "FR0": "FR0.csv",
        }
        self.reels = {
            reel_id: self.read_reels_csv(os.path.join(self.reels_path, file_name))
            for reel_id, file_name in reel_files.items()
        }
        self.padding_reels[self.basegame_type] = self.reels["BR0"]
        self.padding_reels[self.freegame_type] = self.reels["FR0"]

        self.mode_targets = {
            "base": {"cost": 1.0, "rtp": 0.9651, "max_win": 25000.0},
            "enhancer1": {"cost": 2.0, "rtp": 0.9651, "max_win": 25000.0},
            "featureSpin": {"cost": 20.0, "rtp": 0.9651, "max_win": 25000.0},
            "bonus1": {"cost": 100.0, "rtp": 0.9651, "max_win": 25000.0},
            "bonus2": {"cost": 500.0, "rtp": 0.9651, "max_win": 25000.0},
        }

        normal_reels = {
            self.basegame_type: {"BR0": 1},
            self.freegame_type: {"FR0": 1},
            "respin": {"RR0": 1},
        }
        standard_wheel_weights = {
            self.wheel_outcomes[0]: 100,
            self.wheel_outcomes[1]: 100,
            self.wheel_outcomes[2]: 100,
            self.wheel_outcomes[3]: 100,
            self.wheel_outcomes[4]: 100,
            self.wheel_outcomes[5]: 100,
            self.wheel_outcomes[6]: 65,
        }
        base_conditions = {
            "reel_weights": normal_reels,
            "force_freegame": False,
            "force_wincap": False,
            "direct_bonus": False,
            "force_lock_feature": False,
            "multiplier_step_weights": {1: 60, 2: 25, 3: 10, 5: 4, 10: 1},
            "wheel_weights": standard_wheel_weights,
            "bonus_entry_weights": {3: 1},
            "main_win_ceiling": None,
        }
        enhancer1_conditions = {
            **base_conditions,
            "reel_weights": {
                self.basegame_type: {"BR0": 1},
                self.freegame_type: {"FR0": 1},
                "respin": {"RR4": 1},
            },
        }
        feature_spin_conditions = {
            **base_conditions,
            "force_lock_feature": True,
        }
        bonus1_conditions = {
            **base_conditions,
            "force_freegame": True,
            "direct_bonus": True,
            "bonus_entry_weights": {3: 1},
        }
        bonus2_conditions = {
            **base_conditions,
            "force_freegame": True,
            "direct_bonus": True,
            "bonus_entry_weights": {4: 1},
            "main_win_ceiling": 9999.99,
            # Super Bonus starts higher than the normal bonus, but advances in
            # controlled steps so the 5,000x/10,000x tail remains compliant.
            "multiplier_step_weights": {1: 90, 2: 8, 3: 2},
            "wheel_weights": {
                self.wheel_outcomes[0]: 4000,
                self.wheel_outcomes[1]: 2500,
                self.wheel_outcomes[2]: 1000,
                self.wheel_outcomes[3]: 300,
                self.wheel_outcomes[4]: 75,
                self.wheel_outcomes[5]: 10,
                self.wheel_outcomes[6]: 1,
            },
        }

        self.bet_modes = [
            self._make_mode("base", base_conditions, is_feature=True),
            self._make_mode("enhancer1", enhancer1_conditions, is_feature=True),
            self._make_mode("featureSpin", feature_spin_conditions, is_feature=True),
            self._make_mode("bonus1", bonus1_conditions, is_buybonus=True),
            self._make_mode("bonus2", bonus2_conditions, is_buybonus=True),
        ]

    def _make_mode(self, name, conditions, is_feature=False, is_buybonus=False):
        target = self.mode_targets[name]
        # Put one exact 25,000x fence at an optimized probability of 1 in 5M.
        # RTP contribution is payout * probability / mode cost.
        wincap_rtp = target["max_win"] / (5_000_000 * target["cost"])
        wincap_conditions = {
            **conditions,
            "force_wincap": True,
            "force_freegame": True,
            "direct_bonus": True,
            "force_lock_feature": False,
            "bonus_entry_weights": {4: 1},
            "main_win_ceiling": None,
            "multiplier_step_weights": {1: 1},
            "wheel_weights": {self.wheel_outcomes[-1]: 1},
        }
        return BetMode(
            name=name,
            cost=target["cost"],
            rtp=target["rtp"],
            max_win=target["max_win"],
            auto_close_disabled=False,
            is_feature=is_feature,
            is_buybonus=is_buybonus,
            distributions=[
                Distribution(
                    criteria="main",
                    quota=0.99,
                    conditions=conditions,
                ),
                Distribution(
                    criteria="wincap",
                    quota=0.01,
                    win_criteria=target["max_win"],
                    conditions=wincap_conditions,
                ),
            ],
        )
