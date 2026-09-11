"""Append forced high-payout entries to each mode's book file.

Run from the game directory:
    python inject_max_win_books.py

Generates deterministic, mode-contract-safe forced rounds up to the 25,000x
cap (including exactly 2,500,000 cents per mode), appends them to the
existing JSONL books with fresh ids, syncs the publish copies, then rebuilds
all lookup tables via weight_all_lookups.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GAME_DIR = Path(__file__).resolve().parent
if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

import zstandard as zstd

from theme_park_math import generate_forced_coverage_rounds
from game_config import GameConfig
from gamestate import GameState
from math_targets import MODE_COSTS
from report import write_report
from src.write_data.write_configs import generate_configs
from weight_lookups import weight_all_lookups

BOOKS_DIR = Path(__file__).parent / 'library' / 'books'
PUBLISH_DIR = Path(__file__).parent / 'library' / 'publish_files'

CRITERIA_FOR_MODE = {
    'BASE': 'coaster',
    'ANTE': 'coaster',
    'FSPIN1': 'duckcollect',
    'FSPIN2': 'rollerwild',
    'DUCK': 'duck',
    'ROLLER': 'roller',
    'COASTER': 'coaster',
}


def _scan_books(book_path: Path) -> tuple[int, set[tuple[int, str]]]:
    """Return (last id, set of existing (payoutMultiplier, criteria) pairs).

    The pair set makes re-runs idempotent: forced entries already injected by a
    previous run (same payout + criteria) are skipped instead of duplicated.
    """
    last = -1
    existing: set[tuple[int, str]] = set()
    with open(book_path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            last = int(raw['id'])
            existing.add((int(raw['payoutMultiplier']), str(raw.get('criteria', ''))))
    return last, existing


def inject_mode(mode: str) -> list[int]:
    book_path = BOOKS_DIR / f'books_{mode}.jsonl'
    if not book_path.exists():
        print(f'[inject] {mode}: book file not found, skipping')
        return []

    forced_rounds = generate_forced_coverage_rounds(mode)
    if not forced_rounds:
        print(f'[inject] {mode}: no forced rounds defined, skipping')
        return []

    last_id, existing_pairs = _scan_books(book_path)
    next_id = last_id + 1
    criteria = CRITERIA_FOR_MODE[mode]
    payouts_added: list[int] = []

    with open(book_path, 'a', encoding='utf-8') as fh:
        for result in forced_rounds:
            payout_multiplier = int(result['final_amount'])
            if (payout_multiplier, criteria) in existing_pairs:
                print(f'[inject] {mode}: skipped payout={payout_multiplier / 100:.2f}x criteria={criteria} (already present)')
                continue
            entry = {
                'id': next_id,
                'payoutMultiplier': payout_multiplier,
                'events': result['events'],
                'criteria': criteria,
                'baseGameWins': result.get('basegame_win', 0) / 100.0,
                'freeGameWins': result.get('freegame_win', 0) / 100.0,
            }
            fh.write(json.dumps(entry) + '\n')
            payouts_added.append(payout_multiplier)
            print(f'[inject] {mode}: appended id={next_id} payout={payout_multiplier / 100:.2f}x criteria={criteria}')
            next_id += 1

    if not payouts_added:
        print(f'[inject] {mode}: nothing new to inject')
    return payouts_added


def sync_publish_copies():
    compressor = zstd.ZstdCompressor()
    for mode in MODE_COSTS:
        src = BOOKS_DIR / f'books_{mode}.jsonl'
        if not src.exists():
            continue
        dst = PUBLISH_DIR / f'books_{mode}.jsonl.zst'
        with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
            fdst.write(compressor.compress(fsrc.read()))
        print(f'[sync] compressed {src.name} -> publish_files/{dst.name}')


if __name__ == '__main__':
    for mode in MODE_COSTS:
        inject_mode(mode)

    sync_publish_copies()

    library_path = str(Path(__file__).parent / 'library')
    print('\n[inject] rebuilding lookup tables...')
    rtps = weight_all_lookups(library_path)
    print('[inject] weighted RTPs:', rtps)
    config = GameConfig()
    generate_configs(GameState(config))
    print('[inject] report:', write_report(library_path, MODE_COSTS))
    print('[inject] done')
