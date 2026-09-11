"""Theme Park math-sdk config."""

from __future__ import annotations

from src.config.betmode import BetMode
from src.config.config import Config
from src.config.distributions import Distribution

from theme_park_math import BASE_PADDING_REELS, FREEGAME_PADDING_REELS, MAX_WIN_X, PAYLINES, PAYTABLE
from math_targets import ANTE_RATES, BASE_RATES, TARGET_RTP


class GameConfig(Config):
    def __init__(self):
        super().__init__()
        self.game_id = '0_0_theme_park'
        self.provider_number = 0
        self.provider_name = 'sample_provider'
        self.game_name = 'theme_park'
        self.working_name = 'Theme Park'
        self.output_regular_json = False
        self.wincap = float(MAX_WIN_X)
        self.win_type = 'lines'
        self.rtp = TARGET_RTP
        self.construct_paths()

        self.num_reels = 5
        self.num_rows = [5] * self.num_reels
        self.paytable = {(kind, sym): pay for sym, table in PAYTABLE.items() for kind, pay in table.items()}
        self.special_symbols = {
            'wild': ['W'],
            'scatter': ['S_DUCK', 'S_ROLLER', 'S_COASTER'],
            'duck': ['DC'],
        }
        self.paylines = PAYLINES
        self.include_padding = True
        self.padding_reels = {
            self.basegame_type: BASE_PADDING_REELS,
            self.freegame_type: FREEGAME_PADDING_REELS,
        }
        self.freespin_triggers = {self.basegame_type: {3: 10, 4: 10, 5: 10}}
        self.anticipation_triggers = {self.basegame_type: 2}
        self.write_event_list = True

        empty_conditions = {'reel_weights': {self.basegame_type: {'TP': 1}}}
        feature_conditions = {**empty_conditions, 'force_freegame': True}

        def _natural_mode(name: str, cost: float, rates: dict) -> BetMode:
            return BetMode(
                name=name,
                cost=cost,
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=True,
                is_buybonus=False,
                distributions=[
                    Distribution(criteria='0', quota=rates['0'], conditions=empty_conditions.copy()),
                    Distribution(criteria='basegame', quota=rates['basegame'], conditions=empty_conditions.copy()),
                    Distribution(criteria='duckcollect', quota=rates['duckcollect'], conditions=empty_conditions.copy()),
                    Distribution(criteria='duck', quota=rates['duck'], conditions=feature_conditions.copy()),
                    Distribution(criteria='roller', quota=rates['roller'], conditions=feature_conditions.copy()),
                    Distribution(criteria='coaster', quota=rates['coaster'], conditions=feature_conditions.copy()),
                ],
            )

        def _buy_mode(name: str, cost: float, criteria: str) -> BetMode:
            return BetMode(
                name=name,
                cost=cost,
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=False,
                is_buybonus=True,
                distributions=[
                    Distribution(criteria=criteria, quota=1.0, conditions=feature_conditions.copy()),
                ],
            )

        def _feature_spin_mode(name: str, cost: float, criteria: str) -> BetMode:
            return BetMode(
                name=name,
                cost=cost,
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=True,
                is_buybonus=False,
                distributions=[
                    Distribution(criteria=criteria, quota=1.0, conditions=feature_conditions.copy()),
                ],
            )

        self.bet_modes = [
            _natural_mode('BASE', 1.0, BASE_RATES),
            _natural_mode('ANTE', 3.0, ANTE_RATES),
            _feature_spin_mode('FSPIN1', 20.0, 'duckcollect'),
            _feature_spin_mode('FSPIN2', 60.0, 'rollerwild'),
            _buy_mode('DUCK', 100.0, 'duck'),
            _buy_mode('ROLLER', 200.0, 'roller'),
            _buy_mode('COASTER', 500.0, 'coaster'),
        ]
        self.get_special_symbol_names()
        self.get_paying_symbols()
