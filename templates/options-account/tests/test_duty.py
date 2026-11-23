"""duty.py run against scripted reads and clocks.

    python3 -m unittest discover -s tests -v

The first half is the stand-in for the `bevo` SDK the tests run duty.py against:

A scripted stand-in for the `bevo` SDK, for running duty.py offline.

`run(...)` installs a fresh fake as `bevo`, pins the clock to each check's time
(the first is the check at start, the rest are ticks), makes the jitter sleep
free, executes duty.py to the end of its ticks, and returns the fake for
assertions.
"""

import ast
import importlib.util
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent

START = 1792915200  # 2026-10-25T00:00:00Z
WALLET = "0x00000000000000000000000000000000000000a1"


class BevoError(Exception):
    pass


class FakeBevo:
    BevoError = BevoError

    def __init__(self, times, reads, state, platforms=None, refuse=()):
        self.times = list(times)
        self.reads = {path: list(value) if isinstance(value, list) else value
                      for path, value in reads.items()}
        self.state = dict(state)
        self.now = self.times[0]
        self.platforms = [] if platforms is None else platforms
        self.refuse = set(refuse)
        self.logs, self.notes, self.pushes, self.fails = [], [], [], []
        self.statuses, self.rows, self.read_calls, self.removed = [], [], [], []

    def log(self, message):
        self.logs.append(str(message))

    def notify(self, text, quiet=False, push=None):
        self.notes.append(str(text))
        self.pushes.append(push)
        return {"ok": True}

    def fail(self, reason):
        self.fails.append(str(reason))

    def status(self, next, last=None, next_at=None, **values):
        self.statuses.append((next, values))

    def platform_balance(self, site, name, usd, account="", icon=None, positions=None):
        self.rows.append({"site": site, "name": name, "usd": usd, "account": account,
                          "positions": positions})
        # The SDK answers {} for a write the server refused (logged, never raised).
        return {} if account in self.refuse else {"id": "row-1"}

    def platform_balances(self):
        if isinstance(self.platforms, BaseException):
            raise self.platforms
        return list(self.platforms)

    def spawned(self, argv, **_kwargs):
        """`subprocess.run`: records `bevo-platforms remove <id>` instead of running it."""
        if list(argv[:2]) == ["bevo-platforms", "remove"]:
            self.removed.append(argv[2])
        return subprocess.CompletedProcess(argv, 0, "", "")

    def read(self, path, params=None):
        """A list fixture answers one item per call and repeats its last."""
        self.read_calls.append((path, dict(params or {})))
        value = self.reads.get(path)
        if isinstance(value, list):
            value = value.pop(0) if len(value) > 1 else value[0]
        if callable(value):
            value = value(params or {})
        if isinstance(value, BaseException):
            raise value
        if value is None:
            raise BevoError("no fixture for %s" % path)
        return value

    def ticks(self):
        for at in self.times[1:]:
            self.now = at
            yield {"kind": "timer"}


def run(times, reads=None, state=None, params=None, platforms=None, refuse=()):
    fake = FakeBevo(times, reads or {}, state or {}, platforms, refuse)
    sys.modules["bevo"] = fake
    spec = importlib.util.spec_from_file_location("duty_under_test", ROOT / "duty.py")
    module = importlib.util.module_from_spec(spec)
    env = {"PARAMS": json.dumps(params or {})}
    with mock.patch("time.time", lambda: fake.now), mock.patch("time.sleep", lambda _s: None), \
            mock.patch("subprocess.run", fake.spawned), mock.patch.dict(os.environ, env):
        spec.loader.exec_module(module)
    return fake


def every(minutes, count, start=START):
    return [start + i * minutes * 60 for i in range(count)]


DERIVE = "https://www.derive.xyz"
PARADEX = "https://www.paradex.trade"


def venue(vid, name, site, usdc="0", worth=None, positions=(), exists=True, late=False, cash=False):
    """One entry of `venues` in bevo-server's bare `/options/account` answer."""
    return {"venue": vid, "name": name, "site": site, "depositsLandLater": late, "cashLine": cash,
            "available": True,
            "wallet": WALLET, "signerReady": True,
            "account": {"exists": exists, "usdc": usdc, "positions": list(positions),
                        "worthUsd": worth},
            "lines": []}


def derive(usdc="0", worth=None, positions=(), exists=True, subs=None):
    entry = venue("derive", "Derive", DERIVE, usdc, worth, positions, exists, late=True)
    if subs is not None:
        entry["account"]["accounts"] = list(subs)
    return entry


def subaccount(universe, sub_id, usdc, worth, positions=()):
    """One entry of Derive's `account.accounts`: a risk universe's own subaccount."""
    return {"exists": True, "subaccountId": sub_id, "universe": universe, "usdc": usdc,
            "worthUsd": worth, "positions": list(positions)}


def platform(row_id, site, account):
    """A row as `bevo.platform_balances()` lists it."""
    host = site.split("://", 1)[1].split("/", 1)[0].lower()
    return {"id": row_id, "siteHost": host[4:] if host.startswith("www.") else host,
            "account": account}


def paradex(usdc="0", worth=None, positions=(), exists=True):
    return venue("paradex", "Paradex", PARADEX, usdc, worth, positions, exists, cash=True)


def accounts(*venues):
    """The bare read: Derive's legacy body at the top, every venue in `venues`."""
    return {"wallet": WALLET, "signerReady": True, "account": None, "venues": list(venues)}


def position(instrument, size, value, pnl=None):
    parts = instrument.split("-")
    strike = parts[-2]
    return {"instrument": instrument, "size": size, "underlying": parts[0],
            "strike": float(strike.replace("_", ".")), "type": parts[-1],
            "valueUsd": value, "pnlUsd": pnl, "expiresIn": "in 2 days"}



SOURCE = (Path(__file__).resolve().parent.parent / "duty.py").read_text()

CALL = "ETH-USD-6NOV26-2500-C"
PUT = "ETH-USD-23OCT26-2300-P"
DERIVE_CALL = "ETH-20261030-2550-C"


def rows(fake):
    return [(row["site"], row["name"], row["usd"]) for row in fake.rows]


class EveryVenue(unittest.TestCase):
    # Mainnet (2026-10-22): Derive worth 4.54, Paradex 13.93, a call open on each.
    def test_one_row_per_venue_at_its_own_worth_with_its_positions(self):
        body = accounts(derive("1.45", 4.541177, [position(DERIVE_CALL, 0.17, 3.1)]),
                        paradex("8.11", 13.932716, [position(CALL, 0.1, 5.82, pnl=0.07), position(PUT, -0.2, 1.2)]))
        fake = run([0], {"/options/account": body})
        self.assertEqual(rows(fake), [(DERIVE, "Derive", 4.54), (PARADEX, "Paradex", 13.93)])
        self.assertEqual({row["account"] for row in fake.rows}, {WALLET})
        self.assertEqual([p["title"] for p in fake.rows[1]["positions"]],
                         ["Cash", "Bought 0.1 ETH 2,500 call", "Sold 0.2 ETH 2,300 put"])
        self.assertEqual([p["valueUsd"] for p in fake.rows[1]["positions"]], [8.11, 5.82, -1.2])
        self.assertEqual(fake.rows[1]["positions"][1]["details"],
                         [{"label": "Expires", "value": "in 2 days"}, {"label": "Up/down", "value": "$0.07"}])
        self.assertEqual(fake.statuses, [("ok", {"value": 18.47, "positions": 3})])

    def test_one_bare_read_answers_for_every_venue(self):
        fake = run([0], {"/options/account": accounts(derive("5", 5), paradex("5", 5))})
        self.assertEqual(fake.read_calls, [("/options/account", {})])

    def test_a_venue_the_server_adds_is_written_with_nothing_refiled(self):
        later = venue("aevo", "Aevo", "https://www.aevo.xyz", "3", 3)
        fake = run([0], {"/options/account": accounts(derive("5", 5), later)})
        self.assertEqual(rows(fake), [(DERIVE, "Derive", 5), ("https://www.aevo.xyz", "Aevo", 3)])

    def test_only_a_venue_that_exists_gets_a_row(self):
        fake = run([0], {"/options/account": accounts(derive(exists=False), paradex("7", 7))})
        self.assertEqual(rows(fake), [(PARADEX, "Paradex", 7)])

    def test_an_empty_account_that_reads_fine_is_a_real_zero(self):
        fake = run([0], {"/options/account": accounts(paradex("0", 0))})
        self.assertEqual((fake.rows[0]["usd"], fake.rows[0]["positions"]),
                         (0, [{"title": "Cash", "valueUsd": 0}]))

    # Mainnet (2026-10-26): $9.26 on Paradex, $7.30 of it a call, so $1.96 free.
    def test_a_venue_holding_its_cash_lists_it_first_and_counts_it_as_no_position(self):
        fake = run([0], {"/options/account": accounts(paradex("1.964", 9.264, [position(CALL, 0.01, 7.3)]))})
        self.assertEqual([(p["title"], p["valueUsd"]) for p in fake.rows[0]["positions"]],
                         [("Cash", 1.96), ("Bought 0.01 ETH 2,500 call", 7.3)])
        self.assertEqual(fake.statuses, [("ok", {"value": 9.26, "positions": 1})])

    def test_cash_stays_inside_the_twenty_line_limit(self):
        many = [position("ETH-USD-6NOV26-%d-C" % (2000 + i), 0.1, 1) for i in range(25)]
        line = run([0], {"/options/account": accounts(paradex("3", 28, many))}).rows[0]["positions"]
        self.assertEqual((len(line), line[0]["title"]), (20, "Cash"))

    def test_checks_at_start_and_on_every_tick(self):
        fake = run(every(10, 3), {"/options/account": accounts(paradex("5", 5))})
        self.assertEqual(len(fake.rows), 3)


RYSK = "https://app.rysk.finance"


def sold_put(instrument="SOL-30OCT26-93-P", size=10, received=2.15, expires="in 3 days"):
    # Butler's server reads Rysk with no mark, so no value and no P&L; `costUsd` is the premium received.
    parts = instrument.split("-")
    return {"instrument": instrument, "size": -size, "underlying": parts[0], "strike": float(parts[2]),
            "type": "P", "valueUsd": None, "costUsd": received, "pnlUsd": None, "expiresIn": expires}


class Unmarked(unittest.TestCase):
    # Mainnet (2026-10-26): a sold SOL put on Rysk, which marks no position.
    def test_a_position_with_no_mark_is_listed_without_a_value(self):
        rysk = venue("rysk", "Rysk", RYSK, "0", 930, [sold_put()])
        fake = run([0], {"/options/account": accounts(rysk)})
        self.assertEqual(rows(fake), [(RYSK, "Rysk", 930)])
        self.assertEqual(fake.rows[0]["positions"], [{
            "title": "Sold 10 SOL 93 put", "subtitle": "SOL-30OCT26-93-P",
            "details": [{"label": "Expires", "value": "in 3 days"}, {"label": "Received", "value": "$2.15"},
                        {"label": "Collateral", "value": "$930.00"}]}])
        self.assertEqual(fake.statuses, [("ok", {"value": 930, "positions": 1})])

    def test_an_expired_unsettled_one_awaits_settlement(self):
        rysk = venue("rysk", "Rysk", RYSK, "0", 930, [sold_put(expires="expired")])
        line = run([0], {"/options/account": accounts(rysk)}).rows[0]["positions"][0]
        self.assertEqual(line["status"], "Awaiting settlement")
        self.assertNotIn("Expires", [d["label"] for d in line["details"]])


def split_derive(prime_worth=51.53, rwa_worth=6.58):
    # Mainnet (2026-10-26): PRIME holds ETH options, RWA a XAUT call.
    prime = subaccount("PRIME", 1, 17.02, prime_worth, [position("ETH-20261030-2700-C", 0.1, 0.13),
                                                        position("ETH-20261030-2450-P", 0.24, 34.38)])
    rwa = subaccount("RWA", 2, 0, rwa_worth, [position("XAUT-20261113-4200-C", 0.23, 6.58)])
    return derive("17.02", 58.11, subs=[prime, rwa])


class Subaccounts(unittest.TestCase):
    def test_one_row_per_subaccount_at_its_own_worth_cash_first(self):
        fake = run([0], {"/options/account": accounts(split_derive())})
        self.assertEqual([(row["account"], row["usd"]) for row in fake.rows], [("PRIME", 51.53), ("RWA", 6.58)])
        self.assertEqual({(row["site"], row["name"]) for row in fake.rows}, {(DERIVE, "Derive")})
        self.assertEqual([(p["title"], p["valueUsd"]) for p in fake.rows[0]["positions"]],
                         [("Cash", 17.02), ("Bought 0.1 ETH 2,700 call", 0.13), ("Bought 0.24 ETH 2,450 put", 34.38)])
        self.assertEqual([(p["title"], p["valueUsd"]) for p in fake.rows[1]["positions"]],
                         [("Cash", 0), ("Bought 0.23 XAUT 4,200 call", 6.58)])
        self.assertEqual(fake.statuses, [("ok", {"value": 58.11, "positions": 3})])

    def test_the_venue_row_and_a_gone_subaccount_are_retired_and_nothing_else(self):
        existing = [platform("old", DERIVE, WALLET), platform("alt", DERIVE, "ALT"),
                    platform("prime", DERIVE, "PRIME"), platform("px", PARADEX, WALLET),
                    platform("stake", "https://stake.com", "")]
        fake = run([0], {"/options/account": accounts(split_derive(), paradex("5", 5))}, platforms=existing)
        self.assertEqual(fake.removed, ["old", "alt"])

    def test_a_row_the_server_keeps_is_never_retired(self):
        kept = dict(platform("duty", DERIVE, "0x00000000000000000000000000000000000000d7"), serverKept=True)
        existing = [platform("old", DERIVE, WALLET), kept, platform("prime", DERIVE, "PRIME")]
        fake = run([0], {"/options/account": accounts(split_derive())}, platforms=existing)
        self.assertEqual(fake.removed, ["old"])

    def test_nothing_is_retired_while_a_subaccount_row_is_unsaved(self):
        fake = run([0], {"/options/account": accounts(split_derive())},
                   platforms=[platform("old", DERIVE, WALLET)], refuse={"RWA"})
        self.assertEqual(fake.removed, [])

    def test_a_subaccount_with_no_worth_keeps_every_row(self):
        fake = run([0], {"/options/account": accounts(split_derive(rwa_worth=None), paradex("5", 5))},
                   platforms=[platform("old", DERIVE, WALLET)])
        self.assertEqual(rows(fake), [(PARADEX, "Paradex", 5)])
        self.assertEqual(fake.removed, [])
        self.assertEqual(fake.statuses, [("partial", {"value": 5, "skipped": 1})])

    def test_rows_that_cannot_be_listed_are_left_and_the_check_still_reports(self):
        fake = run([0], {"/options/account": accounts(split_derive())}, platforms=BevoError("503"))
        self.assertEqual(fake.removed, [])
        self.assertTrue(any("none was retired" in line for line in fake.logs))
        self.assertEqual(fake.statuses, [("ok", {"value": 58.11, "positions": 3})])


class OneVenueMissed(unittest.TestCase):
    def test_an_unreadable_venue_keeps_its_row_and_the_rest_are_written(self):
        down = dict(paradex(), available=False, error="Paradex answered 502")
        fake = run([0], {"/options/account": accounts(derive("5", 5), down)})
        self.assertEqual(rows(fake), [(DERIVE, "Derive", 5)])
        self.assertEqual(fake.statuses, [("partial", {"value": 5, "skipped": 1})])
        self.assertTrue(any("Paradex answered 502" in line for line in fake.logs))

    def test_a_venue_with_no_worth_keeps_its_row(self):
        fake = run([0], {"/options/account": accounts(derive("5", 5), paradex("5", None))})
        self.assertEqual(rows(fake), [(DERIVE, "Derive", 5)])
        self.assertEqual(fake.statuses, [("partial", {"value": 5, "skipped": 1})])

    def test_a_venue_this_server_does_not_trade_is_left_out_quietly(self):
        off = dict(paradex(), available=False, reason="not configured on this server")
        fake = run([0], {"/options/account": accounts(derive("5", 5), off)})
        self.assertEqual(fake.statuses, [("ok", {"value": 5, "positions": 0})])


class DepositNote(unittest.TestCase):
    def test_a_rise_on_a_venue_whose_deposits_land_later_is_noted(self):
        fake = run(every(10, 2), {"/options/account": [accounts(derive("5", 5)), accounts(derive("55", 55))]})
        self.assertEqual(fake.notes, ["Your Derive deposit landed: $50.00 USDC credited. The account is worth $55.00 now."])
        self.assertEqual(fake.pushes, ["Derive deposit credited"])
        self.assertEqual(fake.statuses[-1], ("credited", {"credit": 50, "value": 55, "positions": 0}))

    def test_the_first_deposit_is_a_rise_from_zero(self):
        fake = run(every(10, 2), {"/options/account": [accounts(derive(exists=False)), accounts(derive("20", 20))]})
        self.assertEqual(len(fake.notes), 1)

    def test_a_venue_whose_card_reports_the_credit_gets_no_note(self):
        fake = run(every(10, 2), {"/options/account": [accounts(paradex("5", 5)), accounts(paradex("55", 55))]})
        self.assertEqual(fake.notes, [])

    def test_the_first_check_and_cash_from_a_close_are_not_deposits(self):
        held = [position(DERIVE_CALL, 0.17, 3.1)]
        fake = run(every(10, 3), {"/options/account": [accounts(derive("5", 8, held)), accounts(derive("9", 9)),
                                                       accounts(derive("9", 9))]})
        self.assertEqual(fake.notes, [])


class NothingWritten(unittest.TestCase):
    def assert_untouched(self, fake, state):
        self.assertEqual(fake.rows, [])
        self.assertEqual(fake.notes, [])
        self.assertEqual(fake.fails, [])
        self.assertEqual([s for s, _ in fake.statuses], [state])

    def test_an_unreadable_read(self):
        fake = run([0], {"/options/account": BevoError("503 OPTIONS_VENUE_UNAVAILABLE")})
        self.assert_untouched(fake, "unreadable")

    def test_a_read_listing_no_venues(self):
        self.assert_untouched(run([0], {"/options/account": {"account": None}}), "unreadable")

    def test_a_venue_without_a_site(self):
        body = accounts(dict(paradex("5", 5), site=None))
        self.assert_untouched(run([0], {"/options/account": body}), "unreadable")

    def test_the_signer_off(self):
        body = accounts(dict(derive(), account=None), dict(paradex(), account=None))
        self.assert_untouched(run([0], {"/options/account": body}), "signer_off")

    def test_no_account_yet(self):
        body = accounts(derive(exists=False), paradex(exists=False))
        self.assert_untouched(run([0], {"/options/account": body}), "no_account")

    def test_a_worth_below_zero(self):
        self.assert_untouched(run([0], {"/options/account": accounts(paradex("1", -3))}), "unpriced")

    def test_a_malformed_answer_is_logged_and_the_next_tick_still_runs(self):
        fake = run(every(10, 2), {"/options/account": [accounts(paradex("1", "not a number")),
                                                       accounts(paradex("7", 7))]})
        self.assertEqual(fake.fails, [])
        self.assertTrue(any(line.startswith("check skipped") for line in fake.logs))
        self.assertEqual([row["usd"] for row in fake.rows], [7])


class Source(unittest.TestCase):
    def test_imports_only_what_a_reader_needs(self):
        imported = set()
        for node in ast.walk(ast.parse(SOURCE)):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module)
        self.assertEqual(imported, {"bevo", "random", "subprocess", "time"})

    def test_names_no_venue_and_never_fails_or_runs_acp(self):
        called = {node.func.attr for node in ast.walk(ast.parse(SOURCE))
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertNotIn("fail", called)
        self.assertNotIn('"acp"', SOURCE)
        for name in ("derive", "paradex"):
            self.assertNotIn('"%s' % name, SOURCE.lower())


if __name__ == "__main__":
    unittest.main()


# Staging (2026-11-06): a $10 resting bid for 0.95 ETH-20261127-2600-C on Derive's
# PRIME, which the Platforms row did not show. The line is the server's own (`platformLine`).
BID_LINE = {"title": "Buying 0.95 ETH 2,600 call", "subtitle": "ETH-20261127-2600-C", "valueUsd": 9.5,
            "status": "Resting",
            "details": [{"label": "Limit", "value": "$10.00 each"}, {"label": "Held back", "value": "$9.50"}]}


def bid(line=BID_LINE):
    return {"orderId": "1b5f603a", "instrument": "ETH-20261127-2600-C", "side": "buy", "size": 0.95,
            "filledSize": 0, "limitPricePerUnitUsd": 10, "status": "open", "platformLine": line}


def prime_with(orders, unread=False):
    prime = dict(subaccount("PRIME", 100001, "22.69", 30.82, [position(DERIVE_CALL, 0.17, 8.13)]),
                 openOrders=orders)
    entry = derive("22.69", 30.82, subs=[prime])
    if unread:
        entry["account"]["ordersUnread"] = True
    return entry


class RestingOrders(unittest.TestCase):
    def test_a_resting_order_is_its_subaccount_rows_last_line(self):
        fake = run([0], {"/options/account": accounts(prime_with([bid()]))})
        self.assertEqual([p["title"] for p in fake.rows[0]["positions"]],
                         ["Cash", "Bought 0.17 ETH 2,550 call", "Buying 0.95 ETH 2,600 call"])
        self.assertEqual(fake.rows[0]["positions"][-1], BID_LINE)
        # Cash is what can be spent: 22.69 less the 9.50 the bid holds.
        self.assertEqual(fake.rows[0]["positions"][0], {"title": "Cash", "valueUsd": 13.19})
        # An order is no position: the status counts only what is held.
        self.assertEqual(fake.statuses[0][1]["positions"], 1)

    def test_a_single_account_venue_lists_its_orders_after_its_positions(self):
        entry = paradex("12", 19, [position(CALL, 0.1, 7)])
        entry["account"]["openOrders"] = [bid()]
        line = run([0], {"/options/account": accounts(entry)}).rows[0]["positions"]
        self.assertEqual([(p["title"], p.get("valueUsd")) for p in line],
                         [("Cash", 2.5), ("Bought 0.1 ETH 2,500 call", 7), ("Buying 0.95 ETH 2,600 call", 9.5)])

    def test_an_order_that_ended_drops_off_on_the_next_read(self):
        shown = dict(platform("prime", DERIVE, "PRIME"), positions=[BID_LINE])
        fake = run([0], {"/options/account": accounts(prime_with([]))}, platforms=[shown])
        self.assertFalse(any(p.get("status") == "Resting" for p in fake.rows[0]["positions"]))

    def test_a_read_that_cannot_see_orders_keeps_the_ones_the_row_shows(self):
        shown = dict(platform("prime", DERIVE, "PRIME"), positions=[{"title": "Cash"}, BID_LINE])
        fake = run([0], {"/options/account": accounts(prime_with([], unread=True))}, platforms=[shown])
        self.assertEqual(fake.rows[0]["positions"][-1], BID_LINE)
        self.assertEqual(sum(p.get("status") == "Resting" for p in fake.rows[0]["positions"]), 1)
        # The carried line's cash is not counted twice.
        self.assertEqual(fake.rows[0]["positions"][0]["valueUsd"], 13.19)

    def test_an_order_without_the_servers_line_is_not_listed(self):
        fake = run([0], {"/options/account": accounts(prime_with([dict(bid(), platformLine=None)]))})
        self.assertFalse(any(p.get("status") == "Resting" for p in fake.rows[0]["positions"]))


    def test_a_call_sale_holds_the_asset_so_cash_is_untouched(self):
        line = dict(BID_LINE, title="Selling 1 ETH 3,000 call", valueUsd=None)
        fake = run([0], {"/options/account": accounts(prime_with([bid(line)]))})
        self.assertEqual(fake.rows[0]["positions"][0]["valueUsd"], 22.69)


def ask(price, size=2, filled=0, order_id="9c41d7e2", instrument="ETH-20261127-2600-C"):
    """A resting sale, as the account read lists it."""
    return {"orderId": order_id, "instrument": instrument, "side": "sell", "size": size,
            "filledSize": filled, "limitPricePerUnitUsd": price, "status": "open", "platformLine": BID_LINE}


def ticker(mark, age=0):
    """`/options/ticker`, read `age` seconds after the venue priced it."""
    return lambda _params: {"instrument": "ETH-20261127-2600-C", "index": "1750", "mark": mark,
                            "bid": None, "ask": None, "asOf": (time.time() - age) * 1000}


class OrderGuard(unittest.TestCase):
    def guarded(self, orders, mark, times=(0,), state=None, unread=False, age=0):
        reads = {"/options/account": accounts(prime_with(orders, unread)), "/options/ticker": ticker(mark, age)}
        return run([START + t for t in times], reads, state)

    def test_a_sale_the_mark_has_passed_is_said_once(self):
        fake = self.guarded([ask(50)], "56", times=(0, 600, 1200))
        self.assertEqual(fake.notes, [
            "Your resting Derive order on ETH-20261127-2600-C, to sell 2 at $50.00 each, is now under "
            "Derive's own price for it, $56.00: filled there it gives away about $12.00. It is still "
            "on the book. Tell me to cancel it or to set a new price."])
        self.assertEqual(fake.pushes, ["A resting Derive order is priced under the market"])
        self.assertIs(fake.state["gift:derive:9c41d7e2"], True)
        # The row is written all the same, with the order on it.
        self.assertEqual(fake.rows[0]["positions"][-1], BID_LINE)

    def test_a_buy_over_the_mark_is_said_the_other_way(self):
        fake = self.guarded([bid()], "7")  # 0.95 bid at $10 against a $7 mark
        self.assertEqual(len(fake.notes), 1)
        self.assertIn("to buy 0.95 at $10.00 each, is now over Derive's own price for it, $7.00", fake.notes[0])
        self.assertIn("gives away about $2.85", fake.notes[0])

    def test_only_what_is_left_of_a_part_filled_order_counts(self):
        fake = self.guarded([ask(50, size=2, filled=1.5)], "56")
        self.assertIn("to sell 0.5 at $50.00", fake.notes[0])
        self.assertIn("gives away about $3.00", fake.notes[0])

    def test_a_price_on_the_right_side_or_inside_the_noise_says_nothing(self):
        for orders, mark in (([ask(50)], "50.9"),      # 1.8% under: inside 2%
                             ([ask(50)], "44"),        # a sale over the mark gives nothing away
                             ([bid()], "12"),          # a buy under the mark neither
                             ([ask(0.5, size=1)], "0.9")):  # 44% under, but $0.40 in all
            fake = self.guarded(orders, mark)
            self.assertEqual(fake.notes, [], (orders, mark))
            self.assertEqual([k for k in fake.state if k.startswith("gift:")], [])

    def test_a_mark_that_is_old_missing_or_unreadable_says_nothing_and_the_rows_still_write(self):
        self.assertEqual(self.guarded([ask(50)], "56", age=300).notes, [])
        self.assertEqual(self.guarded([ask(50)], None).notes, [])
        reads = {"/options/account": accounts(prime_with([ask(50)])), "/options/ticker": BevoError("503")}
        fake = run([START], reads)
        self.assertEqual(fake.notes, [])
        self.assertEqual(len(fake.rows), 1)
        self.assertTrue(any("could not price the resting order" in line for line in fake.logs))
        self.assertEqual(fake.statuses[-1][0], "ok")

    def test_a_read_that_cannot_see_orders_asks_nothing_and_forgets_nothing(self):
        fake = self.guarded([], "56", state={"gift:derive:9c41d7e2": True}, unread=True)
        self.assertEqual([path for path, _ in fake.read_calls if path == "/options/ticker"], [])
        self.assertIs(fake.state["gift:derive:9c41d7e2"], True)

    def test_an_order_that_ended_is_forgotten_so_a_new_one_is_said(self):
        fake = self.guarded([ask(50, order_id="b2")], "56", state={"gift:derive:9c41d7e2": True})
        self.assertNotIn("gift:derive:9c41d7e2", fake.state)
        self.assertIs(fake.state["gift:derive:b2"], True)
        self.assertEqual(len(fake.notes), 1)

    def test_an_order_on_a_single_account_venue_is_priced_with_its_venue(self):
        entry = paradex("12", 19)
        entry["account"]["openOrders"] = [ask(50)]
        fake = run([START], {"/options/account": accounts(entry), "/options/ticker": ticker("56")})
        self.assertIn("Your resting Paradex order", fake.notes[0])
        self.assertIn(("/options/ticker", {"instrument": "ETH-20261127-2600-C", "venue": "paradex"}), fake.read_calls)

    def test_no_more_than_ten_orders_are_priced_a_check(self):
        orders = [ask(50, order_id="o%02d" % i) for i in range(14)]
        fake = self.guarded(orders, "56")
        self.assertEqual(len([path for path, _ in fake.read_calls if path == "/options/ticker"]), 10)
        self.assertEqual(len(fake.notes), 10)
