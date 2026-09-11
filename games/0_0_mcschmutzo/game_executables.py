from game_calculations import GameCalculations
from src.calculations.lines import Lines
from src.events.events import set_total_event, set_win_event, win_info_event


class GameExecutables(GameCalculations):
    def calculate_lines(self):
        return Lines.get_lines(
            self.board,
            self.config,
            multiplier_method="global",
            global_multiplier=self.global_multiplier,
        )

    def award_current_board(self):
        self.win_manager.reset_spin_win()
        self.win_data = self.calculate_lines()
        Lines.record_lines_wins(self)
        self.win_manager.update_spinwin(self.win_data["totalWin"])
        if self.win_data["totalWin"] > 0:
            win_info_event(self)
            self.evaluate_mode_wincap()
            set_win_event(self)
        set_total_event(self)
        self.win_manager.update_gametype_wins(self.gametype)

