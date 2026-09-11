"""Streaming validation for published Magnetic books and lookups."""

from __future__ import annotations

import io
import json
from pathlib import Path

import zstandard as zstd

from math_targets import (
    BONUS_TIER_MEANS,
    BOUGHT_MODE_FOR_TIER,
    MODE_COSTS,
    MYSTERY_MIX,
    MYSTERY_TIER_MEANS,
)
from magnetic_math import visual_cluster_symbols

ROOT = Path(__file__).parent / 'library' / 'publish_files'
EXPECTED_ROWS = 500_000
MAX_PAYOUT = 2_000_000  # 20,000x in 0.01x units


def key(position: dict) -> tuple[int, int]:
    return int(position['reel']), int(position['row'])


def connected(positions: list[dict]) -> bool:
    keys = {key(position) for position in positions}
    if not keys:
        return False
    seen = {next(iter(keys))}
    stack = list(seen)
    while stack:
        reel, row = stack.pop()
        for neighbor in ((reel - 1, row), (reel + 1, row), (reel, row - 1), (reel, row + 1)):
            if neighbor in keys and neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    return seen == keys


def load_lookup(mode: str) -> dict[int, tuple[int, int]]:
    rows: dict[int, tuple[int, int]] = {}
    path = ROOT / f'lookUpTable_{mode}_0.csv'
    with path.open() as file:
        for line in file:
            book_id, weight, payout = map(int, line.rstrip().split(','))
            assert book_id not in rows, (mode, 'duplicate lookup id', book_id)
            assert weight >= 0, (mode, book_id, 'negative weight')
            rows[book_id] = (weight, payout)
    return rows


def validate_mode(mode: str) -> dict[str, float]:
    lookup = load_lookup(mode)
    seen_ids: set[int] = set()
    weighted_payout = 0
    total_weight = 0
    activated = 0
    snapshots = 0
    feature_magnet_books = 0
    feature_natural_books = 0
    tier_weight: dict[str, int] = {}
    tier_payout: dict[str, int] = {}
    criteria_weight: dict[str, int] = {}
    criteria_payout: dict[str, int] = {}
    path = ROOT / f'books_{mode}.jsonl.zst'
    with path.open('rb') as compressed:
        with zstd.ZstdDecompressor().stream_reader(compressed) as reader:
            with io.TextIOWrapper(reader, encoding='utf-8') as text:
                for line_number, line in enumerate(text, start=1):
                    book = json.loads(line)
                    book_id = int(book['id'])
                    payout = int(book['payoutMultiplier'])
                    assert book_id not in seen_ids, (mode, 'duplicate book id', book_id)
                    assert book_id in lookup, (mode, 'missing lookup id', book_id)
                    weight, lookup_payout = lookup[book_id]
                    assert payout == lookup_payout, (mode, book_id, payout, lookup_payout)
                    assert 0 <= payout <= MAX_PAYOUT, (mode, book_id, payout)
                    seen_ids.add(book_id)
                    total_weight += weight
                    weighted_payout += payout * weight
                    criteria = str(book.get('criteria', ''))
                    if criteria in BONUS_TIER_MEANS:
                        criteria_weight[criteria] = criteria_weight.get(criteria, 0) + weight
                        criteria_payout[criteria] = criteria_payout.get(criteria, 0) + payout * weight

                    current_series: list[dict] = []
                    pending_activation: set[tuple[int, int]] = set()
                    previous_base_scatters: set[tuple[int, int]] | None = None
                    active_base_cluster = False
                    base_trigger_seen = False
                    events = book.get('events', [])
                    assert all(int(event.get('index', idx)) == idx for idx, event in enumerate(events)), (mode, book_id, 'event index gap')
                    reveal_indices = [
                        index for index, event in enumerate(events)
                        if event.get('type') == 'reveal'
                    ]
                    for reveal_number, reveal_index in enumerate(reveal_indices):
                        reveal = events[reveal_index]
                        visible = visual_cluster_symbols(reveal.get('board', []))
                        assert len(visible) <= 1, (
                            mode,
                            book_id,
                            reveal.get('index'),
                            'multiple visible cluster symbols',
                            sorted(visible),
                        )

                        previous_reveal = (
                            reveal_indices[reveal_number - 1]
                            if reveal_number > 0 else -1
                        )
                        next_reveal = (
                            reveal_indices[reveal_number + 1]
                            if reveal_number + 1 < len(reveal_indices) else len(events)
                        )
                        before = events[previous_reveal + 1 : reveal_index]
                        after = events[reveal_index + 1 : next_reveal]
                        selected = next(
                            (
                                str(event['symbol'])
                                for event in after
                                if event.get('type') == 'magnetTargetSelected'
                            ),
                            None,
                        )
                        if selected is None:
                            selected = next(
                                (
                                    str(event['magnetTargetSymbol'])
                                    for event in reversed(before)
                                    if event.get('type') == 'superSeriesCarry'
                                    and event.get('magnetTargetSymbol')
                                ),
                                None,
                            )
                        assert selected is None or visible <= {selected}, (
                            mode,
                            book_id,
                            reveal.get('index'),
                            'non-target visible cluster',
                            selected,
                            sorted(visible),
                        )
                    board_before_event: list[list[dict]] | None = None
                    for event in events:
                        event_type = event.get('type')
                        if event_type == 'polarityShift':
                            # The slam is one axis, one lane per symbol, and a pure
                            # permutation of the board. A move that changes both reel
                            # and row is the wall-packing regression.
                            direction = event.get('direction')
                            assert direction in ('LEFT', 'RIGHT', 'UP', 'DOWN'), (
                                mode, book_id, 'bad polarity direction', direction
                            )
                            for move in event.get('moves', []):
                                if direction in ('LEFT', 'RIGHT'):
                                    assert move['from']['row'] == move['to']['row'], (
                                        mode, book_id, 'polarity move changed row', move
                                    )
                                else:
                                    assert move['from']['reel'] == move['to']['reel'], (
                                        mode, book_id, 'polarity move changed reel', move
                                    )
                            cluster_offsets = {
                                (
                                    move['to']['reel'] - move['from']['reel'],
                                    move['to']['row'] - move['from']['row'],
                                )
                                for move in event.get('moves', [])
                                if move.get('kind') == 'cluster'
                            }
                            assert len(cluster_offsets) <= 1, (
                                mode, book_id, 'cluster torn apart by slam', cluster_offsets
                            )
                            if board_before_event is not None:
                                counts_before = sorted(
                                    cell['name'] for column in board_before_event for cell in column
                                )
                                counts_after = sorted(
                                    cell['name'] for column in event.get('board', []) for cell in column
                                )
                                assert counts_before == counts_after, (
                                    mode, book_id, 'polarity shift changed symbol counts'
                                )
                        if event_type in ('reveal', 'polarityShift'):
                            board_before_event = event.get('board')
                        if event_type == 'mysteryBonusReveal':
                            tier = str(event.get('mode', ''))
                            assert tier in MYSTERY_MIX, (mode, book_id, 'bad mystery tier', tier)
                            tier_weight[tier] = tier_weight.get(tier, 0) + weight
                            tier_payout[tier] = tier_payout.get(tier, 0) + payout * weight
                        if event_type == 'reveal' and event.get('gameType') == 'basegame':
                            current_scatters = {
                                (reel, row)
                                for reel, column in enumerate(event.get('board', []))
                                for row, cell in enumerate(column)
                                if cell.get('scatter') or cell.get('name') == 'SCATTER'
                            }
                            if previous_base_scatters is not None:
                                added = current_scatters - previous_base_scatters
                                assert previous_base_scatters <= current_scatters, (
                                    mode, book_id, 'scatter unlocked during respin'
                                )
                                assert len(added) <= 1, (
                                    mode, book_id, 'multiple respin scatters', sorted(added)
                                )
                                assert not added or active_base_cluster, (
                                    mode, book_id, 'scatter added without active cluster'
                                )
                            previous_base_scatters = current_scatters
                        elif event_type == 'freeSpinTrigger' and int(event.get('totalFs', 0)) > 1:
                            trigger_keys = {key(position) for position in event.get('positions', [])}
                            assert len(trigger_keys) in (3, 4, 5), (
                                mode, book_id, 'invalid trigger scatter count', len(trigger_keys)
                            )
                            assert trigger_keys == (previous_base_scatters or set()), (
                                mode, book_id, 'trigger does not match visible scatters'
                            )
                            base_trigger_seen = True
                        elif event_type == 'magnetActivated':
                            activated += 1
                            positions = {key(position) for position in event.get('positions', [])}
                            assert positions, (mode, book_id, 'empty activation')
                            locked_now = {key(position) for series in current_series for position in series['lockedPositions']}
                            pending_activation |= positions - locked_now
                        elif event_type == 'clusterSeriesUpdate':
                            current_series = event.get('series', [])
                            active_base_cluster = bool(current_series)
                            locked_now: set[tuple[int, int]] = set()
                            for series in current_series:
                                positions = series.get('lockedPositions', [])
                                assert len(positions) >= 5, (mode, book_id, 'sub-5 series', series.get('id'), len(positions))
                                assert len({key(position) for position in positions}) == len(positions), (mode, book_id, 'duplicate position')
                                assert connected(positions), (mode, book_id, 'disconnected series', series.get('id'))
                                locked_now |= {key(position) for position in positions}
                                snapshots += 1
                            pending_activation -= locked_now
                    assert not pending_activation, (mode, book_id, 'activated wild never locked', sorted(pending_activation))
                    assert base_trigger_seen == bool(previous_base_scatters and len(previous_base_scatters) >= 3), (
                        mode, book_id, 'scatter trigger mismatch', sorted(previous_base_scatters or set())
                    )
                    if mode == 'FEATURE':
                        resolved_clusters = [
                            event for event in events
                            if event.get('type') == 'clusterSeriesResolved'
                        ]
                        assert resolved_clusters, (mode, book_id, 'feature missing guaranteed cluster')
                        assert all(
                            len(event.get('positions', [])) >= 5 and int(event.get('amount', 0)) > 0
                            for event in resolved_clusters
                        ), (mode, book_id, 'invalid guaranteed cluster')
                        if any(event.get('type') == 'magnetActivated' for event in events):
                            feature_magnet_books += 1
                        else:
                            feature_natural_books += 1
                    final_wins = [event for event in events if event.get('type') == 'finalWin']
                    assert final_wins and int(final_wins[-1]['amount']) == payout, (mode, book_id, 'final payout mismatch')
                    if line_number % 100_000 == 0:
                        print(mode, f'{line_number:,}/{EXPECTED_ROWS:,}', flush=True)

    assert len(seen_ids) == EXPECTED_ROWS, (mode, len(seen_ids))
    assert seen_ids == set(lookup), (mode, 'book/lookup id mismatch')
    if mode == 'FEATURE':
        assert feature_magnet_books > 0, (mode, 'no magnet-caused feature clusters')
        assert feature_natural_books > 0, (mode, 'no natural feature clusters')
    if mode == 'MYSTERY':
        assert set(tier_weight) == set(MYSTERY_MIX), (mode, 'missing tier', sorted(tier_weight))
        for tier, wanted_share in MYSTERY_MIX.items():
            share = tier_weight[tier] / max(total_weight, 1)
            mean = tier_payout[tier] / max(tier_weight[tier], 1) / 100
            wanted_mean = MYSTERY_TIER_MEANS[tier]
            # The reveal animation states these odds and promises the real bonus,
            # so both the share and the tier's own value are contract, not fallout.
            assert abs(share - wanted_share) < 5e-4, (mode, tier, 'share', share, wanted_share)
            assert abs(mean - wanted_mean) < wanted_mean * 0.005, (mode, tier, 'mean', mean, wanted_mean)
            print(mode, tier, f'share {share:.4f} mean {mean:.2f}x (target {wanted_mean:.2f}x)', flush=True)
    rtp = weighted_payout / max(total_weight, 1) / 100 / MODE_COSTS[mode]
    # Integer lookup weights can leave sub-ppm rounding residue. Keep this strict
    # enough to catch real RTP drift without rejecting a valid 96.10001% mode.
    assert abs(rtp - 0.961) < 1e-6, (mode, rtp)
    natural_means = {
        criteria: criteria_payout[criteria] / max(criteria_weight[criteria], 1) / 100
        for criteria in criteria_weight
    }
    for criteria, mean in sorted(natural_means.items()):
        wanted = BONUS_TIER_MEANS[criteria]
        # A natural trigger has to be worth the same as the bought bonus, so this
        # is a contract on the group and not a by-product of the mode-wide tilt.
        assert abs(mean - wanted) < wanted * 0.01, (mode, criteria, 'natural mean', mean, wanted)
        print(mode, f'natural {criteria}: {mean:.2f}x (target {wanted:.2f}x)', flush=True)
    print(mode, 'PASS', {'rtp': rtp, 'activations': activated, 'series_snapshots': snapshots}, flush=True)
    return {
        'rtp': rtp,
        'activations': activated,
        'series_snapshots': snapshots,
        'natural_means': natural_means,
        'mystery_tier_means': {
            tier: tier_payout[tier] / max(tier_weight[tier], 1) / 100
            for tier in tier_weight
        },
    }


def assert_natural_matches_bought(results: dict[str, dict]) -> None:
    """Every route to a bonus must pay the same on average.

    Three routes exist per tier: a natural scatter trigger inside BASE/CHANCE, an
    outright buy, and a Mothership Protocol roll. If they drift apart the buy
    prices stop being honest and feature-hunting becomes mispriced by accident.
    """
    for tier, wanted in BONUS_TIER_MEANS.items():
        observed: dict[str, float] = {}
        for mode in ('BASE', 'CHANCE'):
            mean = results.get(mode, {}).get('natural_means', {}).get(tier)
            if mean is not None:
                observed[f'natural/{mode}'] = mean
        bought_mode = BOUGHT_MODE_FOR_TIER.get(tier)
        if bought_mode:
            observed[f'bought/{bought_mode}'] = results[bought_mode]['rtp'] * MODE_COSTS[bought_mode]
        mystery_mean = results.get('MYSTERY', {}).get('mystery_tier_means', {}).get(tier.upper())
        if mystery_mean is not None:
            observed['mystery'] = mystery_mean
        assert observed, ('no route observed for tier', tier)
        for route, mean in observed.items():
            assert abs(mean - wanted) < wanted * 0.01, ('tier parity', tier, route, mean, wanted)
        spread = max(observed.values()) - min(observed.values())
        assert spread < wanted * 0.01, ('tier parity spread', tier, observed)
        print(
            f'parity {tier}: target {wanted:.2f}x, routes '
            + ', '.join(f'{route} {mean:.2f}x' for route, mean in sorted(observed.items())),
            flush=True,
        )


if __name__ == '__main__':
    results = {mode: validate_mode(mode) for mode in MODE_COSTS}
    assert_natural_matches_bought(results)
    print('magnetic published artifacts: PASS', results)
