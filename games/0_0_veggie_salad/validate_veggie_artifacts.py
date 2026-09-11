"""Validate generated Veggie Salad books, lookups and published packages."""

from __future__ import annotations

import json
from pathlib import Path

import zstandard as zstd

from math_targets import LOOKUP_SCALE, MAX_WIN_AMOUNT, MODE_COSTS, TARGET_RTP
from veggie_math import MULTIPLIER_CAP, PAY_SYMBOLS, pay_for_cluster, position_key


ROOT = Path(__file__).resolve().parent
LIBRARY = ROOT / "library"


def _connected(positions: list[dict]) -> bool:
    keys = {position_key(item) for item in positions}
    pending = [next(iter(keys))]
    reached = {pending[0]}
    while pending:
        reel, row = pending.pop()
        for key in ((reel - 1, row), (reel + 1, row), (reel, row - 1), (reel, row + 1)):
            if key in keys and key not in reached:
                reached.add(key)
                pending.append(key)
    return reached == keys


def _validate_book(book: dict) -> None:
    events = book["events"]
    assert [event["index"] for event in events] == list(range(len(events)))
    assert int(book["payoutMultiplier"]) <= MAX_WIN_AMOUNT
    assert events[-1]["type"] == "finalWin"
    assert int(events[-1]["amount"]) == int(book["payoutMultiplier"])

    board = None
    running_total = 0
    for event in events:
        event_type = event["type"]
        if event_type == "reveal":
            board = event["board"]
            size = int(event["gridSize"])
            assert len(board) == size and all(len(column) == size for column in board)
        elif event_type == "clusterWin":
            assert board is not None
            for win in event["wins"]:
                positions = win["positions"]
                symbol = win["symbol"]
                assert symbol in PAY_SYMBOLS
                assert len(positions) == int(win["size"]) >= 5
                assert _connected(positions)
                assert all(board[p["reel"]][p["row"]]["name"] == symbol for p in positions)
                values = [int(value) for value in win["multiplierValues"]]
                product = 1
                for value in values:
                    assert value in (2, 4)
                    product *= value
                assert int(win["rawMultiplier"]) == product
                assert int(win["appliedMultiplier"]) == min(MULTIPLIER_CAP, product)
                assert int(win["rawAmount"]) == pay_for_cluster(symbol, len(positions))
                assert 0 < int(win["amount"]) <= int(win["rawAmount"]) * int(win["appliedMultiplier"])
            running_total += int(event["totalWin"])
        elif event_type == "setTotalWin":
            assert int(event["amount"]) == running_total


def _load_books(mode: str) -> dict[int, dict]:
    path = LIBRARY / "books" / f"books_{mode}.jsonl"
    books = {}
    with path.open(encoding="utf-8") as file:
        for line in file:
            book = json.loads(line)
            _validate_book(book)
            book_id = int(book["id"])
            assert book_id not in books
            books[book_id] = book
    return books


def _validate_publish_copy(mode: str, plain_path: Path) -> None:
    compressed_path = LIBRARY / "publish_files" / f"books_{mode}.jsonl.zst"
    with compressed_path.open("rb") as compressed:
        with zstd.ZstdDecompressor().stream_reader(compressed) as reader:
            assert reader.read() == plain_path.read_bytes()


def _validate_mode(mode: str) -> None:
    books = _load_books(mode)
    plain_path = LIBRARY / "books" / f"books_{mode}.jsonl"
    _validate_publish_copy(mode, plain_path)

    lookup_path = LIBRARY / "publish_files" / f"lookUpTable_{mode}_0.csv"
    total_weight = 0
    payout_sum = 0
    seen = set()
    with lookup_path.open(encoding="utf-8") as file:
        for line in file:
            book_id, weight, payout = map(int, line.strip().split(","))
            assert book_id in books and book_id not in seen
            assert weight > 0
            assert payout == int(books[book_id]["payoutMultiplier"])
            seen.add(book_id)
            total_weight += weight
            payout_sum += weight * payout
    assert seen == set(books)
    assert total_weight == LOOKUP_SCALE
    rtp = payout_sum / (LOOKUP_SCALE * 100 * MODE_COSTS[mode])
    # Cent-denominated books can leave a sub-1e-8 lattice residual.
    assert abs(rtp - TARGET_RTP) < 1e-8, (mode, rtp)


for mode in MODE_COSTS:
    _validate_mode(mode)

print("Veggie Salad generated artifacts: PASS")
