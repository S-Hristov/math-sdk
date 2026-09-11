from game_executables import GameExecutables
from src.calculations.statistics import get_random_outcome


class GameStateOverride(GameExecutables):
    def reset_book(self):
        super().reset_book()
        self.collected_scatters = 0
        self.locked_positions = {}
        self.locked_symbol = None

    def assign_special_sym_function(self):
        self.special_symbol_functions = {"M": [self.assign_multiplier_steps]}

    def assign_multiplier_steps(self, symbol):
        conditions = self.get_current_distribution_conditions()
        steps = get_random_outcome(conditions["multiplier_step_weights"])
        symbol.assign_attribute({"multiplier": steps})

    def mode_wincap(self):
        mode = self.get_current_betmode()
        return mode.get_wincap() if mode is not None else self.config.wincap

    def evaluate_mode_wincap(self):
        if self.win_manager.running_bet_win >= self.mode_wincap() and not self.wincap_triggered:
            self.wincap_triggered = True
            self.book.add_event(
                {
                    "index": len(self.book.events),
                    "type": "wincap",
                    "amount": int(self.mode_wincap() * 100),
                }
            )
            return True
        return False

    def evaluate_finalwin(self):
        cap = self.mode_wincap()
        self.final_win = round(min(self.win_manager.running_bet_win, cap), 2)
        self.book.payout_multiplier = self.final_win
        self.book.basegame_wins = round(min(self.win_manager.basegame_wins, cap), 2)
        remaining = max(0.0, cap - self.book.basegame_wins)
        self.book.freegame_wins = round(min(self.win_manager.freegame_wins, remaining), 2)
        self.book.add_event(
            {
                "index": len(self.book.events),
                "type": "finalWin",
                "amount": int(round(self.final_win * 100)),
            }
        )

    def check_repeat(self):
        super().check_repeat()
        conditions = self.get_current_distribution_conditions()
        main_win_ceiling = conditions.get("main_win_ceiling")
        if (
            self.repeat is False
            and not conditions.get("force_wincap", False)
            and main_win_ceiling is not None
            and self.final_win > main_win_ceiling
        ):
            self.repeat = True
