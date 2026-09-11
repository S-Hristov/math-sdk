"""Streaming validation for published Magnetic books and lookups."""

from __future__ import annotations

import io
import json
from pathlib import Path

import zstandard as zstd

from math_targets import MODE_COSTS
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
                    for event in events:
                        event_type = event.get('type')
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
                            assert len(trigger_keys) in (3, 4), (
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
    rtp = weighted_payout / max(total_weight, 1) / 100 / MODE_COSTS[mode]
    # Integer lookup weights can leave sub-ppm rounding residue. Keep this strict
    # enough to catch real RTP drift without rejecting a valid 96.10001% mode.
    assert abs(rtp - 0.961) < 1e-6, (mode, rtp)
    print(mode, 'PASS', {'rtp': rtp, 'activations': activated, 'series_snapshots': snapshots}, flush=True)
    return {'rtp': rtp, 'activations': activated, 'series_snapshots': snapshots}


if __name__ == '__main__':
    results = {mode: validate_mode(mode) for mode in MODE_COSTS}
    print('magnetic published artifacts: PASS', results)
