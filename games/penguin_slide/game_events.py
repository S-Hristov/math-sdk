from typing import Optional
from src.events.event_constants import EventConstants


def slide_start_event(gamestate):
    event = {
        "index": len(gamestate.book.events),
        "type": EventConstants.SLIDE_START.value,
        "startingValue": int(round(gamestate.starting_value * 100, 0)),
        "hasLifering": bool(gamestate.has_lifering),
        "numLanes": int(gamestate.config.num_lanes),
    }
    gamestate.book.add_event(event)


def tile_result_event(
    gamestate,
    step_index: int,
    tile_type: str,
    value: float,
    detail: Optional[dict] = None,
):
    event = {
        "index": len(gamestate.book.events),
        "type": EventConstants.TILE_RESULT.value,
        "stepIndex": int(step_index),
        "tileType": tile_type,
        "value": int(round(value * 100, 0)),
    }
    if detail:
        event.update(detail)
    gamestate.book.add_event(event)


def slide_summary_event(gamestate, steps_taken: int, final_value: float, result: str):
    event = {
        "index": len(gamestate.book.events),
        "type": EventConstants.SLIDE_SUMMARY.value,
        "steps": int(steps_taken),
        "finalValue": int(round(final_value * 100, 0)),
        "result": result,
    }
    gamestate.book.add_event(event)
