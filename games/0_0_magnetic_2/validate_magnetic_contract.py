"""Deterministic Magnetic math contract checks."""

import random
from pathlib import Path

from magnetic_math import (
    MYSTERY_BONUS_WEIGHTS,
    MODE_SETTINGS,
    apply_polarity_shift,
    build_bonus_sequence,
    eligible_wild_keys,
    generate_round_for_mode,
    get_scatter_positions,
    make_magnet,
    make_pay_symbol,
    make_polarity,
    make_scatter,
    merge_touching_clusters,
    pos,
    pos_key,
    reconcile_series_components,
    render_series_wins,
    resolve_magnet_sequence,
    suppress_non_target_visual_clusters,
    visual_cluster_symbols,
    wild_qualifies_for_cluster,
)


def _series(series_id: str, x: int, multiplier: int) -> dict:
    position = pos(x, 0)
    return {
        'id': series_id,
        'symbol': 'L4',
        'kind': 'super',
        'anchorPositions': [position],
        'lockedPositions': [position],
        'multiplier': multiplier,
        'persistent': True,
    }


# No hidden per-mode pay alteration may exist.
assert all('payout_scale' not in settings for settings in MODE_SETTINGS.values())
assert 'payout_scale' not in Path(__file__).with_name('magnetic_math.py').read_text()

# If existing clusters become one connected component, every multiplier survives.
connected = reconcile_series_components(
    [_series('super-1', 0, 2), _series('super-2', 1, 3)],
    [[pos(0, 0), pos(1, 0)]],
    'super',
    1,
    True,
    False,
    'L4',
)
assert len(connected) == 1
assert connected[0]['multiplier'] == 6

# A later touching 3x compounds exactly: 2x * 3x * 3x = 18x.
merged = merge_touching_clusters(connected + [_series('super-3', 2, 3)])
assert len(merged) == 1
assert merged[0]['multiplier'] == 18

# L4, 45 cells uses the 33-49 paytable band: 250x * 18x = 4500x.
positions = [pos(reel, row) for reel in range(7) for row in range(7)][:45]
merged[0]['anchorPositions'] = [pos(0, 0), pos(1, 0), pos(2, 0)]
merged[0]['lockedPositions'] = positions
wins = render_series_wins(merged, 1, 'super')
assert len(wins) == 1
assert wins[0]['meta']['baseAmount'] == 25_000
assert wins[0]['meta']['totalMultiplier'] == 18
assert wins[0]['amount'] == 450_000


def _board(fill: str = 'H1') -> list[list[dict]]:
    return [[make_pay_symbol(fill) for _ in range(7)] for _ in range(7)]


# Diagonal contact is not contact.  The wild also lacks four L4 supports.
diagonal_board = _board()
diagonal_board[1][1] = make_magnet()
diagonal_board[2][1] = make_pay_symbol('L4')
existing_keys = {pos_key(pos(0, 0))}
assert not wild_qualifies_for_cluster(diagonal_board, pos(1, 1), 'L4', existing_keys)
assert pos_key(pos(1, 1)) not in eligible_wild_keys(diagonal_board, 'L4', existing_keys)

# Horizontal contact joins immediately.
touching_board = _board()
touching_board[1][0] = make_magnet()
assert wild_qualifies_for_cluster(touching_board, pos(1, 0), 'L4', existing_keys)

# No existing cluster: WILD + four orthogonally connected L4 symbols seeds one.
seed_board = _board()
seed_board[3][3] = make_magnet()
for support in (pos(2, 3), pos(1, 3), pos(4, 3), pos(5, 3)):
    seed_board[support['reel']][support['row']] = make_pay_symbol('L4')
assert wild_qualifies_for_cluster(seed_board, pos(3, 3), 'L4', set())

# Regression from the supplied round: an isolated SUPER wild with only one L4
# may not activate, highlight, lock, or create a two-cell carry cluster.
carry_positions = [pos(0, 2), pos(0, 3), pos(1, 3), pos(0, 4), pos(1, 4)]
carry = [{
    'id': 'super-1',
    'symbol': 'L4',
    'kind': 'super',
    'anchorPositions': [pos(0, 2)],
    'lockedPositions': carry_positions,
    'multiplier': 1,
    'persistent': True,
}]
isolated_board = _board()
isolated_board[2][1] = make_magnet()
isolated_board[1][1] = make_pay_symbol('L4')
isolated = resolve_magnet_sequence(
    random.Random(7), isolated_board, 'SUPER', 'freegame',
    target_symbol='L4', persistent=True, carry_series=carry,
)
assert not any(event['type'] == 'magnetActivated' for event in isolated['events'])
assert len(isolated['series']) == 1
assert {pos_key(p) for p in isolated['series'][0]['lockedPositions']} == {pos_key(p) for p in carry_positions}

# Every FEATURE outcome has a paying cluster. Both natural and magnet-caused
# variants must occur across deterministic seeds.
feature_causes = set()
for seed in range(200):
    feature = generate_round_for_mode('FEATURE', seed)
    resolved = [event for event in feature['events'] if event['type'] == 'clusterSeriesResolved']
    assert resolved, ('feature missing cluster', seed)
    assert all(len(event['positions']) >= 5 and event['amount'] > 0 for event in resolved)
    feature_causes.add(
        'magnet' if any(event['type'] == 'magnetActivated' for event in feature['events']) else 'natural'
    )
assert feature_causes == {'magnet', 'natural'}

# Orthogonally touching SUPER wild does activate and join the carry cluster.
joined_board = _board()
joined_board[1][2] = make_magnet(3)
joined = resolve_magnet_sequence(
    random.Random(7), joined_board, 'SUPER', 'freegame',
    target_symbol='L4', persistent=True, carry_series=carry,
)
assert any(event['type'] == 'magnetActivated' for event in joined['events'])
assert pos_key(pos(1, 2)) in {pos_key(p) for entry in joined['series'] for p in entry['lockedPositions']}

# Regression: a second SUPER WILD absorbed into the existing cluster must still
# pull a visible target from elsewhere on the board to the cluster edge.
pull_board = _board()
for position in carry_positions:
    pull_board[position['reel']][position['row']] = make_pay_symbol('L4')
pull_board[0][2] = {'name': 'WILD', 'wild': True}
pull_board[1][2] = make_magnet()
remote_target = pos(6, 0)
pull_board[remote_target['reel']][remote_target['row']] = make_pay_symbol('L4')
pulled = resolve_magnet_sequence(
    random.Random(11), pull_board, 'SUPER', 'freegame',
    target_symbol='L4', persistent=True, carry_series=carry,
)
assert any(event['type'] == 'magnetActivated' for event in pulled['events'])
assert pull_board[remote_target['reel']][remote_target['row']]['name'] == 'L4'
assert pulled['board'][remote_target['reel']][remote_target['row']]['name'] != 'L4'
assert max(len(entry['lockedPositions']) for entry in pulled['series']) >= len(carry_positions) + 2

# Regression: when Polarity and a carried Magnet fire in the same spin, the
# subsequent magnet activation must use the Magnet's post-shift cell. Reusing
# its old coordinate turns the ordinary replacement symbol into a fake Magnet.
combo_positions = [pos(2, 2), pos(2, 3), pos(3, 3), pos(3, 4), pos(4, 4)]
combo_magnet = pos(3, 3)
combo_board = _board('L1')
for position in combo_positions:
    combo_board[position['reel']][position['row']] = make_pay_symbol('L4')
combo_board[combo_magnet['reel']][combo_magnet['row']] = make_magnet(3)
combo_board[6][6] = make_polarity()
combo_carry = [{
    'id': 'super-combo',
    'symbol': 'L4',
    'kind': 'super',
    'anchorPositions': [combo_magnet],
    'lockedPositions': combo_positions,
    'multiplier': 3,
    'persistent': True,
}]
combo = resolve_magnet_sequence(
    random.Random(19), combo_board, 'SUPER', 'freegame',
    target_symbol='L4', persistent=True, carry_series=combo_carry,
)
combo_shift = next(event for event in combo['events'] if event['type'] == 'polarityShift')
combo_activation = next(event for event in combo['events'] if event['type'] == 'magnetActivated')
shifted_magnet_keys = {
    f'{reel}:{row}'
    for reel, column in enumerate(combo_shift['board'])
    for row, cell in enumerate(column)
    if cell.get('magnet')
}
activated_magnet_keys = {pos_key(position) for position in combo_activation['positions']}
assert shifted_magnet_keys
assert activated_magnet_keys == shifted_magnet_keys
assert pos_key(combo_magnet) not in activated_magnet_keys

# ONE ACTIVE SYMBOL PER ROUND.  Every win in a single winInfo must name the same symbol.
# Multiple clusters of that symbol may each pay; a second symbol never may.  Non-target
# 'side-N' wins used to break this.
one_symbol_failures = []
for check_mode in ('BASE', 'CHANCE', 'FEATURE', 'BONUS', 'MYSTERY', 'SUPER'):
    for check_seed in range(300):
        for event in generate_round_for_mode(check_mode, check_seed)['events']:
            if event['type'] != 'winInfo':
                continue
            paid_symbols = {win['symbol'] for win in event['wins']}
            if len(paid_symbols) > 1:
                one_symbol_failures.append((check_mode, check_seed, sorted(paid_symbols)))
            if any(win['seriesId'].startswith('side') for win in event['wins']):
                one_symbol_failures.append((check_mode, check_seed, 'side win emitted'))
assert not one_symbol_failures, one_symbol_failures[:5]

# Every winInfo position must hold the symbol it is paid as, on the board that is on screen
# when the event fires.  Side wins used to be snapshotted before the respin loop and emitted
# after it, so they paid and highlighted clusters respin_board had already re-rolled — the
# frontend drew a chain across whatever symbols occupied those cells.  Replays the client's
# own view: reveal boards, with locked series positions stamped as the client stamps them.
def _replay_win_positions(mode: str, seeds: range) -> list[str]:
    failures = []
    for seed in seeds:
        board = None
        for event in generate_round_for_mode(mode, seed)['events']:
            kind = event['type']
            if kind == 'reveal':
                board = event['board']
            elif kind == 'polarityShift':
                board = event['board']
            elif kind in ('clusterSeriesUpdate', 'superSeriesCarry'):
                entries = event.get('series') or []
                if isinstance(entries, dict):
                    entries = [entries]
                for entry in entries:
                    for position in entry.get('lockedPositions', []):
                        cell = board[position['reel']][position['row']]
                        if cell['name'] != 'WILD':
                            cell['name'] = entry['symbol']
            elif kind == 'winInfo' and board is not None:
                for win in event['wins']:
                    for position in win['positions']:
                        name = board[position['reel']][position['row']]['name']
                        if name not in (win['symbol'], 'WILD'):
                            failures.append(
                                f"{mode} seed {seed}: {win['seriesId']} pays {win['symbol']} "
                                f"at {position['reel']},{position['row']} holding {name}"
                            )
    return failures


win_position_failures = [
    failure
    for mode in ('BASE', 'BONUS', 'MYSTERY', 'SUPER', 'FEATURE')
    for failure in _replay_win_positions(mode, range(300))
]
assert not win_position_failures, win_position_failures[:5]

# Event 62871 CHANCE regression: on free spin 9 the selected H3 was the only symbol allowed to
# look cluster-capable, but the reveal visibly contained losing L1 and L4 clusters. Suppression
# must preserve every H3 while breaking both misleading shapes.
event_62871_spin_9_names = [
    ['L3', 'L4', 'L2', 'L4', 'H2', 'L4', 'L3'],
    ['H4', 'L1', 'L3', 'H3', 'L4', 'L4', 'H2'],
    ['L4', 'L4', 'H3', 'H4', 'H2', 'L1', 'H4'],
    ['L4', 'L4', 'L1', 'H1', 'L4', 'H1', 'L4'],
    ['H4', 'L4', 'L1', 'L1', 'L1', 'L3', 'H2'],
    ['H2', 'L4', 'H1', 'H4', 'L1', 'H2', 'L2'],
    ['H4', 'L1', 'L2', 'H3', 'H2', 'H1', 'L3'],
]
event_62871_spin_9 = [
    [make_pay_symbol(symbol) for symbol in reel]
    for reel in event_62871_spin_9_names
]
assert visual_cluster_symbols(event_62871_spin_9) == {'L1', 'L4'}
event_62871_h3 = {
    pos_key(pos(reel, row))
    for reel in range(7)
    for row in range(7)
    if event_62871_spin_9[reel][row]['name'] == 'H3'
}
event_62871_clean = suppress_non_target_visual_clusters(event_62871_spin_9, 'H3')
assert visual_cluster_symbols(event_62871_clean) <= {'H3'}
assert event_62871_h3 == {
    pos_key(pos(reel, row))
    for reel in range(7)
    for row in range(7)
    if event_62871_clean[reel][row]['name'] == 'H3'
}

# Generated reveals may visually contain clusters for at most one regular symbol. When a magnet
# target is selected in that reveal segment, that one symbol must be the selected target.
visual_failures = []
for check_mode in ('BASE', 'CHANCE', 'FEATURE', 'BONUS', 'MYSTERY', 'SUPER'):
    for check_seed in range(300):
        events = generate_round_for_mode(check_mode, check_seed)['events']
        reveal_indices = [index for index, event in enumerate(events) if event['type'] == 'reveal']
        for reveal_number, event_index in enumerate(reveal_indices):
            event = events[event_index]
            end = (
                reveal_indices[reveal_number + 1]
                if reveal_number + 1 < len(reveal_indices)
                else len(events)
            )
            segment = events[event_index + 1 : end]
            selected = next(
                (
                    candidate['symbol']
                    for candidate in segment
                    if candidate['type'] == 'magnetTargetSelected'
                ),
                None,
            )
            visible = visual_cluster_symbols(event['board'])
            if len(visible) > 1 or (selected is not None and not visible <= {selected}):
                visual_failures.append(
                    (check_mode, check_seed, event['index'], selected, sorted(visible))
                )
assert not visual_failures, visual_failures[:5]

# A base trigger may also resolve a natural/magnetic cluster before the bonus starts. Every
# respin must keep the original scatters visible: freeSpinTrigger positions are animated against
# the latest reveal, not the first reveal. Replacing them during the cluster sequence made the UI
# appear to award a bonus without scatters and highlight three/four random regular symbols.
trigger_visibility_failures = []
scatter_collection_failures = []
collected_trigger_examples = {
    (mode, criteria): 0
    for mode in ('BASE', 'CHANCE')
    for criteria in ('bonus', 'super', 'hidden')
}
for check_mode in ('BASE', 'CHANCE'):
    for criteria, expected_count in (('bonus', 3), ('super', 4), ('hidden', 5)):
        for check_seed in range(200):
            latest_board = None
            events = generate_round_for_mode(check_mode, check_seed, criteria)['events']
            previous_scatter_keys = None
            initial_scatter_count = None
            active_cluster = False
            for event in events:
                if event['type'] == 'clusterSeriesUpdate':
                    active_cluster = bool(event.get('series'))
                    continue
                if event['type'] == 'reveal' and event.get('gameType') == 'basegame':
                    latest_board = event['board']
                    scatter_keys = {
                        pos_key(position)
                        for position in get_scatter_positions(latest_board)
                    }
                    if initial_scatter_count is None:
                        initial_scatter_count = len(scatter_keys)
                    elif previous_scatter_keys is not None:
                        added = scatter_keys - previous_scatter_keys
                        if (
                            not previous_scatter_keys <= scatter_keys
                            or len(added) > 1
                            or (added and not active_cluster)
                        ):
                            scatter_collection_failures.append(
                                (
                                    check_mode,
                                    criteria,
                                    check_seed,
                                    sorted(previous_scatter_keys),
                                    sorted(scatter_keys),
                                    active_cluster,
                                )
                            )
                    previous_scatter_keys = scatter_keys
                    continue
                if event['type'] != 'freeSpinTrigger' or event['totalFs'] <= 1:
                    continue
                trigger_positions = event['positions']
                visible_scatter_positions = get_scatter_positions(latest_board)
                if (
                    len(trigger_positions) not in (3, 4, 5)
                    or {pos_key(position) for position in trigger_positions}
                    != {pos_key(position) for position in visible_scatter_positions}
                ):
                    trigger_visibility_failures.append(
                        (
                            check_mode,
                            criteria,
                            check_seed,
                            trigger_positions,
                            visible_scatter_positions,
                        )
                    )
                if initial_scatter_count is not None and initial_scatter_count < len(trigger_positions):
                    collected_trigger_examples[(check_mode, criteria)] += 1
                break
assert not trigger_visibility_failures, trigger_visibility_failures[:5]
assert not scatter_collection_failures, scatter_collection_failures[:5]
assert all(count > 0 for count in collected_trigger_examples.values()), collected_trigger_examples

# Polarity Shifter: cluster + loose matches pack against the selected wall.
polarity_board = _board('L1')
polarity_positions = [pos(2, 2), pos(2, 3), pos(3, 3), pos(3, 4), pos(4, 4)]
for position in polarity_positions:
    polarity_board[position['reel']][position['row']] = make_pay_symbol('H1')
magnet_position = polarity_positions[0]
polarity_board[magnet_position['reel']][magnet_position['row']] = make_magnet(2)
polarity_board[6][6] = make_pay_symbol('H1')
polarity_board[5][1] = make_polarity()
scatter_position = pos(1, 3)
polarity_board[scatter_position['reel']][scatter_position['row']] = make_scatter()
polarity_series = [{
    'id': 'natural-1',
    'symbol': 'H1',
    'kind': 'natural',
    'anchorPositions': polarity_positions,
    'lockedPositions': polarity_positions,
    'multiplier': 1,
    'persistent': False,
}]
for polarity_direction in ('LEFT', 'RIGHT', 'UP', 'DOWN'):
    shifted_board, shifted_series, moves = apply_polarity_shift(
        polarity_board, polarity_series, 'H1', polarity_direction
    )
    assert moves, polarity_direction
    # Scatter and the firing shifter do not move during the slam. The shifter is
    # consumed after it fires and does not become part of the cluster.
    assert shifted_board[scatter_position['reel']][scatter_position['row']]['name'] == 'SCATTER'
    assert not any(cell.get('polarity') for reel in shifted_board for cell in reel)
    assert all(
        position not in shifted_series[0]['lockedPositions']
        for position in [pos(5, 1)]
    )
    # Existing matching symbols and the cluster magnet are relocated, not copied.
    before_targets = sum(cell['name'] == 'H1' for reel in polarity_board for cell in reel)
    after_targets = sum(cell['name'] == 'H1' for reel in shifted_board for cell in reel)
    assert before_targets == after_targets, polarity_direction
    assert sum(bool(cell.get('magnet')) for reel in shifted_board for cell in reel) == 1
    # Every symbol stays in its own lane. This is the invariant the old wall
    # packing broke, and the reason clusters looked randomly relocated.
    for move in moves:
        if polarity_direction in ('LEFT', 'RIGHT'):
            assert move['from']['row'] == move['to']['row'], (polarity_direction, move)
        else:
            assert move['from']['reel'] == move['to']['reel'], (polarity_direction, move)
    # Every original cluster cell participates in the wall pack. The magnet moves
    # with it and remains a Wild cluster cell at its exact destination.
    cluster_moves = [move for move in moves if move['kind'] == 'cluster']
    moved_cluster_sources = {pos_key(move['from']) for move in cluster_moves}
    stationary_cluster = {
        pos_key(position)
        for position in polarity_positions
        if position in shifted_series[0]['lockedPositions']
    }
    assert moved_cluster_sources | stationary_cluster == {
        pos_key(position) for position in polarity_positions
    }, polarity_direction
    magnet_move = next(move for move in cluster_moves if move['from'] == magnet_position)
    moved_magnet = shifted_board[magnet_move['to']['reel']][magnet_move['to']['row']]
    assert moved_magnet.get('magnet') and moved_magnet.get('wild'), polarity_direction
    assert magnet_move['to'] in shifted_series[0]['lockedPositions'], polarity_direction

    # Active symbols occupy the wall-most available slots in each obstacle-bounded lane.
    lanes = (
        [[pos(reel, row) for reel in range(7)] for row in range(7)]
        if polarity_direction == 'LEFT'
        else [[pos(reel, row) for reel in reversed(range(7))] for row in range(7)]
        if polarity_direction == 'RIGHT'
        else [[pos(reel, row) for row in range(7)] for reel in range(7)]
        if polarity_direction == 'UP'
        else [[pos(reel, row) for row in reversed(range(7))] for reel in range(7)]
    )
    for lane in lanes:
        segment = []
        for position in lane + [None]:
            is_blocker = position is None or polarity_board[position['reel']][position['row']].get('scatter') or polarity_board[position['reel']][position['row']].get('polarity')
            if not is_blocker:
                segment.append(position)
                continue
            if segment:
                active_count = sum(
                    bool(
                        polarity_board[cell['reel']][cell['row']]['name'] == 'H1'
                        or polarity_board[cell['reel']][cell['row']].get('magnet')
                    )
                    for cell in segment
                )
                packed = [
                    bool(
                        shifted_board[cell['reel']][cell['row']]['name'] == 'H1'
                        or shifted_board[cell['reel']][cell['row']].get('magnet')
                    )
                    for cell in segment
                ]
                assert packed == [True] * active_count + [False] * (len(segment) - active_count), (polarity_direction, segment, packed)
                segment = []
    # Every original locked cell remains locked. Obstacles may divide wall lanes,
    # but they cannot silently remove an already established cluster member.
    locked = shifted_series[0]['lockedPositions']
    assert len(locked) >= len(polarity_positions), (polarity_direction, len(locked))
    for position in locked:
        cell = shifted_board[position['reel']][position['row']]
        assert cell['name'] == 'H1' or cell.get('wild'), (polarity_direction, position, cell)

# Zero Point Protocol: exactly five trigger scatters and a multiplier magnet on spin one.
hidden_round = generate_round_for_mode('BASE', 9901, 'hidden')
hidden_trigger = next(event for event in hidden_round['events'] if event['type'] == 'freeSpinTrigger')
assert len(hidden_trigger['positions']) == 5
first_hidden_reveal = next(
    event for event in hidden_round['events']
    if event['type'] == 'reveal' and event.get('gameType') == 'hidden'
)
hidden_magnets = [cell for reel in first_hidden_reveal['board'] for cell in reel if cell.get('magnet')]
assert hidden_magnets and int(hidden_magnets[0].get('multiplier', 1)) > 1

# Persistent bonus growth is informational; settlement events occur once, after
# the last free spin, for both SUPER and HIDDEN.
for persistent_mode in ('SUPER', 'HIDDEN'):
    persistent_round = build_bonus_sequence(random.Random(7741), persistent_mode, [], 0, False)
    persistent_events = persistent_round['events']
    last_spin_index = max(
        index for index, event in enumerate(persistent_events)
        if event['type'] == 'updateFreeSpin'
    )
    set_total_indexes = [
        index for index, event in enumerate(persistent_events)
        if event['type'] == 'setTotalWin'
    ]
    set_win_indexes = [
        index for index, event in enumerate(persistent_events)
        if event['type'] == 'setWin'
    ]
    assert len(set_total_indexes) == 1 and set_total_indexes[0] > last_spin_index, persistent_mode
    assert len(set_win_indexes) <= 1 and all(index > last_spin_index for index in set_win_indexes), persistent_mode

# Mothership Protocol selection must use the declared 70/25/5 weights.
mystery_counts = {'BONUS': 0, 'SUPER': 0, 'HIDDEN': 0}
for seed in range(1000):
    mystery_counts[generate_round_for_mode('MYSTERY', seed)['mystery_mode']] += 1
assert 640 <= mystery_counts['BONUS'] <= 760, mystery_counts
assert 190 <= mystery_counts['SUPER'] <= 310, mystery_counts
assert 25 <= mystery_counts['HIDDEN'] <= 85, mystery_counts

print('magnetic 2 math contract: PASS (Magnetic 1 regressions + Polarity wall slam + end-only Super payout + 5-scatter Zero Point multiplier start + 70/25/5 Mothership Protocol)')
