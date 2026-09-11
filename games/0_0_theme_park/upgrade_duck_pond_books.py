"""Upgrade existing Theme Park books to the current Duck Your Luck event contract.

Payouts and lookup weights stay unchanged. Existing picked results remain the
first entries in the pool; deterministic reveal-only prizes fill the pond.
Legacy cap books are extended to ten no-op-at-cap pick events so manual play
always reaches the required ten selections. Trigger positions are copied from
the settled S_DUCK scatter board so the client can visibly celebrate the bonus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from pathlib import Path

import zstandard as zstd

from math_targets import MODE_COSTS
from theme_park_math import (
    DUCK_BONUS_DIRECT_POOL,
    DUCK_BONUS_MM_POOL,
    DUCK_POND_SIZE,
    MAX_WIN_AMOUNT,
    TOTAL_PICKS,
    roll_duck_sequence,
)


def _rng_for(mode: str, book_id: int) -> random.Random:
    digest = hashlib.sha256(f'theme-park-duck-pond-v1:{mode}:{book_id}'.encode()).digest()
    return random.Random(int.from_bytes(digest[:8], 'big'))


def upgrade_book(book: dict, mode: str) -> bool:
    events = book.get('events', [])
    try:
        start_index = next(i for i, event in enumerate(events) if event.get('type') == 'duckPickStart')
        end_index = next(i for i, event in enumerate(events[start_index + 1:], start_index + 1) if event.get('type') == 'duckPickEnd')
    except StopIteration:
        return False

    start = events[start_index]
    changed = False
    if not start.get('positions'):
        reveal = next(
            (event for event in reversed(events[:start_index]) if event.get('type') == 'reveal'),
            None,
        )
        if reveal is None:
            raise ValueError(f'{mode}/{book.get("id")}: duckPickStart has no preceding reveal')
        positions = [
            {'reel': reel_index, 'row': padded_row - 1}
            for reel_index, reel in enumerate(reveal.get('board', []))
            for padded_row, cell in enumerate(reel)
            if 1 <= padded_row <= 5
            and cell.get('name') == 'S_DUCK'
            and cell.get('scatter')
        ]
        if len(positions) < 3:
            raise ValueError(
                f'{mode}/{book.get("id")}: expected 3+ Duck Your Luck triggers, got {len(positions)}'
            )
        start['positions'] = positions
        changed = True

    picks = [event for event in events[start_index + 1:end_index] if event.get('type') == 'duckPick']
    if len(start.get('pool', [])) == DUCK_POND_SIZE and len(picks) == TOTAL_PICKS:
        if changed:
            for index, event in enumerate(events):
                event['index'] = index
        return changed

    rng = _rng_for(mode, int(book.get('id', 0)))
    selected = [(str(event['kind']), int(event['value'])) for event in picks]
    if len(selected) < TOTAL_PICKS:
        selected.extend(
            roll_duck_sequence(
                rng,
                TOTAL_PICKS - len(selected),
                DUCK_BONUS_DIRECT_POOL,
                DUCK_BONUS_MM_POOL,
            )
        )

        cap_total = int(picks[-1]['runningTotal']) if picks else MAX_WIN_AMOUNT
        additions = [
            {
                'type': 'duckPick',
                'pickIndex': pick_index,
                'kind': kind,
                'value': value,
                'runningTotal': cap_total,
            }
            for pick_index, (kind, value) in enumerate(selected[len(picks):], len(picks))
        ]
        events[end_index:end_index] = additions

    reveal_only = roll_duck_sequence(
        rng,
        DUCK_POND_SIZE - TOTAL_PICKS,
        DUCK_BONUS_DIRECT_POOL,
        DUCK_BONUS_MM_POOL,
    )
    start['totalPicks'] = TOTAL_PICKS
    start['pool'] = [
        {'kind': kind, 'value': value}
        for kind, value in selected[:TOTAL_PICKS] + reveal_only
    ]
    for index, event in enumerate(events):
        event['index'] = index
    return True


def upgrade_jsonl(path: Path, mode: str) -> tuple[int, int]:
    temp = path.with_suffix(path.suffix + '.tmp')
    rows = changed = 0
    with path.open('r', encoding='utf-8') as source, temp.open('w', encoding='utf-8') as target:
        for line in source:
            if not line.strip():
                continue
            book = json.loads(line)
            rows += 1
            changed += int(upgrade_book(book, mode))
            target.write(json.dumps(book, separators=(',', ':')) + '\n')
    os.replace(temp, path)
    return rows, changed


def compress_jsonl(source: Path, target: Path) -> None:
    temp = target.with_suffix(target.suffix + '.tmp')
    with source.open('rb') as raw, temp.open('wb') as compressed:
        zstd.ZstdCompressor(level=10).copy_stream(raw, compressed)
    os.replace(temp, target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', type=Path, default=Path(__file__).resolve().parent / 'library')
    parser.add_argument('--compress', action='store_true')
    parser.add_argument('--modes', nargs='+', choices=list(MODE_COSTS), default=list(MODE_COSTS))
    args = parser.parse_args()

    for mode in args.modes:
        path = args.library / 'books' / f'books_{mode}.jsonl'
        if not path.exists():
            continue
        rows, changed = upgrade_jsonl(path, mode)
        print(f'{mode}: {changed}/{rows} books upgraded')
        if args.compress:
            target = args.library / 'publish_files' / f'books_{mode}.jsonl.zst'
            if target.exists():
                compress_jsonl(path, target)
                print(f'{mode}: compressed publish book regenerated')


if __name__ == '__main__':
    main()
