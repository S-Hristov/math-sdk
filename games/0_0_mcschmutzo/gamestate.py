import random
from copy import deepcopy

from game_events import (
    bonus_wheel_event,
    freegame_end_event,
    lock_respin_end_event,
    lock_respin_start_event,
    lock_respin_update_event,
    multiplier_update_event,
)
from game_override import GameStateOverride
from src.calculations.lines import Lines
from src.calculations.statistics import get_random_outcome
from src.events.events import reveal_event, update_freespin_event, win_info_event


class GameState(GameStateOverride):
    """McSchmutzo round and feature state."""

    def run_spin(self, sim, simulation_seed):
        self.reset_seed(sim, simulation_seed)
        self.repeat = True
        while self.repeat:
            self.reset_book()

            conditions = self.get_current_distribution_conditions()
            if conditions["direct_bonus"]:
                entry = get_random_outcome(conditions["bonus_entry_weights"])
                self.play_bonus_entry_spin(entry)
                self.run_bonus(entry)
            else:
                self.run_base_spin()

            self.evaluate_finalwin()
            self.check_repeat()
        self.imprint_wins()

    def run_base_spin(self):
        self.gametype = self.config.basegame_type
        conditions = self.get_current_distribution_conditions()
        if conditions.get("force_lock_feature", False):
            while True:
                self.draw_board(emit_event=False)
                initial_win_data = self.calculate_lines()
                if initial_win_data["totalWin"] > 0:
                    break
            reveal_event(self)
        else:
            self.draw_board()
            initial_win_data = self.calculate_lines()

        if initial_win_data["totalWin"] <= 0:
            self.award_current_board()
            return

        self.win_data = initial_win_data
        win_info_event(self)
        target_symbol = self.highest_value_win_symbol(initial_win_data)
        self.run_lock_respin(target_symbol, initial_win_data)

    def highest_value_win_symbol(self, win_data):
        symbols = {win["symbol"] for win in win_data["wins"]}
        return min(symbols, key=lambda symbol: self.config.pay_rank[symbol])

    def qualifying_positions(self, target_symbol, win_data):
        positions = {}
        for win in win_data["wins"]:
            if win["symbol"] != target_symbol:
                continue
            for position in win["positions"]:
                reel, row = position["reel"], position["row"]
                if self.board[reel][row].name in (target_symbol, "W"):
                    positions[(reel, row)] = {"reel": reel, "row": row}
        return positions

    def run_lock_respin(self, target_symbol, initial_win_data, allow_bonus_trigger=True):
        self.collected_scatters = 0
        self.locked_symbol = target_symbol
        self.locked_positions = self.qualifying_positions(target_symbol, initial_win_data)
        for reel, row in self.locked_positions:
            self.board[reel][row].assign_attribute({"locked": True})
        lock_respin_start_event(self, target_symbol, list(self.locked_positions.values()))

        origin_gametype = self.gametype
        while not self.wincap_triggered and len(self.locked_positions) < 25:
            previous_locked = set(self.locked_positions)
            locked_symbols = {
                position: deepcopy(self.board[position[0]][position[1]]) for position in previous_locked
            }

            self.gametype = "respin"
            self.create_board_reelstrips()
            for (reel, row), symbol in locked_symbols.items():
                symbol.assign_attribute({"locked": True})
                self.board[reel][row] = symbol
            self.limit_scatter_symbols_on_board()
            self.get_special_symbols_on_board()
            reveal_event(self)

            scatter_positions, multiplier_positions, added_steps = self.collect_respin_specials()
            current_win_data = Lines.get_lines(self.board, self.config)
            new_positions = self.add_new_locked_positions(target_symbol, current_win_data)
            lock_respin_update_event(
                self,
                new_positions,
                scatter_positions,
                multiplier_positions,
                added_steps,
            )
            if not new_positions:
                break

        self.gametype = origin_gametype
        lock_respin_end_event(self, target_symbol, list(self.locked_positions.values()))
        self.award_current_board()

        if allow_bonus_trigger and self.collected_scatters >= 3 and not self.wincap_triggered:
            entry = 4 if self.collected_scatters == 4 else 3
            self.run_bonus(entry)

    def limit_scatter_symbols_on_board(self):
        """Never reveal/collect more than four activation scatters per sequence."""
        allowed = max(0, 4 - self.collected_scatters)
        scatter_positions = [
            (reel, row)
            for reel in range(self.config.num_reels)
            for row in range(self.config.num_rows[reel])
            if self.board[reel][row].name == "S"
        ]
        random.shuffle(scatter_positions)
        for reel, row in scatter_positions[allowed:]:
            replacement = random.choice(tuple(self.config.pay_rank))
            self.board[reel][row] = self.create_symbol(replacement)

    def add_new_locked_positions(self, target_symbol, current_win_data):
        candidates = {}
        for reel in range(self.config.num_reels):
            for row in range(self.config.num_rows[reel]):
                if self.board[reel][row].name == target_symbol:
                    candidates[(reel, row)] = {"reel": reel, "row": row}

        # Wilds in an already-paying target-symbol line lock with that line.
        for position, value in self.qualifying_positions(target_symbol, current_win_data).items():
            candidates[position] = value

        # Also retain a Wild when it extends a consecutive target/Wild prefix from reel 1.
        # This lets a two-symbol connection survive into the next re-spin and complete a payline,
        # matching the unconditional persistence already used for newly landed target symbols.
        for line in self.config.paylines.values():
            connected_positions = []
            has_target = False
            for reel, row in enumerate(line):
                symbol = self.board[reel][row].name
                if symbol not in (target_symbol, "W"):
                    break
                connected_positions.append((reel, row, symbol))
                has_target = has_target or symbol == target_symbol
            if not has_target:
                continue
            for reel, row, symbol in connected_positions:
                if symbol == "W":
                    candidates[(reel, row)] = {"reel": reel, "row": row}

        new_positions = []
        for position, value in candidates.items():
            if position not in self.locked_positions:
                self.locked_positions[position] = value
                new_positions.append(value)
            self.board[position[0]][position[1]].assign_attribute({"locked": True})
        return new_positions

    def collect_respin_specials(self):
        scatter_positions = deepcopy(self.special_syms_on_board["scatter"])
        multiplier_positions = deepcopy(self.special_syms_on_board["multiplier"])
        self.collected_scatters += len(scatter_positions)
        added_steps = sum(
            self.board[position["reel"]][position["row"]].multiplier for position in multiplier_positions
        )
        if added_steps:
            self.advance_multiplier(added_steps, "respin")
        return scatter_positions, multiplier_positions, added_steps

    def advance_multiplier(self, added_steps, source):
        previous = self.global_multiplier
        ladder = self.config.multiplier_ladder
        index = ladder.index(previous)
        self.global_multiplier = ladder[min(index + added_steps, len(ladder) - 1)]
        multiplier_update_event(self, previous, added_steps, source)

    def play_bonus_entry_spin(self, entry):
        """Open a bought bonus on the spin that would have triggered it.

        A direct bonus used to emit the wheel with nothing on the board behind it, so the buy cut
        straight to the wheel and the player never saw the Scatters they paid for. This lands a
        base board carrying exactly `entry` Scatters (3 Normal, 4 Super) and NO line win, so the
        round still pays out of the free spins alone and the buy's RTP is unchanged.
        """
        self.gametype = self.config.basegame_type
        for _ in range(200):
            self.force_special_board("scatter", entry)
            if self.calculate_lines()["totalWin"] <= 0:
                break
        self.get_special_symbols_on_board()
        reveal_event(self)

    def run_bonus(self, entry):
        self.triggered_freegame = True
        conditions = self.get_current_distribution_conditions()
        free_spins, wheel_steps = get_random_outcome(conditions["wheel_weights"])
        added_steps = self.bonus_entry_steps(entry, wheel_steps)
        previous = self.global_multiplier
        self.advance_multiplier(added_steps, "wheel")
        self.tot_fs = free_spins
        bonus_wheel_event(self, entry, free_spins, added_steps, previous)
        self.run_freespin()

    def bonus_entry_steps(self, entry, wheel_steps):
        """Normal uses wheel steps; Super doubles them up to its 30-step cap."""
        step_multiplier = 1 if entry == 3 else 2
        return min(wheel_steps * step_multiplier, self.config.entry_max_steps[entry])

    def run_freespin(self):
        self.gametype = self.config.freegame_type
        self.fs = 0
        freegame_start_win = self.win_manager.freegame_wins
        while self.fs < self.tot_fs and not self.wincap_triggered:
            update_freespin_event(self)
            self.fs += 1
            self.draw_board()
            multiplier_positions = self.special_syms_on_board["multiplier"]
            added_steps = sum(
                self.board[position["reel"]][position["row"]].multiplier
                for position in multiplier_positions
            )
            if added_steps:
                self.advance_multiplier(added_steps, "freegame")
            initial_win_data = self.calculate_lines()
            if initial_win_data["totalWin"] > 0:
                self.win_data = initial_win_data
                win_info_event(self)
                target_symbol = self.highest_value_win_symbol(initial_win_data)
                self.run_lock_respin(target_symbol, initial_win_data, allow_bonus_trigger=False)
            else:
                self.award_current_board()

        freegame_end_event(self, self.win_manager.freegame_wins - freegame_start_win)

    def evaluate_finalwin(self):
        super().evaluate_finalwin()
        self.win_manager.basegame_wins = self.book.basegame_wins
        self.win_manager.freegame_wins = self.book.freegame_wins
        self.win_manager.running_bet_win = self.final_win
