"""Rogue Bandit SDK configuration."""

from importlib import import_module

from src.config.betmode import BetMode
from src.config.config import Config
from src.config.distributions import Distribution

T = import_module(f"{__package__}.math_targets" if __package__ else "math_targets")


class GameConfig(Config):
    def __init__(self):
        super().__init__()
        T.check_targets()
        self.game_id = T.GAME_ID
        self.game_name = T.GAME_ID
        self.provider_name = "reelcraft"
        self.provider_number = 0
        self.working_name = "Rogue Bandit"
        self.output_regular_json = False
        self.write_event_list = False
        self.simulation_seed = 20261002
        self.wincap = T.MAX_WIN_X
        self.win_type = "cluster"
        self.rtp = float(T.MODE_RTPS["base"])
        self.num_reels = T.COLS
        self.num_rows = [T.ROWS] * T.COLS
        self.include_padding = True
        self.construct_paths()

        self.paytable = self.convert_range_table({
            (band, symbol): value / T.BOOK_SCALE
            for symbol, awards in T.PAYTABLE.items()
            for band, value in zip(T.PAYOUT_BANDS, awards)
        })
        self.special_symbols = {"scatter": [T.SCATTER]}
        self.freespin_triggers = {
            self.basegame_type: {count: T.FREE_SPINS for count in range(4, T.COLS * T.ROWS + 1)},
            self.freegame_type: {count: T.RETRIGGER_SPINS for count in range(3, T.COLS * T.ROWS + 1)},
        }
        self.anticipation_triggers = {self.basegame_type: 3, self.freegame_type: 2}
        padding = [[T.SYMBOLS[(col + row) % len(T.SYMBOLS)] for row in range(T.ROWS + 2)]
                   for col in range(T.COLS)]
        self.padding_reels = {self.basegame_type: padding, self.freegame_type: padding}

        flags = {
            "base": (False, False), "ante": (True, False), "superspin": (True, False),
            "bonus": (False, True), "superbonus": (False, True),
        }
        self.bet_modes = []
        for mode, cost in T.MODE_COSTS.items():
            is_feature, is_buybonus = flags[mode]
            distributions = [
                Distribution(
                    criteria=criteria,
                    quota=quota,
                    required_distribution_conditions=["proposal"],
                    conditions={"proposal": criteria},
                )
                for criteria, quota in T.GENERATION_QUOTAS[mode].items()
            ]
            self.bet_modes.append(BetMode(
                name=mode, cost=float(cost), rtp=float(T.MODE_RTPS[mode]), max_win=self.wincap,
                auto_close_disabled=False, is_feature=is_feature, is_buybonus=is_buybonus,
                distributions=distributions,
            ))
        self.get_special_symbol_names()
        self.get_paying_symbols()
