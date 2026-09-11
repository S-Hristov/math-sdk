"""Show what the weighting WOULD produce, without writing any lookup table.

    python3 games/0_0_mcschmutzo/preview_weighting.py base bonus1

Prints, per group: trigger rate, mean, median, p90, p99 and the 0x rate, plus the mode RTP. Use it
to tune math_targets.py (frequency, mean, TARGET_SCALES, ZERO_WEIGHT_CAP) before committing to a
reweight run.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from game_config import GameConfig
from math_targets import MODE_COSTS
from weight_lookups import _group_of, _load_books, build_mode_lookup


def describe(rows, group_of=None):
    total = sum(w for _, w, _ in rows) or 1
    groups = {}
    for book_id, w, pm in rows:
        key = group_of.get(book_id, 'all') if group_of else 'all'
        g = groups.setdefault(key, {'w': 0, 'wp': 0, 'z': 0, 'vals': []})
        g['w'] += w
        g['wp'] += w * pm
        g['z'] += w if pm == 0 else 0
        g['vals'].append((pm / 100.0, w))
    out = []
    for key, g in sorted(groups.items(), key=lambda kv: -kv[1]['w']):
        cum, pct = 0, {0.5: None, 0.9: None, 0.99: None}
        for v, w in sorted(g['vals']):
            cum += w
            for t in list(pct):
                if pct[t] is None and cum / g['w'] >= t:
                    pct[t] = v
        out.append(
            f"   {key:10s} 1 in {total / g['w']:9.1f} | mean {g['wp'] / g['w'] / 100:9.2f}x | "
            f"median {pct[0.5]:8.2f}x | p90 {pct[0.9]:9.2f}x | p99 {pct[0.99]:10.2f}x | P(0x) {g['z'] / g['w']:6.2%}"
        )
    return out


if __name__ == '__main__':
    modes = sys.argv[1:] or list(MODE_COSTS)
    config = GameConfig()
    for mode in modes:
        books = _load_books(config.library_path, mode)
        group_of = {b['id']: _group_of(b) for b in books}
        rows = build_mode_lookup(mode, books)
        rtp = sum(w * pm for _, w, pm in rows) / sum(w for _, w, _ in rows) / 100 / MODE_COSTS[mode]
        print(f"\n=== {mode} (cost {MODE_COSTS[mode]}x) — PREVIEW ONLY, nothing written")
        for line in describe(rows, group_of):
            print(line)
        print(f"   mode RTP {rtp:.4%}")
        del books, rows, group_of
