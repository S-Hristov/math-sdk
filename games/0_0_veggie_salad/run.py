"""Generate, weight and package Veggie Salad books."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import zstandard as zstd

from game_config import GameConfig
from gamestate import GameState
from math_targets import MODE_COSTS
from report import write_report
from src.state.run_sims import create_books
from src.write_data.write_configs import generate_configs
from weight_lookups import weight_all_lookups


def write_local_books(config: GameConfig) -> None:
    for mode in MODE_COSTS:
        source = os.path.join(config.library_path, "publish_files", f"books_{mode}.jsonl.zst")
        target = os.path.join(config.library_path, "books", f"books_{mode}.jsonl")
        if not os.path.exists(source):
            continue
        with open(source, "rb") as compressed, open(target, "wb") as output:
            with zstd.ZstdDecompressor().stream_reader(compressed) as reader:
                shutil.copyfileobj(reader, output, length=16 * 1024 * 1024)


if __name__ == "__main__":
    common_sims = int(float(os.environ.get("VEGGIE_SIMS", "50000")))
    num_sim_args = {
        mode: int(float(os.environ.get(f"VEGGIE_{mode}_SIMS", str(common_sims))))
        for mode in MODE_COSTS
    }
    threads = int(os.environ.get("VEGGIE_THREADS", "1"))
    batch = int(os.environ.get("VEGGIE_BATCH", "25"))
    print("Veggie Salad run:", {"threads": threads, "batch": batch, **num_sim_args})

    config = GameConfig()
    gamestate = GameState(config)
    create_books(gamestate, config, num_sim_args, batch, threads, True, False)
    write_local_books(config)
    rtps = weight_all_lookups(config.library_path)
    generate_configs(gamestate)
    report_path = write_report(config.library_path)
    print("weighted RTPs:", rtps)
    print("report:", report_path)
    print("done:", config.library_path)
