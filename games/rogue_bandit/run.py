"""Generate, weight, package, and validate Rogue Bandit books."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from math import gcd
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.state.run_sims import create_books
from src.write_data.write_configs import generate_configs
from games.rogue_bandit.game_config import GameConfig
from games.rogue_bandit.gamestate import GameState
from games.rogue_bandit import math_targets as T
from games.rogue_bandit.validate_books import validate_library
from games.rogue_bandit.weight_lookups import weight_all


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--books", type=int, default=10_000, help="Complete books per mode")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--seed", type=int, default=20261002)
    args = parser.parse_args()
    if min(args.books, args.threads, args.batch_size) <= 0 or args.books % args.threads:
        parser.error("positive values required; books must divide evenly by threads")
    batch_size = gcd(args.books // args.threads, args.batch_size)
    config = GameConfig()
    config.simulation_seed = args.seed
    library = Path(config.library_path)
    backup = None
    if library.exists():
        backup = library.with_name("library-backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        library.rename(backup)
        print(f"Previous artifacts archived: {backup}", flush=True)
    state = GameState(config)
    metadata = {"status": "generating", "modelVersion": T.MODEL_VERSION, "seed": args.seed,
                "booksPerMode": args.books, "threads": args.threads, "batchSize": batch_size,
                "previousLibrary": str(backup) if backup else None}
    metadata["sourceHashes"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in sorted(Path(__file__).parent.glob("*.py"))}
    metadata_path = library / "configs/generation.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    try:
        create_books(state, config, {mode: args.books for mode in T.MODE_COSTS},
                     batch_size, args.threads, True, False)
        optimization = weight_all(library)
        (library / "configs/optimization_report.json").write_text(json.dumps(optimization, indent=2) + "\n")
        generate_configs(state)
        report = validate_library(library, args.books)
        (library / "configs/simulation_report.json").write_text(json.dumps(report, indent=2) + "\n")
        if report["blockers"]:
            raise RuntimeError("math gates failed: " + "; ".join(report["blockers"]))
        metadata.update(status=report["status"], totalBooks=args.books * len(T.MODE_COSTS))
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
        print(json.dumps(report, indent=2), flush=True)
        print(f"Publish files: {library / 'publish_files'}", flush=True)
    except BaseException:
        metadata["status"] = "failed_incomplete_do_not_publish"
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
        index = library / "publish_files/index.json"
        if index.exists():
            index.rename(index.with_name("index.failed.json"))
        raise


if __name__ == "__main__":
    main()
