"""McSchmutzo-specific RGS events."""

from copy import deepcopy


def _client_positions(gamestate, positions):
    positions = deepcopy(positions)
    if gamestate.config.include_padding:
        for position in positions:
            position["row"] += 1
    return positions


def lock_respin_start_event(gamestate, symbol, positions):
    gamestate.book.add_event(
        {
            "index": len(gamestate.book.events),
            "type": "lockRespinStart",
            "symbol": symbol,
            "lockedPositions": _client_positions(gamestate, positions),
            "globalMult": gamestate.global_multiplier,
        }
    )


def lock_respin_update_event(
    gamestate,
    new_positions,
    collected_scatter_positions,
    multiplier_positions,
    added_steps,
):
    gamestate.book.add_event(
        {
            "index": len(gamestate.book.events),
            "type": "lockRespinUpdate",
            "newLockedPositions": _client_positions(gamestate, new_positions),
            "scatterPositions": _client_positions(gamestate, collected_scatter_positions),
            "multiplierPositions": _client_positions(gamestate, multiplier_positions),
            "collectedScatters": gamestate.collected_scatters,
            "addedSteps": added_steps,
            "globalMult": gamestate.global_multiplier,
        }
    )


def lock_respin_end_event(gamestate, symbol, positions):
    gamestate.book.add_event(
        {
            "index": len(gamestate.book.events),
            "type": "lockRespinEnd",
            "symbol": symbol,
            "lockedPositions": _client_positions(gamestate, positions),
            "collectedScatters": gamestate.collected_scatters,
            "globalMult": gamestate.global_multiplier,
        }
    )


def multiplier_update_event(gamestate, previous, added_steps, source):
    gamestate.book.add_event(
        {
            "index": len(gamestate.book.events),
            "type": "updateGlobalMult",
            "previousGlobalMult": previous,
            "globalMult": gamestate.global_multiplier,
            "addedSteps": added_steps,
            "source": source,
        }
    )


def bonus_wheel_event(gamestate, entry, free_spins, added_steps, previous):
    gamestate.book.add_event(
        {
            "index": len(gamestate.book.events),
            "type": "bonusWheel",
            "scatterEntry": entry,
            "freeSpins": free_spins,
            "addedSteps": added_steps,
            "previousGlobalMult": previous,
            "globalMult": gamestate.global_multiplier,
        }
    )


def freegame_end_event(gamestate, amount):
    gamestate.book.add_event(
        {
            "index": len(gamestate.book.events),
            "type": "freeSpinEnd",
            "amount": int(round(amount * 100)),
            "globalMult": gamestate.global_multiplier,
        }
    )

