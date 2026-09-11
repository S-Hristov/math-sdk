"""Re-weight lookups and rebuild configs/report from EXISTING books.

run.py re-simulates before weighting.  After reprice_books.py has corrected book
payouts in place, the boards are still valid — only the lookup weights need to be
re-solved so each mode lands back on TARGET_RTP.  This is that step alone.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game_config import GameConfig
from gamestate import GameState
from math_targets import MODE_COSTS
from report import write_report
from src.write_data.write_configs import generate_configs
from weight_lookups import weight_all_lookups

if __name__ == '__main__':
    # Optional mode filter: `python3 reweight_only.py BASE CHANCE` re-weights only those two and
    # leaves every other mode's lookup table byte-for-byte as it was.
    modes = sys.argv[1:] or None
    config = GameConfig()
    gamestate = GameState(config)
    weighted_rtps = weight_all_lookups(config.library_path, modes)
    generate_configs(gamestate)
    report_path = write_report(config.library_path, MODE_COSTS)
    print('weighted_rtps:', weighted_rtps)
    print('report:', report_path)
    print('done:', config.library_path)
