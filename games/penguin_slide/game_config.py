"""Configuration for the Penguin Slide game."""

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.config import BetMode


class GameConfig(Config):
    """Game configuration for Penguin Slide (non-slot)."""

    def __init__(self):
        super().__init__()
        self.game_id = "penguin_slide"
        self.provider_number = 1
        self.working_name = "penguin_slide"
        self.game_name = "Penguin Slide"

        # Core game parameters
        self.starting_value = 1.0
        self.min_steps = 10
        self.max_steps = 80  # safety to prevent infinite loops
        self.num_lanes = 3
        self.lane_offsets = [-1, 0, 1]
        # Enforce a minimum lane-hold so the penguin is in-lane before pickups.
        self.min_lane_change_steps = 2
        self.step_item_counts = {
            1: 75,
            2: 20,
            3: 5,
        }
        self.avoid_banana = False
        self.avoid_banana_chance = 0.0

        # Tile probabilities (can be tuned later)
        # Target ~50 steps on average (goal + slip per step ≈ 2%)
        self.tile_probs = {
            "coin": 0.45,
            "banana": 0.25,
            "star": 0.15,
            "lifering": 0.07,
            "empty": 0.05,
            "goal": 0.03,
        }

        # Coin prize values (flat additions to value)
        # Tier weights sum to 110 by design (treated as relative weights).
        self.coin_values = {
            "bronze": 90,
            "silver": 15,
            "gold": 5,
        }
        self.coin_value_tiers = {
            "bronze": (0.1, 3.0),
            "silver": (3.0, 20.0),
            "gold": (20.0, 100.0),
        }
        self.coin_value_min = 0.1
        self.coin_value_max = 100.0

        # Star multipliers (multiply current value)
        self.star_multipliers = {
            2: 40,
            3: 25,
            4: 15,
            5: 12,
            10: 8,
        }

        # Banana outcomes
        self.banana_fall_prob = 0.5
        self.high_win_threshold = 10.0  # >=10x bet is considered high win
        self.high_win_slip_mult = 1.0   # keep banana slip at 50/50 even after high win

        # Cap now matches variant max wins
        self.wincap = 10_000
        self.win_type = "burst"
        self.rtp = 0.9601
        self.construct_paths()

        # Game dimensions (not a reel-based game)
        self.num_reels = 0
        self.num_rows = [0] * self.num_reels
        self.paytable = {}
        self.include_padding = False
        self.special_symbols = {"wild": [], "scatter": [], "multiplier": []}

        self.freespin_triggers = {self.basegame_type: {}, self.freegame_type: {}}
        self.anticipation_triggers = {self.basegame_type: 0, self.freegame_type: 0}

        variant_info = [
            ("base_hard", "hard", 5.0, 1000.0),
            ("base_very_hard", "very_hard", 5.0, 5000.0),
            ("base_extreme", "extreme", 5.0, 10000.0),
        ]
        self.variant_max_wins = {variant: max_win for _, variant, _, max_win in variant_info}
        self.bet_modes = []
        for name, variant, cost, max_win in variant_info:
            self.bet_modes.append(
                BetMode(
                    name=name,
                    cost=cost,
                    rtp=self.rtp,
                    max_win=max_win,
                    auto_close_disabled=True,
                    is_feature=False,
                    is_buybonus=False,
                    distributions=[
                        Distribution(
                            criteria="basegame",
                            quota=1.0,
                            conditions={
                                "reel_weights": {},
                                "force_wincap": False,
                                "force_freegame": False,
                            },
                        )
                    ],
                )
            )
