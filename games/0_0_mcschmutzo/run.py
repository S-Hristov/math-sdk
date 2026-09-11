"""Generate McSchmutzo books, configs, optimization tables, and reports."""

import sys
from pathlib import Path

# The shared virtualenv is editable-installed against the primary checkout.
# Force imports to resolve from this branch's worktree instead.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from game_config import GameConfig
from game_optimization import OptimizationSetup
from gamestate import GameState
from optimization_program.run_script import OptimizationExecution
from src.state.run_sims import create_books
from src.write_data.write_configs import generate_configs
from utils.game_analytics.run_analysis import create_stat_sheet
from utils.rgs_verification import execute_all_tests


if __name__ == "__main__":
    num_threads = 10
    rust_threads = 20
    batching_size = 5000
    compression = True
    profiling = False

    num_sim_args = {
        "base": int(1e5),
        "enhancer1": int(1e5),
        "featureSpin": int(1e5),
        "bonus1": int(1e5),
        "bonus2": int(1e5),
    }
    run_conditions = {
        "run_sims": True,
        "run_optimization": True,
        "run_analysis": True,
        "run_format_checks": True,
    }

    config = GameConfig()
    gamestate = GameState(config)
    OptimizationSetup(config)

    if run_conditions["run_sims"]:
        create_books(
            gamestate,
            config,
            num_sim_args,
            batching_size,
            num_threads,
            compression,
            profiling,
        )

    generate_configs(gamestate)

    if run_conditions["run_optimization"]:
        OptimizationExecution().run_all_modes(config, list(num_sim_args), rust_threads)
        generate_configs(gamestate)

    if run_conditions["run_analysis"]:
        create_stat_sheet(
            gamestate,
            custom_keys=[
                {"symbol": "scatter"},
                {"symbol": "multiplier"},
                {"feature": "lockRespin"},
            ],
        )

    if run_conditions["run_format_checks"]:
        execute_all_tests(config)
