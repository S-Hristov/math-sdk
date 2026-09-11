"""math-sdk configuration for Veggie Salad."""

from __future__ import annotations

from src.config.betmode import BetMode
from src.config.config import Config
from src.config.distributions import Distribution

from math_targets import MAX_WIN_X, MODE_COSTS, TARGET_RTP
from veggie_math import PAYTABLE


def _sdk_paytable() -> dict:
    result = {}
    for symbol, pays in PAYTABLE.items():
        for size, payout in pays.items():
            key = ((size, 100), symbol) if size == 15 else ((size, size), symbol)
            result[key] = payout
    return result


def _conditions() -> dict:
    return {"reel_weights": {"basegame": {"VEGGIE": 1}}}


def _dist(criteria: str, quota: float) -> Distribution:
    return Distribution(criteria=criteria, quota=quota, conditions=_conditions())


def _max_dist() -> Distribution:
    return Distribution(criteria="max", fixed_amt=1, conditions=_conditions())


def _tail_dist(tier: str) -> Distribution:
    return Distribution(criteria=f"tail_{tier}", fixed_amt=1, conditions=_conditions())


class GameConfig(Config):
    def __init__(self):
        super().__init__()
        self.game_id = "0_0_veggie_salad"
        self.provider_number = 0
        self.provider_name = "sample_provider"
        self.game_name = "veggie_salad"
        self.working_name = "Veggie Salad"
        self.output_regular_json = False
        self.wincap = float(MAX_WIN_X)
        self.win_type = "clusters"
        self.rtp = TARGET_RTP
        self.construct_paths()

        self.num_reels = 7
        self.num_rows = [7] * 7
        self.paytable = self.convert_range_table(_sdk_paytable())
        self.special_symbols = {"scatter": ["SCATTER"]}
        self.include_padding = False
        self.write_event_list = True
        self.freespin_triggers = {
            self.basegame_type: {3: 10, 4: 10, **{count: 10 for count in range(5, 50)}}
        }
        self.anticipation_triggers = {self.basegame_type: 2}

        self.bet_modes = [
            BetMode(
                name="BASE",
                cost=MODE_COSTS["BASE"],
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=True,
                is_buybonus=False,
                distributions=[
                    _max_dist(),
                    _tail_dist("normal"),
                    _tail_dist("super"),
                    _tail_dist("hidden"),
                    _dist("0", 0.20),
                    _dist("basegame", 0.35),
                    _dist("normal", 0.20),
                    _dist("super", 0.15),
                    _dist("hidden", 0.10),
                ],
            ),
            BetMode(
                name="CHANCE",
                cost=MODE_COSTS["CHANCE"],
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=True,
                is_buybonus=False,
                distributions=[
                    _max_dist(),
                    _tail_dist("normal"),
                    _tail_dist("super"),
                    _tail_dist("hidden"),
                    _dist("0", 0.20),
                    _dist("basegame", 0.35),
                    _dist("normal", 0.20),
                    _dist("super", 0.15),
                    _dist("hidden", 0.10),
                ],
            ),
            BetMode(
                name="FEATURE",
                cost=MODE_COSTS["FEATURE"],
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=False,
                is_buybonus=True,
                distributions=[_max_dist(), _dist("feature", 1.0)],
            ),
            BetMode(
                name="BONUS",
                cost=MODE_COSTS["BONUS"],
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=False,
                is_buybonus=True,
                distributions=[_max_dist(), _tail_dist("normal"), _dist("normal", 1.0)],
            ),
            BetMode(
                name="MYSTERY",
                cost=MODE_COSTS["MYSTERY"],
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=False,
                is_buybonus=True,
                distributions=[
                    _max_dist(),
                    _tail_dist("normal"),
                    _tail_dist("super"),
                    _tail_dist("hidden"),
                    _dist("normal", 0.45),
                    _dist("super", 0.35),
                    _dist("hidden", 0.20),
                ],
            ),
            BetMode(
                name="SUPER",
                cost=MODE_COSTS["SUPER"],
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=False,
                is_buybonus=True,
                distributions=[_max_dist(), _tail_dist("super"), _dist("super", 1.0)],
            ),
        ]
        self.get_special_symbol_names()
        self.get_paying_symbols()
