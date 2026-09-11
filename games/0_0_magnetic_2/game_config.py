"""Magnetic 2 Mothership math-sdk config."""

from __future__ import annotations

from src.config.betmode import BetMode
from src.config.config import Config
from src.config.distributions import Distribution

from magnetic_math import MAX_WIN_X, PAYTABLE_BANDS
from math_targets import BASE_RATES, CHANCE_RATES, TARGET_RTP


def _paytable_from_bands():
    pay_group = {}
    for symbol, bands in PAYTABLE_BANDS.items():
        for start, end, payout in bands:
            pay_group[((start, end), symbol)] = payout
    return pay_group


class GameConfig(Config):
    def __init__(self):
        super().__init__()
        self.game_id = '0_0_magnetic_2'
        self.provider_number = 0
        self.provider_name = 'sample_provider'
        self.game_name = 'magnetic_2'
        self.working_name = 'Magnetic 2: Mothership'
        self.output_regular_json = False
        self.wincap = float(MAX_WIN_X)
        self.win_type = 'clusters'
        self.rtp = TARGET_RTP
        self.construct_paths()

        self.num_reels = 7
        self.num_rows = [7] * self.num_reels
        self.paytable = self.convert_range_table(_paytable_from_bands())
        self.special_symbols = {
            'magnet': ['MAGNET'],
            'scatter': ['SCATTER'],
            'wild': ['WILD'],
            'polarity': ['POLARITY'],
        }
        self.include_padding = False
        self.superspin_type = 'superspin'
        self.hidden_type = 'hidden'
        self.feature_type = 'feature'
        self.freespin_triggers = {self.basegame_type: {3: 10, 4: 10, 5: 10}}
        self.anticipation_triggers = {self.basegame_type: 2}
        self.write_event_list = True

        empty_conditions = {'reel_weights': {self.basegame_type: {'PROTO': 1}}}
        self.bet_modes = [
            BetMode(
                name='BASE',
                cost=1.0,
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=True,
                is_buybonus=False,
                distributions=[
                    Distribution(criteria='0', quota=BASE_RATES['0'], conditions=empty_conditions.copy()),
                    Distribution(criteria='basegame', quota=BASE_RATES['basegame'], conditions=empty_conditions.copy()),
                    Distribution(criteria='bonus', quota=BASE_RATES['bonus'], conditions={**empty_conditions, 'force_freegame': True}),
                    Distribution(criteria='super', quota=BASE_RATES['super'], conditions={**empty_conditions, 'force_freegame': True}),
                    Distribution(criteria='hidden', quota=BASE_RATES['hidden'], conditions={**empty_conditions, 'force_freegame': True}),
                ],
            ),
            BetMode(
                name='CHANCE',
                cost=2.0,
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=True,
                is_buybonus=False,
                distributions=[
                    Distribution(criteria='0', quota=CHANCE_RATES['0'], conditions=empty_conditions.copy()),
                    Distribution(criteria='basegame', quota=CHANCE_RATES['basegame'], conditions=empty_conditions.copy()),
                    Distribution(criteria='bonus', quota=CHANCE_RATES['bonus'], conditions={**empty_conditions, 'force_freegame': True}),
                    Distribution(criteria='super', quota=CHANCE_RATES['super'], conditions={**empty_conditions, 'force_freegame': True}),
                    Distribution(criteria='hidden', quota=CHANCE_RATES['hidden'], conditions={**empty_conditions, 'force_freegame': True}),
                ],
            ),
            BetMode(
                name='FEATURE',
                cost=50.0,
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=False,
                is_buybonus=True,
                distributions=[
                    Distribution(criteria='feature', quota=1.0, conditions={**empty_conditions, 'force_freegame': True}),
                ],
            ),
            BetMode(
                name='BONUS',
                cost=100.0,
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=False,
                is_buybonus=True,
                distributions=[
                    Distribution(criteria='bonus', quota=1.0, conditions={**empty_conditions, 'force_freegame': True}),
                ],
            ),
            BetMode(
                name='MYSTERY',
                cost=300.0,
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=False,
                is_buybonus=True,
                distributions=[
                    Distribution(criteria='mystery', quota=1.0, conditions={**empty_conditions, 'force_freegame': True}),
                ],
            ),
            BetMode(
                name='SUPER',
                cost=500.0,
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=False,
                is_buybonus=True,
                distributions=[
                    Distribution(criteria='super', quota=1.0, conditions={**empty_conditions, 'force_freegame': True}),
                ],
            ),
        ]
        self.get_special_symbol_names()
        self.get_paying_symbols()
