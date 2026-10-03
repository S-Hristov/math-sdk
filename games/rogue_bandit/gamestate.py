"""Rogue Bandit custom SDK state adapter."""

from importlib import import_module

from src.state.state import GeneralGameState

M = import_module(f"{__package__}.rogue_bandit_math" if __package__ else "rogue_bandit_math")
T = import_module(f"{__package__}.math_targets" if __package__ else "math_targets")


class GameState(GeneralGameState):
    def assign_special_sym_function(self):
        self.special_symbol_functions = {}

    def run_freespin(self):
        return None

    def run_sims(self, *args, **kwargs):
        # SDK keeps this sidecar list on the reusable state object. Reset it per
        # worker batch or later modes inherit earlier payouts and fail hashes.
        self._payout_ints = []
        return super().run_sims(*args, **kwargs)

    def run_spin(self, sim, simulation_seed=None):
        self.reset_seed(sim, simulation_seed)
        self.reset_book()
        seed = (sim if simulation_seed is None else simulation_seed) + int(self.config.simulation_seed) * 10_000_019
        result = M.generate_candidate(self.betmode, self.criteria, int(seed))
        self.book.events = result["events"]
        self.triggered_freegame = result["triggered"]
        self.win_manager.running_bet_win = result["payoutMultiplier"] / T.BOOK_SCALE
        self.win_manager.basegame_wins = result["baseGameWins"] / T.BOOK_SCALE
        self.win_manager.freegame_wins = result["freeGameWins"] / T.BOOK_SCALE
        self.update_final_win()
        if self.book.to_json()["payoutMultiplier"] != result["payoutMultiplier"]:
            raise RuntimeError("SDK payout scaling mismatch")
        self.record({"criteria": self.criteria})
        if result["steals"]:
            self.record({"steals": result["steals"]})
        if result["maxHeatLevel"]:
            self.record({"maxHeatLevel": result["maxHeatLevel"]})
        self.imprint_wins()
