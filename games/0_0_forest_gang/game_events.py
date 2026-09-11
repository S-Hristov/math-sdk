"""Forest Gang event helpers."""

from src.events.event_constants import EventConstants
from forest_math import SCATTER, ROW_OFFSET, board_json, calc_padding_positions


def add_event(gamestate, payload: dict):
    payload = dict(payload)
    payload['index'] = len(gamestate.book.events)
    gamestate.book.add_event(payload)


def build_scatter_anticipation(board, game_type: str):
    # Anticipation works for all modes — scatters retrigger in bonus too

    visible_scatter_reels = []
    for reel_index, reel in enumerate(board):
        has_scatter = any(reel[row + ROW_OFFSET] == SCATTER for row in range(4))
        visible_scatter_reels.append(has_scatter)

    total_scatters = sum(visible_scatter_reels)
    if total_scatters < 2:
        return [0, 0, 0, 0, 0]

    anticipation = [0, 0, 0, 0, 0]
    anticipation_index = 0

    for reel_index in range(5):
        previous_scatters = sum(visible_scatter_reels[:reel_index])

        if previous_scatters >= 3:
            # 3 already landed — anticipate retrigger (4th scatter)
            anticipation_index += 1
            anticipation[reel_index] = anticipation_index
        elif previous_scatters >= 2:
            # 2 already landed — anticipate trigger (3rd scatter), even on near-miss
            anticipation_index += 1
            anticipation[reel_index] = anticipation_index

    return anticipation


def reveal_event(gamestate, board, game_type: str):
    add_event(
        gamestate,
        {
            'type': EventConstants.REVEAL.value,
            'board': board_json(board),
            'paddingPositions': calc_padding_positions(),
            'anticipation': build_scatter_anticipation(board, game_type),
            'gameType': game_type,
        },
    )


def win_info_event(gamestate, total_win: int, wins: list):
    add_event(gamestate, {'type': EventConstants.WIN_DATA.value, 'totalWin': total_win, 'wins': wins})


def set_win_event(gamestate, amount: int, win_level: int):
    add_event(gamestate, {'type': EventConstants.SET_WIN.value, 'amount': amount, 'winLevel': win_level})


def set_total_event(gamestate, amount: int):
    add_event(gamestate, {'type': EventConstants.SET_TOTAL_WIN.value, 'amount': amount})


def fs_trigger_event(gamestate, total_fs: int, positions: list):
    add_event(gamestate, {'type': EventConstants.FREESPINTRIGGER.value, 'totalFs': total_fs, 'positions': positions})


def update_fs_event(gamestate, amount: int, total: int):
    add_event(gamestate, {'type': EventConstants.UPDATE_FS.value, 'amount': amount, 'total': total})


def fs_end_event(gamestate, amount: int, win_level: int):
    add_event(gamestate, {'type': EventConstants.FREE_SPIN_END.value, 'amount': amount, 'winLevel': win_level})


def final_win_event(gamestate, amount: int):
    add_event(gamestate, {'type': EventConstants.FINAL_WIN.value, 'amount': amount})


def bonus_symbol_selected_event(gamestate, symbol: str, mode: str, profile: str | None = None):
    event: dict = {'type': 'bonusSymbolSelected', 'symbol': symbol, 'mode': mode}
    if profile is not None:
        event['profile'] = profile
    add_event(gamestate, event)


def expanded_symbol_reveal_event(gamestate, symbol: str, reels: list, positions: list):
    add_event(gamestate, {'type': 'expandedSymbolReveal', 'symbol': symbol, 'reels': reels, 'positions': positions})


def apply_temp_multiplier_event(gamestate, multiplier: int, win_before: int, win_after: int):
    add_event(gamestate, {'type': 'applyTempMultiplier', 'multiplier': multiplier, 'winBefore': win_before, 'winAfter': win_after})


def update_global_multiplier_event(gamestate, multiplier: int):
    add_event(gamestate, {'type': 'updateGlobalMultiplier', 'multiplier': multiplier})


def retrigger_free_spins_event(gamestate, amount: int, total: int, scatter_count: int, positions: list):
    add_event(gamestate, {'type': 'retriggerFreeSpins', 'amount': amount, 'total': total, 'scatterCount': scatter_count, 'positions': positions})
