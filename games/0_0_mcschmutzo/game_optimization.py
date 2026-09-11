"""Optimization targets for McSchmutzo."""

from optimization_program.optimization_config import (
    ConstructConditions,
    ConstructParameters,
    ConstructScaling,
    verify_optimization_input,
)


class OptimizationSetup:
    def __init__(self, game_config):
        self.game_config = game_config
        self.game_config.opt_params = {}
        for mode, target in game_config.mode_targets.items():
            wincap_rtp = target["max_win"] / (5_000_000 * target["cost"])
            scaling = []
            if mode == "bonus2":
                scaling = [
                    {
                        "criteria": "main",
                        "scale_factor": 0.15,
                        "win_range": (5000, 10000),
                        "probability": 1.0,
                    },
                    {
                        "criteria": "main",
                        "scale_factor": 0.03,
                        "win_range": (10000, target["max_win"]),
                        "probability": 1.0,
                    },
                ]
            self.game_config.opt_params[mode] = {
                "conditions": {
                    "main": ConstructConditions(
                        rtp=target["rtp"] - wincap_rtp,
                        hr="x",
                    ).return_dict(),
                    "wincap": ConstructConditions(
                        rtp=wincap_rtp,
                        av_win=target["max_win"],
                        search_conditions=target["max_win"],
                    ).return_dict(),
                },
                "scaling": ConstructScaling(scaling).return_dict(),
                "parameters": ConstructParameters(
                    num_show=5000,
                    num_per_fence=10000,
                    min_m2m=4,
                    max_m2m=8,
                    pmb_rtp=1.0,
                    sim_trials=5000,
                    test_spins=[50, 100, 200],
                    test_weights=[0.3, 0.4, 0.3],
                    score_type="rtp",
                ).return_dict(),
            }
        verify_optimization_input(self.game_config, self.game_config.opt_params)
