"""Theme Park contract and generated-artifact regression tests."""

from __future__ import annotations

import json
import os
import random
import unittest

from math_targets import (
    BASE_RATES,
    LOOKUP_SCALE,
    MODE_COSTS,
    TARGET_BASE_HIT_RATE,
    TARGET_RTP,
    TARGET_RTP_SHARES,
)
from theme_park_math import (
    DUCK_POND_SIZE,
    FSPIN1_DUCK_COUNT_DIST,
    MAX_WIN_AMOUNT,
    ROLLER_MULT_POOL,
    ROLLER_SINGLE_MULT_POOL,
    TOTAL_PICKS,
    WILD,
    build_base_round,
    evaluate_board,
    generate_forced_coverage_rounds,
    generate_round_for_mode,
    roll_coaster_setup,
    transformed_wild_board,
    no_win_board,
    _cell,
    _wild_cell,
    set_visible,
)


ROOT = os.path.dirname(__file__)
LIBRARY = os.path.join(ROOT, 'library')


class ThemeParkRoundContractTests(unittest.TestCase):
    def test_multiplier_wilds_substitute_symbols_and_five_wilds_pay(self) -> None:
        board = no_win_board()
        for reel in range(5):
            set_visible(board, reel, 0, _wild_cell(2) if reel in (0, 1, 2, 4) else _cell('L5'))

        result = evaluate_board(board)
        line = next(win for win in result['wins'] if win['meta']['lineIndex'] == 0)
        self.assertEqual(line['symbol'], 'L5')
        self.assertEqual(line['kind'], 5)
        self.assertEqual(line['win'], 800)  # 1x for five L5s, multiplied by four 2x Wilds.
        self.assertFalse(any(win['symbol'] == 'H1' for win in result['wins']))

        all_wild = no_win_board()
        for reel in range(5):
            set_visible(all_wild, reel, 0, _wild_cell(2))
        result = evaluate_board(all_wild)
        line = next(win for win in result['wins'] if win['meta']['lineIndex'] == 0)
        self.assertEqual(line['symbol'], 'H1')
        self.assertEqual(line['kind'], 5)
        self.assertEqual(line['win'], 20000)  # 20x five-Wild award, multiplied by five 2x Wilds.

    def test_all_modes_emit_valid_rounds(self) -> None:
        for mode in MODE_COSTS:
            for seed in range(50):
                with self.subTest(mode=mode, seed=seed):
                    round_data = generate_round_for_mode(mode, seed)
                    events = round_data['events']
                    self.assertTrue(events)
                    self.assertEqual([event['index'] for event in events], list(range(len(events))))
                    self.assertEqual(events[-1]['type'], 'finalWin')
                    self.assertEqual(events[-1]['amount'], round_data['final_amount'])
                    self.assertLessEqual(round_data['final_amount'], MAX_WIN_AMOUNT)
                    for event in events:
                        if event['type'] == 'reveal':
                            self.assertEqual(len(event['board']), 5)
                            self.assertTrue(all(len(reel) == 7 for reel in event['board']))

    def test_fspin1_guarantees_one_and_supports_every_board_count(self) -> None:
        self.assertEqual([count for count, weight in FSPIN1_DUCK_COUNT_DIST if weight > 0], list(range(1, 26)))
        rounds = [generate_round_for_mode('FSPIN1', seed) for seed in range(1000)]
        rounds += generate_forced_coverage_rounds('FSPIN1')
        for round_data in rounds:
            starts = [event for event in round_data['events'] if event['type'] == 'duckCollectStart']
            self.assertEqual(len(starts), 1)
            positions = starts[0]['positions']
            self.assertGreaterEqual(len(positions), 1)
            self.assertLessEqual(len(positions), 25)
            self.assertEqual(len({(position['reel'], position['row']) for position in positions}), len(positions))

    def test_duck_bonus_provides_full_pond_and_ten_picks(self) -> None:
        rounds = [generate_round_for_mode('DUCK', seed) for seed in range(100)]
        rounds += generate_forced_coverage_rounds('DUCK')
        for round_data in rounds:
            with self.subTest(book=round_data.get('id'), payout=round_data['final_amount']):
                start = next(event for event in round_data['events'] if event['type'] == 'duckPickStart')
                picks = [event for event in round_data['events'] if event['type'] == 'duckPick']
                reveal = next(event for event in round_data['events'] if event['type'] == 'reveal')
                scatter_positions = [
                    {'reel': reel_index, 'row': padded_row - 1}
                    for reel_index, reel in enumerate(reveal['board'])
                    for padded_row, cell in enumerate(reel)
                    if 1 <= padded_row <= 5 and cell.get('name') == 'S_DUCK' and cell.get('scatter')
                ]
                self.assertEqual(start['totalPicks'], TOTAL_PICKS)
                self.assertEqual(len(start['pool']), DUCK_POND_SIZE)
                self.assertEqual(len(start['positions']), 3)
                self.assertCountEqual(start['positions'], scatter_positions)
                self.assertEqual(len(picks), TOTAL_PICKS)
                self.assertEqual(
                    [(event['kind'], event['value']) for event in picks],
                    [(prize['kind'], prize['value']) for prize in start['pool'][:TOTAL_PICKS]],
                )
                self.assertEqual([event['pickIndex'] for event in picks], list(range(TOTAL_PICKS)))

    def test_scatter_features_always_use_exactly_three_scatters(self) -> None:
        for mode in ('BASE', 'ANTE'):
            for feature in ('duck', 'roller', 'coaster'):
                for seed in range(100):
                    round_data = build_base_round(
                        random.Random(seed), mode, forced_feature=feature
                    )
                    self.assertEqual(round_data['basegame_win'], 0)
                    reveal = next(
                        event for event in build_base_round(
                            random.Random(seed), mode, forced_feature=feature
                        )['events']
                        if event['type'] == 'reveal'
                    )
                    scatter_count = sum(
                        cell.get('scatter', False)
                        for reel in reveal['board']
                        for cell in reel[1:6]
                    )
                    self.assertEqual(scatter_count, 3, (mode, feature, seed))

    def test_full_reel_wild_multipliers_add(self) -> None:
        board = [[{'name': 'H1'} for _ in range(7)] for _ in range(5)]
        for row in range(1, 6):
            board[0][row] = {'name': WILD, 'wild': True, 'reelMultiplier': 5}
            board[1][row] = {'name': WILD, 'wild': True, 'reelMultiplier': 7}
        # Each complete Wild reel owns one multiplier plaque. All five cells repeat the same
        # reelMultiplier for line evaluation; multipliers from different reels still add.
        result = evaluate_board(board)
        first_line = next(win for win in result['wins'] if win['meta']['lineIndex'] == 0)
        self.assertEqual(first_line['meta']['lineMultiplier'], 12)
        self.assertEqual(first_line['win'], 20 * 100 * 12)

    def test_roller_wild_lands_then_transforms_with_one_reel_multiplier(self) -> None:
        saw_non_middle_trigger = False
        for seed in range(500):
            round_data = generate_round_for_mode('FSPIN2', seed)
            reveal = next(event for event in round_data['events'] if event['type'] == 'reveal')
            apply = next(event for event in round_data['events'] if event['type'] == 'rollerWildsApply')
            self.assertEqual(apply['index'], reveal['index'] + 1)
            for reel in apply['reels']:
                self.assertTrue(0 <= reel['reel'] < 5)
                self.assertTrue(0 <= reel['triggerRow'] < 5)
                trigger = reveal['board'][reel['reel']][reel['triggerRow'] + 1]
                self.assertTrue(trigger.get('rollerTrigger'))
                self.assertNotIn('multipliers', reel)
                self.assertIn(reel['fakeMultiplier'], {2, 3, 5, 10, 25, 50, 100})
                self.assertIn(reel['multiplier'], {2, 3, 5, 10, 25, 50, 100})
                self.assertNotEqual(reel['fakeMultiplier'], reel['multiplier'])
                saw_non_middle_trigger |= reel['triggerRow'] != 2
        self.assertTrue(saw_non_middle_trigger)

    def test_fake_plaque_value_does_not_change_payout(self) -> None:
        board = [[{'name': 'H1'} for _ in range(7)] for _ in range(5)]
        transformed = transformed_wild_board(
            board,
            [{'reel': 0, 'triggerRow': 2, 'fakeMultiplier': 100, 'multiplier': 2}],
        )
        first_line = next(
            win for win in evaluate_board(transformed)['wins'] if win['meta']['lineIndex'] == 0
        )
        self.assertEqual(first_line['meta']['lineMultiplier'], 2)

    def test_single_plaque_pool_preserves_legacy_mean_multiplier(self) -> None:
        # Legacy sparse plaques: 0 rows resolved as neutral 1x; otherwise row values added.
        legacy_count_dist = [(0, 15), (1, 72), (2, 11), (3, 1.7), (4, 0.27), (5, 0.03)]
        value_mean = sum(value * weight for value, weight in ROLLER_MULT_POOL) / sum(
            weight for _, weight in ROLLER_MULT_POOL
        )
        count_mean = sum(count * weight for count, weight in legacy_count_dist) / sum(
            weight for _, weight in legacy_count_dist
        )
        empty_rate = legacy_count_dist[0][1] / sum(weight for _, weight in legacy_count_dist)
        legacy_mean = empty_rate + count_mean * value_mean
        single_mean = sum(value * weight for value, weight in ROLLER_SINGLE_MULT_POOL) / sum(
            weight for _, weight in ROLLER_SINGLE_MULT_POOL
        )
        self.assertAlmostEqual(single_mean, legacy_mean, delta=0.01)

    def test_roller_wild_can_land_in_base_game(self) -> None:
        round_data = build_base_round(random.Random(7), 'BASE', forced_feature='base_rollerwild')
        reveal = next(event for event in round_data['events'] if event['type'] == 'reveal')
        apply = next(event for event in round_data['events'] if event['type'] == 'rollerWildsApply')
        self.assertEqual(apply['index'], reveal['index'] + 1)
        self.assertGreaterEqual(len(apply['reels']), 1)

    def test_each_coaster_duck_applies_exactly_one_doubling_step(self) -> None:
        for seed in range(500):
            pukes, tiles = roll_coaster_setup(random.Random(seed))
            steps_by_cell: dict[tuple[int, int], list[int]] = {}
            for puke in pukes:
                cell = (puke['reel'], puke['row'])
                steps = steps_by_cell.setdefault(cell, [])
                expected_multiplier = 2 ** (len(steps) + 1)
                self.assertEqual(puke['multiplier'], expected_multiplier, (seed, cell, steps))
                steps.append(puke['multiplier'])

            final_by_cell = {
                (tile['reel'], tile['row']): tile['multiplier']
                for tile in tiles
            }
            self.assertEqual(set(final_by_cell), set(steps_by_cell))
            for cell, steps in steps_by_cell.items():
                self.assertEqual(final_by_cell[cell], steps[-1])


class ThemeParkArtifactTests(unittest.TestCase):
    def test_report_and_config_are_release_consistent(self) -> None:
        report_path = os.path.join(LIBRARY, 'configs', 'simulation_report.json')
        config_path = os.path.join(LIBRARY, 'configs', 'config.json')
        with open(report_path, 'r', encoding='utf-8') as file:
            report = json.load(file)
        with open(config_path, 'r', encoding='utf-8') as file:
            config = json.load(file)
        config_modes = {entry['name']: entry for entry in config['bookShelfConfig']}

        self.assertEqual(set(report['modes']), set(MODE_COSTS))
        self.assertEqual(set(config_modes), set(MODE_COSTS))
        for mode in MODE_COSTS:
            with self.subTest(mode=mode):
                mode_report = report['modes'][mode]
                self.assertEqual(mode_report['lookup_total_weight'], LOOKUP_SCALE)
                self.assertEqual(mode_report['rows'], config_modes[mode]['bookLength'])
                self.assertAlmostEqual(mode_report['rtp'], TARGET_RTP, delta=1e-6)
                self.assertEqual(mode_report['max_x_observed'], 25000.0)

        base = report['modes']['BASE']
        self.assertLessEqual(config_modes['BASE']['std'], 50.0)
        self.assertAlmostEqual(base['hit_rate'], TARGET_BASE_HIT_RATE, delta=0.002)
        self.assertAlmostEqual(
            base['base_rtp_contribution'],
            TARGET_RTP * TARGET_RTP_SHARES['base'],
            delta=1e-9,
        )
        self.assertAlmostEqual(
            base['freespin_rtp_contribution'],
            TARGET_RTP * TARGET_RTP_SHARES['freespin'],
            delta=1e-9,
        )
        self.assertAlmostEqual(
            base['bonus_rtp_contribution'],
            TARGET_RTP * TARGET_RTP_SHARES['bonus'],
            delta=1e-9,
        )
        for criteria, rate in BASE_RATES.items():
            label = 'none' if criteria == '0' else criteria
            self.assertAlmostEqual(
                base['criteria'][label]['weighted_prob'],
                rate,
                delta=1e-6,
            )


if __name__ == '__main__':
    unittest.main()
