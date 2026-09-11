"""Re-weight McSchmutzo lookups from EXISTING books and rebuild the configs.

run.py re-simulates and then runs the Rust optimizer. This replaces only the weighting step, using
weight_lookups.py, and leaves books_*.jsonl.zst untouched.

    python3 games/0_0_mcschmutzo/reweight_only.py base enhancer1 bonus1 bonus2
    python3 games/0_0_mcschmutzo/reweight_only.py               # every mode
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from game_config import GameConfig
from gamestate import GameState
from src.write_data.write_configs import generate_configs
from weight_lookups import weight_all_lookups

if __name__ == '__main__':
    modes = sys.argv[1:] or None
    config = GameConfig()
    gamestate = GameState(config)
    weighted_rtps = weight_all_lookups(config.library_path, modes)
    generate_configs(gamestate)
    print('weighted_rtps:', weighted_rtps)
    print('done:', config.library_path)
