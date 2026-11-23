"""duty.py against a simulated Derive account and book.

    python3 -m unittest discover -s tests -v

The first half is the stand-in for the `bevo` SDK the tests run duty.py against:

A scripted stand-in for the `bevo` SDK and the options rail, for running duty.py offline.

`run(...)` installs a fresh fake as `bevo`, steps the clock through `times` (the
first is the program's start, the rest are ticks), routes every `acp options`
command into a small simulated Derive account (`Venue`), and returns the fake.

The venue answers as the rail does from a duty's own wallet: every command is
queued under its key and settled on the ledger, a resting order sits in
`openOrders` until something fills or cancels it, an immediate-or-cancel order
fills against the scripted book, and an RFQ fills only when the scripted maker
quote is inside the bound.
"""

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent

START = 1795000000  # 2026-11-17T09:46:40Z
PUT = "ETH-20261204-3000-P"
CALL = "ETH-20261204-3500-C"


class BevoError(Exception):
    pass


def num(argv, flag):
    return float(argv[argv.index(flag) + 1]) if flag in argv else None


class Venue:
    """One duty wallet's Derive account and the market for one option."""

    def __init__(self, instrument=PUT, free=10000.0, position=0.0, book=None, makers=None,
                 hits=None, refuse=None, unknown=(), orders_unread=False, cash=0.0,
                 fee_rate=0.5, rfq_seconds=25):
        self.instrument = instrument
        self.free = free
        self.position = position
        self.entry = None
        #: [(from time, {mark, bid, ask, index[, asOf]})]: the book from that time on.
        self.book = sorted(book or [(0, {"mark": 52.0, "bid": 48.5, "ask": 55.0, "index": 3100.0})],
                           key=lambda b: b[0])
        #: [(from time, price)]: the best maker quote an RFQ gets from that time on.
        self.makers = sorted(makers or [], key=lambda m: m[0])
        #: [(at time, size)]: a taker trades against our resting order at that time.
        self.hits = sorted(hits or [], key=lambda h: h[0])
        self.refuse = dict(refuse or {})
        self.unknown = set(unknown)
        self.orders_unread = orders_unread
        self.cash = cash
        #: A taker's fee is $0.50 an order and `fee_rate` a contract: $1.50 on the 2 contracts
        #: of `params()`, its FEE_USD.
        self.fee_rate = fee_rate
        self.rfq_seconds = rfq_seconds
        self.orders = {}
        self.ledger = {}
        self.commands = []
        self.next_id = 1
        self.now = 0
        #: Seconds of real time the commands have taken, for the duty's own stopwatch.
        self.clock = 0.0

    def quote(self):
        live = [b for at, b in self.book if at <= self.now]
        return dict(live[-1] if live else self.book[0][1])

    def maker(self):
        live = [p for at, p in self.makers if at <= self.now]
        return live[-1] if live else None

    def fill(self, side, size, price):
        # Derive's entryPricePerUnitUsd carries the fee: a 0.1 put bought for $0.56 plus a
        # $0.55 fee read back as $11.17 (live, 2026-11-20).
        each = (0.5 + self.fee_rate * size) / size
        price = price + each if side == "buy" else price - each
        signed = size if side == "buy" else -size
        before = self.position
        self.position = round(self.position + signed, 10)
        if before == 0 or (before > 0) == (signed > 0):
            total = abs(before) * (self.entry or 0) + size * price
            self.entry = total / abs(self.position) if self.position else None

    def tick(self, now):
        """Takers reach our resting orders up to `now`."""
        self.now = now
        due = [h for h in self.hits if h[0] <= now]
        self.hits = [h for h in self.hits if h[0] > now]
        for _, size in due:
            for order in list(self.orders.values()):
                take = min(size, order["size"] - order["filledSize"])
                if take <= 0:
                    continue
                order["filledSize"] = round(order["filledSize"] + take, 10)
                self.fill(order["side"], take, order["limitPricePerUnitUsd"])
                if order["filledSize"] >= order["size"] - 1e-12:
                    del self.orders[order["orderId"]]
                break

    def side(self, argv):
        if argv[0] == "open":
            return "sell"
        if argv[0] == "buy":
            return "buy"
        return "sell" if "--min-proceeds" in argv else "buy"

    def run(self, argv, key):
        self.commands.append((self.now, list(argv)))
        self.clock += self.rfq_seconds if "rfq" in argv else 4
        if key in self.ledger:
            return  # same key, same outcome: never a second order
        self.execute(argv, key)
        if any(key.endswith(u) for u in self.unknown):
            # It ran, but the answer was lost: the ledger cannot say.
            self.ledger[key] = {"state": "unknown", "response": None}

    def execute(self, argv, key):
        verb = argv[0]
        if verb in self.refuse:
            self.ledger[key] = {"state": "refused", "response": {"code": self.refuse[verb]}}
            return
        if verb == "deposit":
            amount = num(argv, "--amount")
            self.cash -= amount
            self.free += amount
            self.ledger[key] = {"state": "executed", "response": {"outcome": {}}}
            return
        if verb == "cancel":
            order_id = argv[argv.index("--order") + 1]
            order = self.orders.pop(order_id, None)
            if order is None:
                self.ledger[key] = {"state": "refused", "response": {"code": "OPTIONS_ORDER_NOT_FOUND"}}
            else:
                self.ledger[key] = {"state": "executed", "response": {"outcome": {
                    "orderId": order_id, "orderStatus": "cancelled", "filledSize": order["filledSize"]}}}
            return
        side, size = self.side(argv), num(argv, "--size")
        book = self.quote()
        if "--order" in argv and argv[argv.index("--order") + 1] == "post-only":
            price = num(argv, "--min-price") or num(argv, "--max-price")
            crosses = price <= book["bid"] if side == "sell" else price >= book["ask"]
            if crosses:
                self.ledger[key] = {"state": "refused", "response": {"code": "OPTIONS_NOT_FILLED"}}
                return
            order_id = "o-%d" % self.next_id
            self.next_id += 1
            self.orders[order_id] = {"orderId": order_id, "instrument": self.instrument, "side": side,
                                     "size": size, "filledSize": 0.0, "limitPricePerUnitUsd": price,
                                     "status": "open"}
            self.ledger[key] = {"state": "executed", "response": {"outcome": {
                "resting": True, "order": {"orderId": order_id}}}}
            return
        rfq = "--order" in argv and argv[argv.index("--order") + 1] == "rfq"
        price = self.maker() if rfq else (book["bid"] if side == "sell" else book["ask"])
        bound = num(argv, "--min-premium") or num(argv, "--min-proceeds") or num(argv, "--max-cost")
        fee = 0.5 + self.fee_rate * size
        ok = price is not None and (price * size - fee >= bound if side == "sell" else price * size + fee <= bound)
        if not ok:
            said = "Nothing traded."
            if rfq and price is not None:
                # The rail names the best quote, fees included, for the whole size.
                said = ("the best quote pays $%.2f after fees, under the approved $%.2f" % (price * size - fee, bound)
                        if side == "sell" else
                        "the best quote costs $%.2f with fees, over the approved $%.2f" % (price * size + fee, bound))
            self.ledger[key] = {"state": "refused", "response": {"code": "OPTIONS_NOT_FILLED", "error": said}}
            return
        self.fill(side, size, price)
        self.ledger[key] = {"state": "executed", "response": {"outcome": {
            "trade": {"size": size, "grossUsd": round(price * size, 2)}}}}

    def account(self):
        positions = []
        if self.position:
            positions.append({"instrument": self.instrument, "size": self.position,
                              "entryPricePerUnitUsd": self.entry})
        held = sum(o["size"] * 3000 for o in self.orders.values() if o["side"] == "sell")
        return {"account": {"exists": True, "freeForNewPutsUsd": self.free - held,
                            "positions": positions, "openOrders": list(self.orders.values()),
                            **({"ordersUnread": True} if self.orders_unread else {})}}

    def ticker(self):
        book = self.quote()
        return {"instrument": self.instrument, "mark": str(book["mark"]), "index": str(book["index"]),
                "bid": str(book["bid"]) if book.get("bid") else None,
                "ask": str(book["ask"]) if book.get("ask") else None,
                "asOf": book.get("asOf", self.now) * 1000}


class Balance:
    def __init__(self, cash):
        self.cash_usd = cash


class FakeBevo:
    BevoError = BevoError
    SERVICE_ID = "duty-1"

    def __init__(self, times, venue, state, unreadable=()):
        self.times = list(times)
        self.venue = venue
        self.state = dict(state)
        self.unreadable = set(unreadable)
        self.now = self.times[0]
        self.logs, self.notes, self.pushes, self.fails, self.statuses = [], [], [], [], []
        self.finished = None

    def log(self, message):
        self.logs.append(str(message))

    def notify(self, text, quiet=False, push=None):
        self.notes.append(str(text))
        self.pushes.append(push)
        return {"ok": True}

    def fail(self, reason):
        self.fails.append(str(reason))

    def done(self, summary=None, **_values):
        self.finished = str(summary)
        raise SystemExit(0)

    def status(self, next, last=None, next_at=None, **values):
        self.statuses.append((next, values))

    def key(self, *parts):
        return ":".join(str(p) for p in parts)

    def read(self, path, params=None):
        if path in self.unreadable:
            raise BevoError("unreadable")
        if path == "/options/account":
            return self.venue.account()
        if path == "/options/ticker":
            return self.venue.ticker()
        raise BevoError("no fixture for %s" % path)

    def balance(self):
        return Balance(self.venue.cash)

    def exec_status(self, key, route="trade"):
        row = self.venue.ledger.get(key)
        return dict(row) if row else {"state": "not_found"}

    def settled(self, key, route=None, wait=0, again=False):
        state = (self.venue.ledger.get(key) or {}).get("state")
        return {"executed": "executed", "refused": "dropped", "unknown": "unknown"}.get(state, "waiting")

    def spawned(self, argv, **_kwargs):
        if list(argv[:2]) != ["acp", "options"]:
            raise AssertionError("unexpected command %r" % (argv,))
        args = list(argv[2:])
        key = args[args.index("--idempotency-key") + 1]
        del args[args.index("--idempotency-key"):args.index("--idempotency-key") + 2]
        self.venue.run(args, key)
        return subprocess.CompletedProcess(argv, 0, json.dumps({"status": "queued", "idempotencyKey": key}), "")

    def ticks(self):
        for at in self.times[1:]:
            self.now = at
            self.venue.tick(at)
            yield {"kind": "timer"}

    def placed(self, verb=None):
        """The commands the venue received, as (time from START in minutes, argv)."""
        return [((at - START) / 60.0, argv) for at, argv in self.venue.commands
                if verb is None or argv[0] == verb]


def params(**overrides):
    base = {"INSTRUMENT": PUT, "ACTION": "open", "SIZE": 2, "WORST_PRICE": 47, "FEE_USD": 1.5,
            "WORK_MINUTES": 120, "STEP_MINUTES": 30, "SIZE_STEP": 0.01, "MIN_SIZE": 0.1,
            "FILL_NOW_PRICE": 47}
    base.update(overrides)
    return base


def run(times, venue=None, settings=None, state=None, unreadable=()):
    venue = venue or Venue()
    venue.now = times[0]
    fake = FakeBevo(times, venue, state or {}, unreadable)
    sys.modules["bevo"] = fake
    spec = importlib.util.spec_from_file_location("duty_under_test", ROOT / "duty.py")
    module = importlib.util.module_from_spec(spec)
    env = {"PARAMS": json.dumps(params(**(settings or {}))), "BEVO_SERVICE_NAME": "ETH put order"}
    with mock.patch("time.time", lambda: fake.now), mock.patch("time.sleep", lambda _s: None), \
            mock.patch("time.monotonic", lambda: venue.clock), \
            mock.patch("subprocess.run", fake.spawned), mock.patch.dict(os.environ, env):
        try:
            spec.loader.exec_module(module)
        except SystemExit:
            pass
    return fake


def minutes(count, start=START):
    """A tick a minute: the program's start, then `count` ticks."""
    return [start + i * 60 for i in range(count + 1)]


def at(minute):
    return START + minute * 60


BOOK = {"mark": 52.0, "bid": 48.5, "ask": 55.0, "index": 3100.0}


def book(**changes):
    return dict(BOOK, **changes)


def per_contract(argv):
    """The price per contract a command commits to, before fees."""
    size = num(argv, "--size")
    if "--min-price" in argv or "--max-price" in argv:
        return num(argv, "--min-price") or num(argv, "--max-price")
    bound = num(argv, "--min-premium") or num(argv, "--min-proceeds") or num(argv, "--max-cost")
    return bound / size


def orders(fake, kind):
    """(minute, argv) of each command of this kind: rest, rfq, take or cancel."""
    out = []
    for minute, argv in fake.placed():
        order = argv[argv.index("--order") + 1] if "--order" in argv and argv[0] != "cancel" else None
        found = ("cancel" if argv[0] == "cancel" else "rest" if order == "post-only"
                 else "rfq" if order == "rfq" else "take" if argv[0] != "deposit" else "deposit")
        if found == kind:
            out.append((minute, argv))
    return out


class TheExample(unittest.TestCase):
    """Harry's worked example: sell 2 ETH 3,000 puts, mark $52, bid $48.50."""

    def setUp(self):
        venue = Venue(book=[(0, BOOK), (at(12), book(mark=51.6))],
                      makers=[(0, 50.10), (at(25), 51.5)], hits=[(at(12), 0.5)])
        self.fake = run(minutes(40), venue)

    def test_it_asks_the_makers_for_half_the_gap_first_then_rests_at_the_mark_the_same_minute(self):
        first = self.fake.placed()[0]
        self.assertEqual((first[0], first[1][-2:]), (1, ["--order", "rfq"]))
        self.assertAlmostEqual(per_contract(first[1]), (50.25 * 2 - 1.5) / 2, places=2)
        rest = orders(self.fake, "rest")[0]
        self.assertEqual((rest[0], num(rest[1], "--min-price"), num(rest[1], "--size")), (1, 52.0, 2.0))

    def test_at_the_step_it_pulls_the_rest_and_a_maker_fills_it_in_one_minute(self):
        self.assertEqual([m for m, _ in orders(self.fake, "cancel")], [31])
        step = orders(self.fake, "rfq")[1]
        self.assertEqual((step[0], num(step[1], "--size")), (31, 1.5))
        self.assertLess(per_contract(step[1]), 52)
        self.assertGreater(per_contract(step[1]), 47)

    def test_the_receipt_gives_the_average_against_filling_at_once(self):
        self.assertEqual(self.fake.venue.position, -2.0)
        self.assertIn("Sold 2 of 2 %s" % PUT, self.fake.finished)
        self.assertIn("Average $51.62 each before fees, $4.62 each better than filling at once ($47.00), "
                      "$9.25 in all. Filled: 1.5 by a maker's quote, 0.5 on its resting order.",
                      self.fake.finished)

    def test_one_approval_and_no_card(self):
        self.assertEqual(self.fake.fails, [])


class Receipt(unittest.TestCase):
    # Live (2026-11-20): a maker sold 0.1 ETH 1,300 put at $5.60 against a $6.00 ask.
    # Derive's entry price ($11.17, fee included) made the receipt say "$5.17 each worse".
    def test_a_maker_fill_is_priced_before_fees(self):
        venue = Venue(instrument="ETH-20261204-1300-P",
                      book=[(0, book(mark=5.5, bid=5.3, ask=6.0, index=1744.7))], makers=[(at(16), 5.6)])
        fake = run(minutes(20), venue, {"INSTRUMENT": "ETH-20261204-1300-P", "ACTION": "buy", "SIZE": 0.1,
                                        "WORST_PRICE": 6.0, "FEE_USD": 0.56, "WORK_MINUTES": 20,
                                        "STEP_MINUTES": 5, "MIN_SIZE": 0.01, "FILL_NOW_PRICE": 6.0})
        self.assertIn("Bought 0.1 of 0.1 ETH-20261204-1300-P. Average about $5.60 each before fees, "
                      "$0.40 each better than filling at once ($6.00), $0.04 in all. "
                      "Filled: 0.1 by a maker's quote.", fake.finished)

    def test_a_resting_fill_is_priced_at_its_own_limit(self):
        venue = Venue(hits=[(at(5), 2.0)])
        fake = run(minutes(8), venue)
        self.assertIn("Average $52.00 each before fees, $5.00 each better", fake.finished)


class TheMakers(unittest.TestCase):
    LIVE = {"INSTRUMENT": "ETH-20261204-1300-P", "ACTION": "buy", "SIZE": 0.1, "WORST_PRICE": 6.0,
            "FEE_USD": 0.55, "WORK_MINUTES": 240, "MIN_SIZE": 0.01, "FILL_NOW_PRICE": 6.0}
    BOOK = {"mark": 5.5, "bid": 5.3, "ask": 6.0, "index": 1744.7}

    def venue(self, **kwargs):
        return Venue(instrument="ETH-20261204-1300-P", **kwargs)

    # Live (2026-11-20): the maker's $5.65 was there from the start, and the old
    # ladder reached it at its third step.
    def test_a_quote_that_saves_half_the_gap_is_taken_in_the_first_minute(self):
        fake = run(minutes(3), self.venue(book=[(0, self.BOOK)], makers=[(0, 5.6)]), self.LIVE)
        self.assertEqual([m for m, _ in fake.placed()], [1])
        self.assertIn("Average about $5.60 each before fees, $0.40 each better than filling at once ($6.00)",
                      fake.finished)

    # Live (2026-11-23): a close's floor of $0.98 less $0.56 came out $0.43, not $0.42,
    # and refused a maker paying exactly the line.
    def test_a_bound_on_the_cent_is_not_rounded_past_it(self):
        venue = self.venue(position=0.1, book=[(0, {"mark": 10.1, "bid": 9.5, "ask": 10.4, "index": 1742.0})],
                           makers=[(0, 9.8)], fee_rate=0.6)
        fake = run(minutes(2), venue, dict(self.LIVE, INSTRUMENT="ETH-20261204-1300-P", ACTION="close",
                                           WORST_PRICE=9.5, FILL_NOW_PRICE=9.5, FEE_USD=0.56))
        self.assertEqual(num(fake.placed()[0][1], "--min-proceeds"), 0.42)
        self.assertIn("Sold 0.1 of 0.1", fake.finished)

    def test_take_saving_1_waits_for_the_ladder_instead(self):
        fake = run(minutes(40), self.venue(book=[(0, self.BOOK)], makers=[(0, 5.65)]),
                   dict(self.LIVE, TAKE_SAVING=1))
        self.assertIsNone(fake.finished)
        self.assertEqual([m for m, _ in orders(fake, "rfq")], [1, 31])

    def test_a_quote_that_saves_less_is_left_and_the_order_rests_at_the_mark(self):
        fake = run(minutes(5), self.venue(book=[(0, self.BOOK)], makers=[(0, 5.9)]), self.LIVE)
        self.assertEqual([(m, a[a.index("--order") + 1]) for m, a in fake.placed()], [(1, "rfq"), (1, "post-only")])
        self.assertAlmostEqual(fake.state["quote"]["price"], 5.9, places=1)

    def test_the_makers_are_asked_again_as_soon_as_the_mark_makes_their_quote_fit(self):
        # Their $50.00 misses the $50.25 line; the mark then rises $1, and the same edge fits.
        venue = Venue(book=[(0, BOOK), (at(6), book(mark=53.0))], makers=[(0, 50.0), (at(6), 51.0)])
        fake = run(minutes(8), venue)
        self.assertEqual([m for m, _ in orders(fake, "rfq")], [1, 6])
        self.assertIn("Average $51.00 each", fake.finished)

    def test_silent_makers_are_asked_only_at_each_step(self):
        fake = run(minutes(65), Venue(book=[(0, BOOK), (at(6), book(mark=53.0))]))
        self.assertEqual([m for m, _ in orders(fake, "rfq")], [1, 31, 61])
        self.assertNotIn("quote", fake.state)

    def test_a_maker_dearer_than_the_book_is_never_taken(self):
        # At the deadline the ask is $5.70 and the maker wants $5.90, both inside the $6.00 worst.
        venue = self.venue(book=[(0, dict(self.BOOK, ask=6.4)), (at(9), dict(self.BOOK, ask=5.7, mark=5.5))],
                           makers=[(at(9), 5.9)])
        fake = run(minutes(12), venue, dict(self.LIVE, WORK_MINUTES=8, STEP_MINUTES=None))
        self.assertIn("Average about $5.70 each", fake.finished)
        self.assertIn("Filled: 0.1 from the book.", fake.finished)

    def test_a_maker_who_beats_a_book_that_reached_the_target_is_taken_first(self):
        venue = Venue(book=[(0, BOOK), (at(5), book(bid=52.5, ask=54.0))], makers=[(at(5), 52.9)])
        fake = run(minutes(8), venue)
        self.assertEqual(orders(fake, "take"), [])
        self.assertIn("Average $52.90 each", fake.finished)

    def test_a_slow_rfq_leaves_the_next_command_to_the_next_minute(self):
        venue = Venue(book=[(0, BOOK), (at(5), book(bid=52.5, ask=54.0))], rfq_seconds=45)
        fake = run(minutes(8), venue)
        self.assertEqual([m for m, _ in orders(fake, "rfq")], [1, 5])
        self.assertEqual([m for m, _ in orders(fake, "rest")], [2])
        self.assertEqual([m for m, _ in orders(fake, "take")], [6])

    def test_one_setting_makes_it_quick(self):
        fake = run(minutes(9), Venue(), {"WORK_MINUTES": 16, "STEP_MINUTES": None})
        self.assertEqual([m for m, _ in orders(fake, "rfq")], [1, 3, 5, 7, 9])


class NeverPastTheWorstPrice(unittest.TestCase):
    def test_a_book_under_the_worst_price_sells_nothing_and_finishes_at_the_deadline(self):
        venue = Venue(book=[(0, book(mark=46.0, bid=40.0))], makers=[(0, 45.0)])
        fake = run(minutes(130), venue)
        for _, argv in fake.placed():
            if argv[0] != "cancel":
                self.assertGreaterEqual(per_contract(argv) + 1e-9, 47 - 1.5 / 2, argv)
        self.assertEqual(venue.position, 0)
        self.assertIn("nothing filled, no one would buy at $47.00 or better by the deadline", fake.finished)

    def test_the_target_walks_toward_the_bid_and_stops_at_the_worst(self):
        venue = Venue(book=[(0, book(mark=52.0, bid=44.0))])
        fake = run(minutes(125), venue)
        rests = [num(argv, "--min-price") for _, argv in orders(fake, "rest")]
        self.assertEqual(rests[0], 52.0)
        self.assertEqual(rests, sorted(rests, reverse=True))
        self.assertGreaterEqual(min(rests), 47.0)

    def test_a_buy_never_pays_over_the_worst(self):
        venue = Venue(book=[(0, book(mark=52.0, ask=60.0))])
        fake = run(minutes(130), venue, {"ACTION": "buy", "WORST_PRICE": 56})
        for _, argv in fake.placed():
            if argv[0] != "cancel":
                self.assertLessEqual(per_contract(argv), 56 + 1.5 / 2 + 1e-9, argv)
        self.assertTrue(all(argv[0] == "buy" for _, argv in orders(fake, "rest")))


class FollowsTheMarket(unittest.TestCase):
    def test_a_bid_that_reaches_the_target_is_taken(self):
        venue = Venue(book=[(0, BOOK), (at(5), book(bid=52.5, ask=54.0))])
        fake = run(minutes(8), venue)
        self.assertEqual([m for m, _ in orders(fake, "cancel")], [5])
        self.assertEqual([m for m, _ in orders(fake, "take")], [5])
        self.assertEqual(venue.position, -2.0)
        self.assertIn("Sold 2 of 2", fake.finished)
        self.assertIn("Filled: 2 from the book.", fake.finished)

    def test_a_mark_that_moves_more_than_1pct_is_followed(self):
        venue = Venue(book=[(0, BOOK), (at(10), book(mark=50.0))])
        fake = run(minutes(14), venue)
        self.assertEqual([m for m, _ in orders(fake, "cancel")], [10])
        self.assertEqual([num(a, "--min-price") for _, a in orders(fake, "rest")], [52.0, 50.0])

    # Live (2026-11-20): an ETH 2,100 call's mark flickered $5.80 / $5.70 on a $0.10
    # tick, and the order was cancelled and placed again at the same $5.80.
    def test_a_mark_flickering_by_one_tick_leaves_the_order_where_it_is(self):
        flicker = [(at(m), book(mark=5.8 if m % 2 else 5.7, bid=5.5, ask=6.2, index=1744.6)) for m in range(0, 14)]
        venue = Venue(instrument=CALL, book=flicker)
        fake = run(minutes(13), venue, {"INSTRUMENT": CALL, "ACTION": "buy", "SIZE": 0.1, "WORST_PRICE": 5.9,
                                        "FEE_USD": 0.56, "FILL_NOW_PRICE": 5.9, "MIN_SIZE": 0.01})
        self.assertEqual(orders(fake, "cancel"), [])
        self.assertEqual(len(orders(fake, "rest")), 1)

    def test_a_resting_buy_rests_on_the_tick_below_its_target(self):
        venue = Venue(book=[(0, book(mark=52.04))])
        fake = run(minutes(3), venue, {"ACTION": "buy", "WORST_PRICE": 56})
        self.assertEqual(num(orders(fake, "rest")[0][1], "--max-price"), 52.0)

    def test_a_small_mark_move_leaves_the_order_where_it_is(self):
        venue = Venue(book=[(0, BOOK), (at(10), book(mark=51.8))])
        fake = run(minutes(14), venue)
        self.assertEqual(orders(fake, "cancel"), [])

    def test_a_fast_index_move_against_a_sold_put_pulls_it_for_15_calm_minutes(self):
        venue = Venue(book=[(0, BOOK), (at(10), book(index=3085.0))])
        fake = run(minutes(29), venue)
        self.assertEqual([m for m, _ in orders(fake, "cancel")], [10])
        self.assertEqual([m for m, _ in orders(fake, "rest")], [1, 25])
        self.assertIn(("paused", {"filled": "0", "size": "2"}), fake.statuses)

    def test_a_slow_drift_is_followed_by_repricing_not_a_pause(self):
        drift = [(at(m), book(index=3100.0 - 1.5 * m)) for m in range(0, 15)]  # 0.45% over 14 minutes
        fake = run(minutes(14), Venue(book=drift))
        self.assertEqual(orders(fake, "cancel"), [])
        self.assertNotIn("paused", [state for state, _ in fake.statuses])

    # Live (2026-11-20): a bought ETH call, the index 0.37% lower seven minutes in. The
    # 30-minute window then paused it to its deadline and skipped two maker-quote steps.
    def test_a_pause_still_asks_the_makers_at_each_step(self):
        venue = Venue(instrument=CALL, book=[(0, BOOK), (at(4), book(index=3088.0))])
        fake = run(minutes(14), venue, {"INSTRUMENT": CALL, "ACTION": "buy", "WORST_PRICE": 55,
                                        "WORK_MINUTES": 20, "STEP_MINUTES": 5})
        self.assertEqual([m for m, _ in orders(fake, "cancel")], [4])
        self.assertEqual([m for m, _ in orders(fake, "rfq")], [1, 6, 11])
        self.assertEqual([m for m, _ in orders(fake, "rest")], [1])

    def test_the_index_moving_the_owners_way_changes_nothing(self):
        venue = Venue(book=[(0, BOOK), (at(10), book(index=3130.0))])
        fake = run(minutes(14), venue)
        self.assertEqual(orders(fake, "cancel"), [])

    def test_a_bought_call_is_pulled_when_the_index_falls(self):
        venue = Venue(instrument=CALL, book=[(0, BOOK), (at(10), book(index=3085.0))])
        fake = run(minutes(12), venue, {"INSTRUMENT": CALL, "ACTION": "buy", "WORST_PRICE": 55})
        self.assertEqual([m for m, _ in orders(fake, "cancel")], [10])

    def test_stale_prices_pull_the_order(self):
        venue = Venue(book=[(0, BOOK), (at(6), book(asOf=at(2)))])
        fake = run(minutes(8), venue)
        self.assertEqual([m for m, _ in orders(fake, "cancel")], [6])
        self.assertEqual([m for m, _ in orders(fake, "rest")], [1])

    def test_prices_unread_for_over_two_minutes_pull_the_order(self):
        venue = Venue()
        fake = run(minutes(3), venue)
        self.assertEqual(len(venue.orders), 1)
        fake = run([at(4), at(5), at(6), at(8)], venue, state=fake.state, unreadable={"/options/ticker"})
        self.assertEqual([m for m, _ in orders(fake, "cancel")], [6])


class PartFills(unittest.TestCase):
    def test_a_part_fill_is_counted_from_the_position_and_the_rest_keeps_resting(self):
        venue = Venue(hits=[(at(5), 0.7)])
        fake = run(minutes(8), venue)
        self.assertEqual(venue.position, -0.7)
        self.assertIn("ETH put order: 0.7 of 2 filled so far.", fake.notes)
        self.assertEqual(len(orders(fake, "rest")), 1)
        self.assertEqual(fake.statuses[-1], ("working", {"filled": "0.7", "size": "2", "price": 52.0}))

    def test_a_resting_order_whose_answer_was_lost_is_found_and_not_placed_twice(self):
        venue = Venue(unknown={":1:rest"})
        fake = run(minutes(6), venue)
        self.assertEqual(len(orders(fake, "rest")), 1)
        self.assertEqual(len(venue.orders), 1)
        self.assertEqual(fake.state.get("rest_id"), "o-1")

    def test_left_under_the_venue_minimum_finishes(self):
        venue = Venue(hits=[(at(5), 1.95)])
        fake = run(minutes(8), venue)
        self.assertIn("Sold 1.95 of 2", fake.finished)


class Close(unittest.TestCase):
    def test_a_close_never_rests_and_buys_back_by_rfq(self):
        venue = Venue(position=-2.0, book=[(0, book(ask=56.0))], makers=[(at(31), 52.5)])
        fake = run(minutes(35), venue, {"ACTION": "close", "WORST_PRICE": 56, "FILL_NOW_PRICE": 56})
        self.assertEqual(orders(fake, "rest"), [])
        self.assertTrue(all("--max-cost" in a for _, a in orders(fake, "rfq")))
        self.assertEqual(venue.position, 0)
        self.assertIn("Bought 2 of 2", fake.finished)
        self.assertIn("Average $52.50 each before fees, $3.50 each better than filling at once ($56.00)",
                      fake.finished)

    # Live (2026-11-20): a 0.1 ETH 1,400 put sold back at the deadline for $0.81.
    def test_a_close_sold_back_on_the_book_at_the_deadline(self):
        venue = Venue(instrument="ETH-20261204-1400-P", position=0.1,
                      book=[(0, book(mark=8.4, bid=8.1, ask=8.8, index=1752.5))], makers=[(0, 7.0)])
        fake = run(minutes(9), venue, {"INSTRUMENT": "ETH-20261204-1400-P", "ACTION": "close", "SIZE": 0.1,
                                       "WORST_PRICE": 7.9, "FEE_USD": 0.56, "WORK_MINUTES": 6,
                                       "STEP_MINUTES": 2, "MIN_SIZE": 0.01, "FILL_NOW_PRICE": 7.9})
        self.assertEqual(venue.position, 0)
        self.assertIn("Sold 0.1 of 0.1 ETH-20261204-1400-P. Average about $8.10 each", fake.finished)

    def test_a_close_with_nothing_held_finishes_at_once(self):
        fake = run(minutes(2), Venue(), {"ACTION": "close"})
        self.assertEqual(fake.placed(), [])
        self.assertIn("there is no %s position to close" % PUT, fake.finished)


class Deadline(unittest.TestCase):
    def test_at_the_deadline_it_pulls_the_rest_asks_the_makers_then_the_book_at_the_worst(self):
        venue = Venue(book=[(0, book(bid=45.0))])
        fake = run(minutes(125), venue)
        late = [(m, a[0], a[-1]) for m, a in fake.placed() if m >= 121]
        self.assertEqual([x[0] for x in late], [121, 121, 121])
        self.assertEqual(late[0][1], "cancel")
        self.assertEqual(late[1][2], "rfq")
        self.assertAlmostEqual(per_contract(fake.placed()[-1][1]), (47 * 2 - 1.5) / 2, places=2)

    def test_it_finishes_an_hour_before_expiry_whatever_the_minutes_say(self):
        expiry = 1796371200  # ETH-20261204 at 08:00 UTC
        start = expiry - 3 * 3600
        venue = Venue()
        fake = run([start + i * 60 for i in range(125)], venue, {"WORK_MINUTES": 600})
        self.assertAlmostEqual(fake.state["deadline"], expiry - 3600, delta=60)


class Funding(unittest.TestCase):
    def test_it_deposits_its_wallet_then_starts(self):
        venue = Venue(free=0.0, cash=15.0)
        fake = run(minutes(3), venue, {"ACTION": "buy", "SIZE": 0.1, "WORST_PRICE": 56, "FEE_USD": 0.6})
        self.assertEqual(orders(fake, "deposit")[0][1][:3], ["deposit", "--amount", "15"])
        self.assertTrue(fake.notes[0].startswith("ETH put order: working your order to buy 0.1"))

    def test_an_empty_wallet_waits_and_says_so_once(self):
        fake = run(minutes(45), Venue(free=0.0), {"ACTION": "buy"})
        self.assertEqual(fake.placed(), [])
        self.assertEqual(len([n for n in fake.notes if "has not started" in n]), 1)


class Stops(unittest.TestCase):
    def test_bad_settings_send_nothing(self):
        fake = run(minutes(2), Venue(), {"INSTRUMENT": "ETH-PUT"})
        self.assertEqual(fake.placed(), [])
        self.assertTrue(fake.fails[0].startswith("settings: INSTRUMENT"))

    def test_options_off_for_duties_stops_it_with_one_note(self):
        venue = Venue(refuse={"open": "OPTIONS_DUTY_OFF"})
        fake = run(minutes(5), venue)
        self.assertEqual(len(fake.placed()), 1)
        self.assertIn("stopped", fake.finished)


class NothingLeftResting(unittest.TestCase):
    def test_stop_cancels_the_resting_order_and_sends_the_receipt(self):
        venue = Venue(hits=[(at(5), 0.7)])
        first = run(minutes(6), venue)
        self.assertEqual(len(venue.orders), 1)
        fake = run([at(7), at(8)], venue, {"STOP": True}, state=first.state)
        self.assertEqual(venue.orders, {})
        self.assertEqual([a[0] for _, a in fake.placed() if _ >= 8], ["cancel"])
        self.assertIn("Sold 0.7 of 2", fake.finished)
        self.assertIn("Stopped: you stopped it.", fake.finished)

    def test_stop_is_the_same_order_not_a_new_one(self):
        first = run(minutes(3), Venue())
        fake = run([at(4), at(5)], first.venue, {"STOP": "true"}, state=first.state)
        self.assertEqual(fake.state["order"], first.state["order"])
        self.assertIn("nothing filled, you stopped it", fake.finished)

    def test_stop_before_it_started_trades_nothing(self):
        fake = run(minutes(2), Venue(free=0.0), {"STOP": True})
        self.assertEqual(fake.placed(), [])
        self.assertIn("nothing filled, you stopped it", fake.finished)

    def test_a_remainder_under_the_minimum_is_cancelled_before_it_finishes(self):
        venue = Venue(hits=[(at(5), 1.95)])
        fake = run(minutes(8), venue)
        self.assertEqual(venue.orders, {})
        self.assertIn("Sold 1.95 of 2", fake.finished)

    def test_an_order_an_earlier_option_left_behind_is_cancelled_first(self):
        venue = Venue()
        first = run(minutes(3), venue)
        self.assertEqual(len(venue.orders), 1)
        venue.instrument = CALL
        fake = run([at(4), at(5)], venue, {"INSTRUMENT": CALL, "ACTION": "buy", "WORST_PRICE": 55},
                   state=first.state)
        later = [argv for minute, argv in fake.placed() if minute >= 4]
        self.assertEqual(later[0][:3], ["cancel", "--order", "o-1"])
        self.assertEqual([o["instrument"] for o in venue.orders.values()], [CALL])

    def test_an_order_the_account_cannot_show_is_never_called_gone(self):
        first = run(minutes(3), Venue())
        first.venue.orders_unread = True
        fake = run([at(4), at(5)], first.venue, {"STOP": True}, state=first.state)
        self.assertIsNone(fake.finished)
        self.assertEqual(len(first.venue.orders), 1)


class NewSettings(unittest.TestCase):
    def test_new_settings_are_a_new_order_with_new_keys(self):
        venue = Venue(makers=[(0, 53.0)])
        first = run(minutes(2), venue, {"SIZE": 1})
        self.assertIn("Sold 1 of 1", first.finished)
        again = run([at(5), at(6), at(7)], venue, {"SIZE": 0.5}, state=first.state)
        keys = list(venue.ledger)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(venue.position, -1.5)
        self.assertIn("Sold 0.5 of 0.5", again.finished)

    def test_the_same_settings_carry_on_where_they_were(self):
        venue = Venue()
        first = run(minutes(3), venue)
        again = run([at(4), at(5)], venue, state=first.state)
        self.assertEqual(len(orders(again, "rest")), 1)


if __name__ == "__main__":
    unittest.main()
