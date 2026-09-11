"""Magnetic proto event helpers."""

from __future__ import annotations


def add_event(gamestate, payload: dict):
    event = dict(payload)
    event['index'] = len(gamestate.book.events)
    gamestate.book.add_event(event)


def reveal_event(gamestate, board, game_type: str):
    add_event(
        gamestate,
        {
            'type': 'reveal',
            'board': board,
            'paddingPositions': [1, 3, 5, 7, 9, 11, 13],
            'anticipation': [0] * 7,
            'gameType': game_type,
        },
    )


def win_info_event(gamestate, wins: list):
    add_event(gamestate, {'type': 'winInfo', 'totalWin': sum(win['amount'] for win in wins), 'wins': wins})


def set_win_event(gamestate, amount: int, win_level: int):
    add_event(gamestate, {'type': 'setWin', 'amount': amount, 'winLevel': win_level})


def set_total_event(gamestate, amount: int):
    add_event(gamestate, {'type': 'setTotalWin', 'amount': amount})


def fs_trigger_event(gamestate, total_fs: int, positions: list):
    add_event(gamestate, {'type': 'freeSpinTrigger', 'totalFs': total_fs, 'positions': positions})


def update_fs_event(gamestate, amount: int, total: int):
    add_event(gamestate, {'type': 'updateFreeSpin', 'amount': amount, 'total': total})


def fs_end_event(gamestate, amount: int, win_level: int):
    add_event(gamestate, {'type': 'freeSpinEnd', 'amount': amount, 'winLevel': win_level})


def final_win_event(gamestate, amount: int):
    add_event(gamestate, {'type': 'finalWin', 'amount': amount})


def magnet_activated_event(gamestate, series_id: str, symbol: str, positions: list, multiplier: int, total_multiplier: int, persistent: bool):
    add_event(
        gamestate,
        {
            'type': 'magnetActivated',
            'seriesId': series_id,
            'symbol': symbol,
            'positions': positions,
            'multiplier': multiplier,
            'totalMultiplier': total_multiplier,
            'persistent': persistent,
        },
    )


def magnet_target_selected_event(gamestate, symbol: str):
    add_event(gamestate, {'type': 'magnetTargetSelected', 'symbol': symbol})


def cluster_series_update_event(gamestate, series: list, magnet_target_symbol, total_multiplier: int):
    add_event(
        gamestate,
        {
            'type': 'clusterSeriesUpdate',
            'series': series,
            'magnetTargetSymbol': magnet_target_symbol,
            'totalMultiplier': total_multiplier,
        },
    )


def cluster_series_resolved_event(gamestate, series_id: str, symbol: str, positions: list, amount: int, multiplier: int):
    add_event(
        gamestate,
        {
            'type': 'clusterSeriesResolved',
            'seriesId': series_id,
            'symbol': symbol,
            'positions': positions,
            'amount': amount,
            'multiplier': multiplier,
        },
    )


def super_series_carry_event(gamestate, series, magnet_target_symbol, total_multiplier: int):
    add_event(
        gamestate,
        {
            'type': 'superSeriesCarry',
            'series': series,
            'magnetTargetSymbol': magnet_target_symbol,
            'totalMultiplier': total_multiplier,
        },
    )
