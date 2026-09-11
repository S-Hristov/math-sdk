"""Deterministic Magnetic math contract checks."""

import random
from pathlib import Path

from magnetic_math import (
    MODE_SETTINGS,
    eligible_wild_keys,
    generate_round_for_mode,
    get_scatter_positions,
    make_magnet,
    make_pay_symbol,
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

# ONE ACTIVE SYMBOL PER ROUND.  Every win in a single winInfo must name the same symbol.
# Multiple clusters of that symbol may each pay; a second symbol never may.  Non-target
# 'side-N' wins used to break this.
one_symbol_failures = []
for check_mode in ('BASE', 'CHANCE', 'FEATURE', 'BONUS', 'SUPER'):
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
    for mode in ('BASE', 'BONUS', 'SUPER', 'FEATURE')
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
for check_mode in ('BASE', 'CHANCE', 'FEATURE', 'BONUS', 'SUPER'):
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
    for criteria in ('bonus', 'super')
}
for check_mode in ('BASE', 'CHANCE'):
    for criteria, expected_count in (('bonus', 3), ('super', 4)):
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
                    len(trigger_positions) != expected_count
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
                if initial_scatter_count is not None and initial_scatter_count < expected_count:
                    collected_trigger_examples[(check_mode, criteria)] += 1
                break
assert not trigger_visibility_failures, trigger_visibility_failures[:5]
assert not scatter_collection_failures, scatter_collection_failures[:5]
assert all(count > 0 for count in collected_trigger_examples.values()), collected_trigger_examples

print('magnetic math contract: PASS (1-2 scatters lock and collect only on active cluster respins; trigger scatters stay visible; one visible cluster symbol; event 62871 fixed; SUPER secondary pull; FEATURE guaranteed mixed clusters; L4 45 @ 18x = 4500x; win positions match paid symbol; one paying symbol per round)')
