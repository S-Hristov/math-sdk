"""Custom math-sdk game state for Veggie Salad."""

from __future__ import annotations

from src.state.state import GeneralGameState

from veggie_math import generate_round_for_mode


class GameState(GeneralGameState):
    def assign_special_sym_function(self):
        self.special_symbol_functions = {}

    def run_freespin(self):
        return None

    def run_spin(self, sim, simulation_seed=None):
        seed = simulation_seed if simulation_seed is not None else sim
        self.reset_seed(sim, seed)
        self.reset_book()
        result = generate_round_for_mode(self.betmode, seed, str(self.criteria))

        for event in result["events"]:
            self.book.add_event(event)

        self.book.payout_multiplier = result["final_amount"] / 100.0
        self.book.basegame_wins = result["basegame_win"] / 100.0
        self.book.freegame_wins = result["freegame_win"] / 100.0
        self.win_manager.running_bet_win = self.book.payout_multiplier
        self.win_manager.basegame_wins = self.book.basegame_wins
        self.win_manager.freegame_wins = self.book.freegame_wins
        self.final_win = self.book.payout_multiplier
        self.triggered_freegame = result.get("trigger_tier") in ("normal", "super", "hidden")
        self.imprint_wins()
