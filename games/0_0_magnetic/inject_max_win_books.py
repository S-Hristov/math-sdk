"""Append forced high-payout entries to each mode's book file.

Run from the game directory:
    python inject_max_win_books.py

The script generates deterministic forced rounds that cover the payout range
up to the 20,000× cap, appends them to the existing JSONL books, then
rebuilds all lookup tables via weight_all_lookups.

Each forced entry has a unique id (starting after the last existing id) and
uses criteria matching the mode (basegame / feature / freegame / superspin).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from magnetic_math import generate_forced_coverage_rounds
from math_targets import MODE_COSTS
from weight_lookups import weight_all_lookups

BOOKS_DIR = Path(__file__).parent / 'library' / 'books'
PUBLISH_DIR = Path(__file__).parent / 'library' / 'publish_files'

CRITERIA_FOR_MODE = {
    'BASE': 'basegame',
    'CHANCE': 'basegame',
    'FEATURE': 'feature',
    'BONUS': 'bonus',
    'SUPER': 'super',
}


def _last_id(book_path: Path) -> int:
    last = -1
    with open(book_path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line:
                last = int(json.loads(line)['id'])
    return last


def inject_mode(mode: str) -> list[int]:
    book_path = BOOKS_DIR / f'books_{mode}.jsonl'
    if not book_path.exists():
        print(f'[inject] {mode}: book file not found, skipping')
        return []

    forced_rounds = generate_forced_coverage_rounds(mode)
    if not forced_rounds:
        print(f'[inject] {mode}: no forced rounds defined, skipping')
        return []

    next_id = _last_id(book_path) + 1
    criteria = CRITERIA_FOR_MODE[mode]
    payouts_added: list[int] = []

    with open(book_path, 'a', encoding='utf-8') as fh:
        for result in forced_rounds:
            payout_multiplier = int(result['final_amount'])
            entry = {
                'id': next_id,
                'payoutMultiplier': payout_multiplier,
                'events': result['events'],
                'criteria': criteria,
                'baseGameWins': result.get('basegame_win', 0),
                'freeGameWins': result.get('freegame_win', 0),
            }
            fh.write(json.dumps(entry) + '\n')
            payouts_added.append(payout_multiplier)
            print(f'[inject] {mode}: appended id={next_id} payout={payout_multiplier / 100:.2f}x criteria={criteria}')
            next_id += 1

    return payouts_added


def sync_publish_copies():
    for mode in MODE_COSTS:
        src = BOOKS_DIR / f'books_{mode}.jsonl'
        dst = PUBLISH_DIR / f'books_{mode}.jsonl'
        if src.exists():
            import shutil
            shutil.copy2(src, dst)
            print(f'[sync] copied {src.name} → publish_files/')


if __name__ == '__main__':
    for mode in MODE_COSTS:
        inject_mode(mode)

    sync_publish_copies()

    library_path = str(Path(__file__).parent / 'library')
    print('\n[inject] rebuilding lookup tables...')
    rtps = weight_all_lookups(library_path)
    print('[inject] weighted RTPs:', rtps)
    print('[inject] done')
