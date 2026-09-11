"""Theme Park thin event emitters (gamestate-book helpers, magnetic-style).

The round engine in theme_park_math.py emits events directly; these helpers
exist for parity with the other custom games and for ad-hoc tooling.
"""

from __future__ import annotations


def add_event(gamestate, payload: dict):
    event = dict(payload)
    event['index'] = len(gamestate.book.events)
    gamestate.book.add_event(event)


def reveal_event(gamestate, board, padding_positions, anticipation, game_type: str):
    add_event(gamestate, {
        'type': 'reveal',
        'board': board,
        'paddingPositions': padding_positions,
        'anticipation': anticipation,
        'gameType': game_type,
    })


def win_info_event(gamestate, total_win: int, wins: list):
    add_event(gamestate, {'type': 'winInfo', 'totalWin': total_win, 'wins': wins})


def set_total_event(gamestate, amount: int):
    add_event(gamestate, {'type': 'setTotalWin', 'amount': amount})


def set_win_event(gamestate, amount: int, win_level: int):
    add_event(gamestate, {'type': 'setWin', 'amount': amount, 'winLevel': win_level})


def final_win_event(gamestate, amount: int):
    add_event(gamestate, {'type': 'finalWin', 'amount': amount})


def fs_trigger_event(gamestate, total_fs: int, positions: list, bonus_type: str):
    add_event(gamestate, {'type': 'freeSpinTrigger', 'totalFs': total_fs, 'positions': positions, 'bonusType': bonus_type})


def update_fs_event(gamestate, amount: int, total: int):
    add_event(gamestate, {'type': 'updateFreeSpin', 'amount': amount, 'total': total})


def fs_end_event(gamestate, amount: int, win_level: int):
    add_event(gamestate, {'type': 'freeSpinEnd', 'amount': amount, 'winLevel': win_level})


def wincap_event(gamestate, amount: int):
    add_event(gamestate, {'type': 'wincap', 'amount': amount})


def duck_collect_start_event(gamestate, positions: list):
    add_event(gamestate, {'type': 'duckCollectStart', 'positions': positions})


def duck_reveal_event(gamestate, position: dict, kind: str, value: int, running_total: int):
    add_event(gamestate, {'type': 'duckReveal', 'position': position, 'kind': kind, 'value': value, 'runningTotal': running_total})


def duck_collect_end_event(gamestate, amount: int):
    add_event(gamestate, {'type': 'duckCollectEnd', 'amount': amount})


def duck_pick_start_event(gamestate, total_picks: int, pool: list, positions: list):
    add_event(gamestate, {
        'type': 'duckPickStart',
        'totalPicks': total_picks,
        'pool': pool,
        'positions': positions,
    })


def duck_pick_event(gamestate, pick_index: int, kind: str, value: int, running_total: int):
    add_event(gamestate, {'type': 'duckPick', 'pickIndex': pick_index, 'kind': kind, 'value': value, 'runningTotal': running_total})


def duck_pick_end_event(gamestate, amount: int):
    add_event(gamestate, {'type': 'duckPickEnd', 'amount': amount})


def roller_wilds_apply_event(gamestate, reels: list):
    add_event(gamestate, {'type': 'rollerWildsApply', 'reels': reels})


def coaster_setup_event(gamestate, pukes: list, tiles: list):
    add_event(gamestate, {'type': 'coasterSetup', 'pukes': pukes, 'tiles': tiles})
