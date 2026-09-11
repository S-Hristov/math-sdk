"""Magnetic proto custom gamestate."""

from __future__ import annotations

from src.state.state import GeneralGameState

from magnetic_math import generate_round_for_mode


class GameState(GeneralGameState):
    def assign_special_sym_function(self):
        self.special_symbol_functions = {}

    def run_freespin(self):
        return None

    def _accept_round(self, result: dict) -> bool:
        criteria = str(self.criteria)
        trigger_mode = result.get('trigger_mode')
        final_amount = int(result.get('final_amount', 0))
        base_amount = int(result.get('basegame_win', 0))
        if criteria == '0':
            return trigger_mode is None and final_amount == 0
        if criteria == 'basegame':
            return trigger_mode is None and base_amount > 0
        if criteria == 'bonus':
            return trigger_mode == self.config.freegame_type
        if criteria == 'super':
            return trigger_mode == self.config.superspin_type
        if criteria == 'feature':
            return trigger_mode == self.config.feature_type
        return True

    def run_spin(self, sim, simulation_seed=None):
        seed = simulation_seed if simulation_seed is not None else sim
        self.reset_seed(sim, seed)
        while True:
            self.reset_book()
            # Lookup quotas intentionally contain far more trigger books than the
            # natural trigger rate. Generate the requested trigger directly; the
            # lookup weights, not rejection sampling, define production odds.
            result = generate_round_for_mode(self.betmode, seed + self.repeat_count, str(self.criteria))
            if not self._accept_round(result):
                self.repeat_count += 1
                continue

            for event in result['events']:
                self.book.add_event(event)

            self.book.payout_multiplier = result['final_amount'] / 100.0
            self.book.basegame_wins = result['basegame_win'] / 100.0
            self.book.freegame_wins = result['freegame_win'] / 100.0
            self.win_manager.running_bet_win = self.book.payout_multiplier
            self.win_manager.basegame_wins = self.book.basegame_wins
            self.win_manager.freegame_wins = self.book.freegame_wins
            self.final_win = self.book.payout_multiplier
            self.triggered_freegame = result.get('trigger_mode') in (self.config.freegame_type, self.config.superspin_type, self.config.feature_type)
            self.imprint_wins()
            return
