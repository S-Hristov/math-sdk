from fractions import Fraction
import unittest

from games.rogue_bandit import math_targets as T
from games.rogue_bandit.rogue_bandit_math import (
    apply_steal,
    component,
    evaluate_clusters,
    find_steals,
    generate_candidate,
)


class RogueBanditMathTests(unittest.TestCase):
    def test_targets_and_paytable_are_monotone(self):
        T.check_targets()
        self.assertEqual(set(T.MODE_RTPS.values()), {T.TARGET_RTP})
        self.assertEqual(T.TARGET_RTP, Fraction(24, 25))
        prior = None
        for symbol in T.SYMBOLS:
            values = T.PAYTABLE[symbol]
            self.assertEqual(tuple(sorted(values)), values)
            if prior is not None:
                self.assertTrue(all(a >= b for a, b in zip(prior, values)))
            prior = values

    def test_cluster_is_orthogonal_and_scatter_never_pays(self):
        board = [[T.SYMBOLS[(col * 3 + row) % len(T.SYMBOLS)] for row in range(T.ROWS + 2)]
                 for col in range(T.COLS)]
        cells = ((1, 2), (1, 3), (1, 4), (2, 4), (3, 4))
        for col, row in cells:
            board[col][row] = "H1"
        board[5][8] = T.SCATTER
        wins = evaluate_clusters(board)
        self.assertTrue(any(win.symbol == "H1" and set(cells).issubset(win.cells) for win in wins))
        self.assertFalse(any(win.symbol == T.SCATTER for win in wins))

    def test_every_steal_completes_target_cluster_without_moving_scatter(self):
        board = [[T.SYMBOLS[(col * 3 + row) % len(T.SYMBOLS)] for row in range(T.ROWS + 2)]
                 for col in range(T.COLS)]
        target = (2, 4)
        board[target[0]][target[1]] = "H3"
        for cell in ((2, 3), (1, 3), (1, 4), (1, 5), (5, 8)):
            board[cell[0]][cell[1]] = "L1"
        scatter = (0, 1)
        board[scatter[0]][scatter[1]] = T.SCATTER
        candidates = [steal for steal in find_steals(board) if steal.target == target and steal.symbol == "L1"]
        self.assertTrue(candidates)
        apply_steal(board, candidates[0])
        self.assertGreaterEqual(len(component(board, target, "L1")), T.MIN_CLUSTER)
        self.assertEqual(board[scatter[0]][scatter[1]], T.SCATTER)

    def test_generation_is_seed_deterministic(self):
        first = generate_candidate("superspin", "10to100", 20261002)
        second = generate_candidate("superspin", "10to100", 20261002)
        self.assertEqual(first, second)

    def test_event_money_and_terminal_contract(self):
        result = generate_candidate("bonus", "ordinary", 77)
        self.assertEqual(result["events"][-1], {
            "index": len(result["events"]) - 1,
            "type": "finalWin",
            "amount": result["payoutMultiplier"],
        })
        for event in result["events"]:
            if event["type"] == "winInfo":
                self.assertEqual(event["totalWin"], sum(win["win"] for win in event["wins"]))


if __name__ == "__main__":
    unittest.main()
