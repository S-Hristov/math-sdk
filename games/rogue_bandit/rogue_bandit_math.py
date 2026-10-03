"""Deterministic Rogue Bandit mechanics and candidate generation."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
import random
from typing import Iterable

try:
    from . import math_targets as T
except ImportError:
    import math_targets as T

Cell = tuple[int, int]
Board = list[list[str]]  # padded columns: row 0 + visible 1..8 + row 9


class CandidateRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class Cluster:
    symbol: str
    cells: tuple[Cell, ...]
    base_award: int


@dataclass(frozen=True)
class Steal:
    source: Cell
    target: Cell
    symbol: str
    displaced: str
    near_miss: tuple[Cell, ...]


def neighbours(col: int, row: int) -> Iterable[Cell]:
    for c, r in ((col - 1, row), (col + 1, row), (col, row - 1), (col, row + 1)):
        if 0 <= c < T.COLS and T.ROW_OFFSET <= r < T.ROW_OFFSET + T.ROWS:
            yield c, r


def component(board: Board, start: Cell, symbol: str, seen: set[Cell] | None = None) -> set[Cell]:
    visited = set() if seen is None else seen
    if start in visited or board[start[0]][start[1]] != symbol:
        return set()
    out = {start}
    visited.add(start)
    queue = deque([start])
    while queue:
        for candidate in neighbours(*queue.popleft()):
            c, r = candidate
            if candidate not in visited and board[c][r] == symbol:
                visited.add(candidate)
                out.add(candidate)
                queue.append(candidate)
    return out


def payout(symbol: str, size: int) -> int:
    for index, (lower, upper) in enumerate(T.PAYOUT_BANDS):
        if lower <= size <= upper:
            return T.PAYTABLE[symbol][index]
    return 0


def evaluate_clusters(board: Board) -> list[Cluster]:
    seen: set[Cell] = set()
    wins = []
    for col in range(T.COLS):
        for row in range(T.ROW_OFFSET, T.ROW_OFFSET + T.ROWS):
            cell = (col, row)
            symbol = board[col][row]
            if cell in seen or symbol == T.SCATTER:
                continue
            cells = component(board, cell, symbol, seen)
            if len(cells) >= T.MIN_CLUSTER:
                wins.append(Cluster(symbol, tuple(sorted(cells)), payout(symbol, len(cells))))
    return wins


def find_steals(board: Board) -> list[Steal]:
    """Return legal swaps. Each returned swap is asserted to create its target cluster."""
    candidates: list[Steal] = []
    for tc in range(T.COLS):
        for tr in range(T.ROW_OFFSET, T.ROW_OFFSET + T.ROWS):
            displaced = board[tc][tr]
            if displaced == T.SCATTER:
                continue
            target = (tc, tr)
            for symbol in T.SYMBOLS:
                if symbol == displaced:
                    continue
                adjacent: set[Cell] = set()
                seen: set[Cell] = {target}
                for neighbour in neighbours(tc, tr):
                    c, r = neighbour
                    if board[c][r] == symbol and neighbour not in seen:
                        adjacent.update(component(board, neighbour, symbol, seen))
                if len(adjacent) + 1 < T.MIN_CLUSTER:
                    continue
                for sc in range(T.COLS):
                    for sr in range(T.ROW_OFFSET, T.ROW_OFFSET + T.ROWS):
                        source = (sc, sr)
                        if source == target or source in adjacent or board[sc][sr] != symbol:
                            continue
                        candidates.append(Steal(source, target, symbol, displaced, tuple(sorted(adjacent))))
    return candidates


def choose_steal(board: Board, rng: random.Random) -> Steal | None:
    candidates = find_steals(board)
    if not candidates:
        return None
    largest = max(len(candidate.near_miss) for candidate in candidates)
    top = [candidate for candidate in candidates if len(candidate.near_miss) == largest]
    farthest = max(abs(s.source[0] - s.target[0]) + abs(s.source[1] - s.target[1]) for s in top)
    visible = [s for s in top if abs(s.source[0] - s.target[0]) + abs(s.source[1] - s.target[1]) >= min(3, farthest)]
    return rng.choice(visible)


def apply_steal(board: Board, steal: Steal) -> None:
    sc, sr = steal.source
    tc, tr = steal.target
    board[sc][sr], board[tc][tr] = board[tc][tr], board[sc][sr]
    target_cluster = component(board, steal.target, steal.symbol)
    assert len(target_cluster) >= T.MIN_CLUSTER and steal.target in target_cluster


def symbol_json(symbol: str) -> dict:
    return {"name": symbol, **({"scatter": True} if symbol == T.SCATTER else {})}


def board_json(board: Board) -> list[list[dict]]:
    return [[symbol_json(symbol) for symbol in column] for column in board]


def positions_json(cells: Iterable[Cell]) -> list[dict]:
    return [{"reel": col, "row": row} for col, row in sorted(cells)]


def scatter_positions(board: Board) -> list[Cell]:
    return [(col, row) for col in range(T.COLS)
            for row in range(T.ROW_OFFSET, T.ROW_OFFSET + T.ROWS)
            if board[col][row] == T.SCATTER]


class ProposalSource:
    """Seeded, stratified candidate source. LUT weights—not this source—are live math."""

    def __init__(self, rng: random.Random, mode: str, criteria: str):
        self.rng = rng
        self.mode = mode
        self.criteria = criteria
        self.hot_symbol = "H1" if criteria == "wincap" else rng.choice(T.SYMBOLS)
        self.hot_probability = {
            "wincap": .999,
            "hot": .58,
            "100plus": .42,
            "10to100": .12,
        }.get(criteria, 0.0)

    def draw(self, mode: str, allow_scatter: bool = True) -> str:
        if self.rng.random() < self.hot_probability:
            return self.hot_symbol
        rule = T.MODE_RULES[mode]
        items = list(T.SYMBOLS)
        weights = [T.SYMBOL_WEIGHTS[symbol] for symbol in items]
        if allow_scatter and self.criteria != "wincap":
            items.append(T.SCATTER)
            weights.append(T.SYMBOL_WEIGHTS[T.SCATTER] * rule["scatter_factor"])
        return self.rng.choices(items, weights=weights, k=1)[0]

    def board(self, mode: str, *, allow_scatter: bool = True, require_steal: bool = False) -> Board:
        for _ in range(500):
            board = [[self.draw(mode, allow_scatter) for _ in range(T.ROWS + 2)] for _ in range(T.COLS)]
            if require_steal and not evaluate_clusters(board) and not find_steals(board):
                continue
            return board
        raise CandidateRejected("could not draw requested board")

    def trigger_board(self, scatters: int) -> Board:
        old_hot = self.hot_probability
        self.hot_probability = 0.0
        try:
            for _ in range(500):
                board = self.board("base", allow_scatter=False)
                for flat in self.rng.sample(range(T.COLS * T.ROWS), scatters):
                    col, visible_row = divmod(flat, T.ROWS)
                    board[col][visible_row + T.ROW_OFFSET] = T.SCATTER
                if not evaluate_clusters(board):
                    return board
        finally:
            self.hot_probability = old_hot
        raise CandidateRejected("could not construct scatter trigger board")


class Round:
    def __init__(self, source: ProposalSource):
        self.source = source
        self.rng = source.rng
        self.events: list[dict] = []
        self.total = 0
        self.base = 0
        self.free = 0
        self.steals = 0
        self.max_heat_level = 0
        self.triggered = False

    def emit(self, kind: str, **payload) -> None:
        self.events.append({"index": len(self.events), "type": kind, **payload})

    def _add(self, amount: int, stage: str) -> int:
        paid = min(amount, T.MAX_WIN_AMOUNT - self.total)
        self.total += paid
        if stage == "basegame":
            self.base += paid
        else:
            self.free += paid
        return paid

    def _win_level(self, amount: int, feature: bool = False) -> int:
        x = amount / T.BOOK_SCALE
        bands = (1, 5, 10, 20, 50, 100, 500, 2000, T.MAX_WIN_X) if feature else (.1, 1, 2, 5, 15, 30, 50, 100, T.MAX_WIN_X)
        return next((index + 1 for index, upper in enumerate(bands) if x < upper), 10)

    def _tumble(self, board: Board, removed: set[Cell], mode: str) -> list[list[dict]]:
        new_symbols: list[list[dict]] = []
        for col in range(T.COLS):
            keep = [symbol for row, symbol in enumerate(board[col]) if (col, row) not in removed]
            added = [self.source.draw(mode) for _ in range(len(board[col]) - len(keep))]
            board[col] = added + keep
            new_symbols.append([symbol_json(symbol) for symbol in added])
        return new_symbols

    def play_spin(self, mode: str, stage: str, heat_level: int, board: Board | None = None,
                  no_steal: bool = False) -> tuple[int, int, Board]:
        rule = T.MODE_RULES[mode]
        require_steal = rule["steal_prob"] == 1 and not no_steal and self.source.criteria != "wincap"
        board = board or self.source.board(mode, require_steal=require_steal)
        self.emit("reveal", board=board_json(board), paddingPositions=[self.rng.randrange(250) for _ in range(T.COLS)],
                  gameType=stage, anticipation=[0] * T.COLS)
        if rule["heat_start"] is not None and rule["heat_start"] > 0:
            heat_level = rule["heat_start"]
            self.max_heat_level = max(self.max_heat_level, heat_level)
            self.emit("updateGlobalMult", globalMult=T.HEAT[heat_level])
        spin_total = 0
        steals_this_spin = 0
        cascades = 0
        while self.total < T.MAX_WIN_AMOUNT:
            wins = evaluate_clusters(board)
            if wins:
                cascades += 1
                if cascades > T.MAX_CASCADES:
                    raise CandidateRejected("cascade guard exceeded")
                multiplier = T.HEAT[heat_level]
                raw_awards = [win.base_award * multiplier for win in wins]
                paid_step = min(sum(raw_awards), T.MAX_WIN_AMOUNT - self.total)
                remaining = paid_step
                win_rows = []
                for win, raw in zip(wins, raw_awards):
                    paid = min(raw, remaining)
                    remaining -= paid
                    if paid <= 0:
                        break
                    mid = win.cells[len(win.cells) // 2]
                    win_rows.append({"symbol": win.symbol, "clusterSize": len(win.cells), "win": paid,
                                     "positions": positions_json(win.cells),
                                     "meta": {"globalMult": multiplier, "clusterMult": 1,
                                              "winWithoutMult": win.base_award / T.BOOK_SCALE,
                                              "overlay": {"reel": mid[0], "row": mid[1]}}})
                paid_step = self._add(paid_step, stage)
                spin_total += paid_step
                self.emit("winInfo", totalWin=paid_step, wins=win_rows)
                self.emit("updateTumbleWin", amount=spin_total)
                if self.total >= T.MAX_WIN_AMOUNT:
                    break
                removed = {cell for win in wins for cell in win.cells}
                self.emit("tumbleBoard", newSymbols=self._tumble(board, removed, mode),
                          explodingSymbols=positions_json(removed))
                continue
            if no_steal or steals_this_spin >= rule["max_steals"] or self.rng.random() >= rule["steal_prob"]:
                break
            steal = choose_steal(board, self.rng)
            if steal is None:
                break
            apply_steal(board, steal)
            steals_this_spin += 1
            self.steals += 1
            heat_level = min(heat_level + 1, len(T.HEAT) - 1)
            self.max_heat_level = max(self.max_heat_level, heat_level)
            self.emit("steal", **{"from": {"reel": steal.source[0], "row": steal.source[1]},
                                  "to": {"reel": steal.target[0], "row": steal.target[1]},
                                  "symbol": steal.symbol, "displaced": steal.displaced,
                                  "nearMiss": positions_json(steal.near_miss),
                                  "heat": {"level": heat_level, "multiplier": T.HEAT[heat_level]}})
            self.emit("updateGlobalMult", globalMult=T.HEAT[heat_level])
        if spin_total > 0:
            self.emit("setWin", amount=spin_total, winLevel=self._win_level(spin_total))
        return spin_total, heat_level, board

    def free_spins(self, kind: str, trigger: list[Cell]) -> None:
        mode = "superfreegame" if kind == "superbonus" else "freegame"
        heat_level = 3 if kind == "superbonus" else 0
        total_fs = T.FREE_SPINS
        played = 0
        self.triggered = True
        self.emit("freeSpinTrigger", totalFs=total_fs, positions=positions_json(trigger))
        while played < total_fs and self.total < T.MAX_WIN_AMOUNT:
            if total_fs > T.MAX_FREE_SPINS:
                raise CandidateRejected("free-spin guard exceeded")
            played += 1
            self.emit("updateFreeSpin", amount=played, total=total_fs)
            self.emit("updateGlobalMult", globalMult=T.HEAT[heat_level])
            before = self.free
            _, heat_level, board = self.play_spin(mode, "freegame", heat_level)
            self.emit("setTotalWin", amount=self.total)
            scatters = scatter_positions(board)
            if len(scatters) >= 3 and self.total < T.MAX_WIN_AMOUNT:
                total_fs += T.RETRIGGER_SPINS
                self.emit("freeSpinRetrigger", totalFs=total_fs, positions=positions_json(scatters))
        self.emit("freeSpinEnd", amount=self.free, winLevel=self._win_level(self.free, True))

    def generate(self, mode: str) -> dict:
        if mode in ("bonus", "superbonus"):
            scatter_count = T.SUPER_BUY_SCATTERS if mode == "superbonus" else T.BASE_TRIGGER_SCATTERS
            board = self.source.trigger_board(scatter_count)
            self.play_spin("base", "basegame", 0, board=board, no_steal=True)
            self.emit("setTotalWin", amount=0)
            self.free_spins(mode, scatter_positions(board))
        else:
            _, _, board = self.play_spin(mode, "basegame", 0)
            self.emit("setTotalWin", amount=self.total)
            scatters = scatter_positions(board)
            if len(scatters) >= T.BASE_TRIGGER_SCATTERS and self.total < T.MAX_WIN_AMOUNT:
                self.free_spins("bonus", scatters)
        self.emit("finalWin", amount=self.total)
        return {"payoutMultiplier": self.total, "events": self.events, "baseGameWins": self.base,
                "freeGameWins": self.free, "steals": self.steals,
                "maxHeatLevel": self.max_heat_level, "triggered": self.triggered}


def accepts(mode: str, criteria: str, result: dict) -> bool:
    payout = result["payoutMultiplier"]
    if criteria == "wincap":
        return payout == T.MAX_WIN_AMOUNT
    if mode in ("base", "ante"):
        if criteria == "0":
            return payout == 0 and not result["triggered"]
        if criteria == "basegame":
            return 0 < payout < T.MAX_WIN_AMOUNT and not result["triggered"]
        if criteria == "freegame":
            return 0 < payout < T.MAX_WIN_AMOUNT and result["triggered"] and result["steals"] > 0
    if mode == "superspin":
        if criteria == "under10":
            return payout < 10 * T.BOOK_SCALE
        if criteria == "10to100":
            return 10 * T.BOOK_SCALE <= payout < 100 * T.BOOK_SCALE
        if criteria == "100plus":
            return 100 * T.BOOK_SCALE <= payout < T.MAX_WIN_AMOUNT
    return criteria in ("ordinary", "hot") and payout < T.MAX_WIN_AMOUNT


def generate_candidate(mode: str, criteria: str, seed: int, max_attempts: int = 20_000) -> dict:
    for attempt in range(max_attempts):
        rng = random.Random((seed + 1) * 1_000_003 + attempt * 97_409)
        source = ProposalSource(rng, mode, criteria)
        try:
            result = Round(source).generate(mode)
        except CandidateRejected:
            continue
        if accepts(mode, criteria, result):
            return result
    raise RuntimeError(f"Could not generate {mode}/{criteria} candidate after {max_attempts} attempts")
