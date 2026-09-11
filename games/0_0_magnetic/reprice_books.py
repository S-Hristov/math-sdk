"""Reprice existing Magnetic books after multiplier/paytable contract changes.

Board/RNG outcomes are unchanged. This streams each book, removes legacy mode
scaling from awards, restores exact multiplier compounding from visible magnet
anchors, and rebuilds raw + compressed artifacts atomically.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import zstandard as zstd

from magnetic_math import MAX_WIN_AMOUNT, get_pay_for_size

MODES = ('BASE', 'CHANCE', 'FEATURE', 'BONUS', 'SUPER')


def _position_key(position: dict[str, Any]) -> tuple[int, int]:
    return int(position['reel']), int(position['row'])


def _series_multiplier(series: dict[str, Any], anchor_values: dict[tuple[int, int], int]) -> int:
    if series.get('kind') == 'natural' or str(series.get('id', '')).startswith('side-'):
        return 1
    result = 1
    for anchor in series.get('anchorPositions', []):
        result *= anchor_values.get(_position_key(anchor), 1)
    return result


def repair_events(events: list[dict[str, Any]]) -> int:
    anchor_values: dict[tuple[int, int], int] = {}
    pending_resolved: dict[str, dict[str, Any]] = {}
    running_total = 0
    latest_win = 0

    for event in events:
        event_type = event.get('type')

        if event_type == 'magnetActivated':
            positions = event.get('positions', [])
            raw_multiplier = max(1, int(event.get('multiplier', 1)))
            # One event can contain several magnets whose product is already in
            # `multiplier`. Attach that product once; remaining anchors are 1x.
            for index, position in enumerate(positions):
                anchor_values.setdefault(_position_key(position), raw_multiplier if index == 0 else 1)

        elif event_type in ('clusterSeriesUpdate', 'superSeriesCarry'):
            series_list = event.get('series', [])
            for series in series_list:
                series['multiplier'] = _series_multiplier(series, anchor_values)
            event['totalMultiplier'] = max(
                (int(series.get('multiplier', 1)) for series in series_list),
                default=1,
            )

        elif event_type == 'clusterSeriesResolved':
            pending_resolved[str(event.get('seriesId', ''))] = event

        elif event_type == 'winInfo':
            repaired_wins = []
            remaining = max(0, MAX_WIN_AMOUNT - running_total)
            for win in event.get('wins', []):
                meta = win.setdefault('meta', {})
                series_id = str(win.get('seriesId', ''))
                kind = str(meta.get('seriesKind', ''))
                # ONE ACTIVE SYMBOL PER ROUND: a non-target 'side-N' cluster must not pay.
                # Dropped here so already-simulated books can be corrected without a re-run;
                # magnetic_math.py no longer produces them.  Downstream totals, finalWin and
                # payoutMultiplier all recompute from the surviving wins below.
                if series_id.startswith('side-'):
                    continue
                if kind == 'natural':
                    multiplier = 1
                else:
                    multiplier = 1
                    for anchor in meta.get('anchors', []):
                        multiplier *= anchor_values.get(_position_key(anchor), 1)
                base_amount = int(meta.get('baseAmount', round(get_pay_for_size(str(win['symbol']), int(win['size'])) * 100)))
                amount = min(base_amount * multiplier, remaining)
                if amount <= 0:
                    continue
                meta['baseAmount'] = base_amount
                meta['totalMultiplier'] = multiplier
                win['amount'] = amount
                repaired_wins.append(win)
                remaining -= amount

                resolved = pending_resolved.get(series_id)
                if resolved is not None:
                    resolved['amount'] = amount
                    resolved['multiplier'] = multiplier

            event['wins'] = repaired_wins
            event['totalWin'] = sum(int(win['amount']) for win in repaired_wins)
            latest_win = int(event['totalWin'])
            running_total += latest_win
            pending_resolved.clear()

        elif event_type == 'setTotalWin':
            event['amount'] = running_total

        elif event_type == 'setWin':
            event['amount'] = latest_win

        elif event_type in ('freeSpinEnd', 'finalWin'):
            event['amount'] = running_total

    # Magnet activation is emitted immediately before its corrected series
    # snapshot. Mirror that snapshot's exact compounded display multiplier.
    for index, event in enumerate(events):
        if event.get('type') != 'magnetActivated':
            continue
        position_keys = {_position_key(position) for position in event.get('positions', [])}
        fallback = max(1, int(event.get('multiplier', 1)))
        event['totalMultiplier'] = fallback
        for later in events[index + 1:]:
            if later.get('type') not in ('clusterSeriesUpdate', 'superSeriesCarry'):
                continue
            matched = False
            for series in later.get('series', []):
                anchors = {_position_key(position) for position in series.get('anchorPositions', [])}
                if position_keys & anchors:
                    matched = True
                    break
            if matched:
                event['totalMultiplier'] = int(later.get('totalMultiplier', fallback))
            break

    return running_total


def repair_book(book: dict[str, Any]) -> dict[str, Any]:
    events = book['events']
    final_amount = repair_events(events)
    book['payoutMultiplier'] = final_amount
    has_feature = any(event.get('type') == 'freeSpinTrigger' for event in events)
    if 'baseGameWins' in book:
        book['baseGameWins'] = 0.0 if has_feature else final_amount / 100
    if 'freeGameWins' in book:
        book['freeGameWins'] = final_amount / 100 if has_feature else 0.0
    return book


def reprice_mode(library: Path, mode: str) -> None:
    source = library / 'books' / f'books_{mode}.jsonl'
    raw_tmp = source.with_suffix(source.suffix + '.repriced')
    compressed = library / 'publish_files' / f'books_{mode}.jsonl.zst'
    compressed_tmp = compressed.with_suffix(compressed.suffix + '.repriced')

    rows = 0
    with source.open('rb') as src, raw_tmp.open('wb') as raw_out, compressed_tmp.open('wb') as compressed_file:
        compressor = zstd.ZstdCompressor(level=3)
        with compressor.stream_writer(compressed_file, closefd=False) as compressed_out:
            for line in src:
                if not line.strip():
                    continue
                book = repair_book(json.loads(line))
                encoded = json.dumps(book, separators=(',', ':')).encode() + b'\n'
                raw_out.write(encoded)
                compressed_out.write(encoded)
                rows += 1
                if rows % 10_000 == 0:
                    print(f'{mode}: {rows:,}', flush=True)

    os.replace(raw_tmp, source)
    os.replace(compressed_tmp, compressed)
    print(f'{mode}: complete ({rows:,})', flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=(*MODES, 'ALL'), default='ALL')
    parser.add_argument('--library', type=Path, default=Path(__file__).with_name('library'))
    args = parser.parse_args()
    modes = MODES if args.mode == 'ALL' else (args.mode,)
    for mode in modes:
        reprice_mode(args.library, mode)


if __name__ == '__main__':
    main()
