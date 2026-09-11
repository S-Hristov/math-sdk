"""Generate Theme Park books/configs."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GAME_DIR = Path(__file__).resolve().parent
if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

import zstandard as zstd

from game_config import GameConfig
from gamestate import GameState
from math_targets import MODE_COSTS
from report import write_report
from src.state.run_sims import create_books
from src.write_data.write_configs import generate_configs
from weight_lookups import weight_all_lookups


def write_local_mock_jsonl_copies(config: GameConfig):
    publish_path = os.path.join(config.library_path, 'publish_files')
    books_path = os.path.join(config.library_path, 'books')
    for mode in MODE_COSTS:
        src = os.path.join(publish_path, f'books_{mode}.jsonl.zst')
        dst = os.path.join(books_path, f'books_{mode}.jsonl')
        if not os.path.exists(src):
            continue
        with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
            fdst.write(zstd.ZstdDecompressor().decompress(fsrc.read()))
        print('wrote', dst)


if __name__ == '__main__':
    num_threads = int(os.environ.get('TP_THREADS', '10'))
    batching_size = int(os.environ.get('TP_BATCH', '25'))
    compression = True
    profiling = False
    num_sim_args = {
        'BASE': int(float(os.environ.get('TP_BASE_SIMS', '500000'))),
        'ANTE': int(float(os.environ.get('TP_ANTE_SIMS', '500000'))),
        'FSPIN1': int(float(os.environ.get('TP_FSPIN1_SIMS', '200000'))),
        'FSPIN2': int(float(os.environ.get('TP_FSPIN2_SIMS', '200000'))),
        'DUCK': int(float(os.environ.get('TP_DUCK_SIMS', '200000'))),
        'ROLLER': int(float(os.environ.get('TP_ROLLER_SIMS', '300000'))),
        'COASTER': int(float(os.environ.get('TP_COASTER_SIMS', '300000'))),
    }

    print('theme_park run config:', {'threads': num_threads, 'batch': batching_size, **num_sim_args})

    config = GameConfig()
    gamestate = GameState(config)
    create_books(gamestate, config, num_sim_args, batching_size, num_threads, compression, profiling)
    write_local_mock_jsonl_copies(config)
    weighted_rtps = weight_all_lookups(config.library_path)
    generate_configs(gamestate)
    report_path = write_report(config.library_path, MODE_COSTS)
    print('weighted_rtps:', weighted_rtps)
    print('report:', report_path)
    print('done:', config.library_path)
