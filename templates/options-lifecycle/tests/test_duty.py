"""duty.py run against scripted accounts, clocks and settlements.

    python3 -m unittest discover -s tests -v

The first half is the stand-in for the `bevo` SDK the tests run duty.py against:

A scripted stand-in for the `bevo` SDK, for running duty.py offline.

`run(times, world, ...)` installs a fresh fake as `bevo`, sets PARAMS, and steps the
clock through `times`, one tick each. `World` is what the reads answer from: the main
wallet's account on each venue, each Butler wallet's own account with the Platforms row
the server keeps for it, an index per underlying and the settlements published so far.
A test changes the world between runs and carries `fake.state` across them.
"""

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent

SITES = {"derive": "https://www.derive.xyz", "paradex": "https://app.paradex.trade", "rysk": "https://app.rysk.finance"}
#: ETH-20261030 at 08:00 UTC.
EXPIRY = 1793347200


class BevoError(Exception):
    pass


def position(instrument, size, cost=None, **fields):
    """An account's row for one option held: positive `size` is bought, negative sold."""
    row = {"instrument": instrument, "size": size, "costUsd": cost}
    row.update(fields)
    return row


def put(size=-0.5, cost=20.5, strike=2450, **fields):
    return position("ETH-20261030-%d-P" % strike, size, cost, underlying="ETH", strike=strike,
                    type="P", expirySec=EXPIRY, **fields)


def call(size=0.2, cost=4.0, strike=2600, **fields):
    return position("ETH-20261030-%d-C" % strike, size, cost, underlying="ETH", strike=strike,
                    type="C", expirySec=EXPIRY, **fields)


class World:
    def __init__(self, derive=(), paradex=None, rysk=None, wallets=(), index=None, settled=None,
                 unreadable=(), rysk_paid=()):
        #: venue -> the main wallet's positions there; None for a venue with no account.
        self.main = {"derive": list(derive), "paradex": paradex, "rysk": rysk}
        #: [{"id", "label", "address", "venue", "positions", "row": True}]: a Butler wallet's
        #: own account; `row` False drops its Platforms row, as for a wallet never traded.
        self.wallets = [dict(w) for w in wallets]
        self.index = dict({"ETH": 2500.0} if index is None else index)
        #: (underlying, expiry) or instrument -> the settlement price.
        self.settled = dict(settled or {})
        #: Paths, venues ("venue:paradex") or wallet ids ("wallet:<id>") that fail to read.
        self.unreadable = set(unreadable)
        self.rysk_paid = list(rysk_paid)
        self.reads = []

    def account(self, positions, **more):
        return {"exists": positions is not None, "positions": list(positions or []), **more}

    def main_body(self):
        venues = []
        for venue, positions in self.main.items():
            entry = {"venue": venue, "name": venue.title(), "site": SITES[venue]}
            if "venue:" + venue in self.unreadable:
                venues.append(dict(entry, available=False, error="timeout"))
                continue
            more = {"settled": self.rysk_paid} if venue == "rysk" else {}
            venues.append(dict(entry, available=True, account=self.account(positions, **more)))
        return {"account": venues[0].get("account"), "venues": venues}

    def read(self, path, params):
        self.reads.append((path, dict(params or {})))
        if path in self.unreadable:
            raise BevoError("unreadable")
        params = params or {}
        if path == "/options/account":
            if "walletId" not in params:
                return self.main_body()
            if "wallet:" + params["walletId"] in self.unreadable:
                raise BevoError("unreadable")
            wallet = next(w for w in self.wallets if w["id"] == params["walletId"] and w["venue"] == params["venue"])
            return {"venue": wallet["venue"], "account": self.account(wallet["positions"])}
        if path == "/platform-balances":
            return {"platforms": [
                {"name": "%s · %s" % (w["venue"].title(), w["label"]), "siteUrl": SITES[w["venue"]],
                 "siteHost": SITES[w["venue"]].split("://")[1], "account": w["address"].lower(),
                 "serverKept": True} for w in self.wallets if w.get("row", True)
            ] + [{"name": "Derive", "siteHost": "www.derive.xyz", "account": "PRIME", "serverKept": False}]}
        if path == "/wallets":
            return {"wallets": [{"walletId": w["id"], "label": w["label"], "address": w["address"],
                                 "chainType": "ethereum", "status": "active"} for w in self.wallets]}
        if path == "/options/ticker":
            name = params["instrument"]
            value = self.index.get(name.split("-")[0])
            return {"instrument": name, "index": None if value is None else str(value)}
        if path == "/options/settlement":
            key = params.get("instrument") or (params["underlying"], int(params["expiry"]))
            return {"price": self.settled.get(key)}
        raise BevoError("no fixture for %s" % path)


class FakeBevo:
    BevoError = BevoError

    def __init__(self, times, world, state):
        self.times = list(times)
        self.world = world
        self.state = dict(state)
        self.now = self.times[0]
        self.logs, self.notes, self.statuses = [], [], []

    def log(self, message):
        self.logs.append(str(message))

    def notify(self, text, quiet=False, push=None):
        self.notes.append(str(text))
        return {"ok": True}

    def status(self, next, last=None, next_at=None, **values):
        self.statuses.append((next, values))

    def read(self, path, params=None):
        return self.world.read(path, params)

    def platform_balances(self):
        return self.read("/platform-balances").get("platforms", [])

    def ticks(self):
        for at in self.times:
            self.now = at
            yield {"kind": "timer"}


def run(times, world, settings=None, state=None):
    fake = FakeBevo(times, world, state or {})
    sys.modules["bevo"] = fake
    spec = importlib.util.spec_from_file_location("duty_under_test", ROOT / "duty.py")
    module = importlib.util.module_from_spec(spec)
    with mock.patch("time.time", lambda: fake.now), \
            mock.patch.dict(os.environ, {"PARAMS": json.dumps(settings or {})}):
        spec.loader.exec_module(module)
    return fake


DAY = 86400
EARLY = EXPIRY - 5 * DAY
EVE = EXPIRY - 20 * 3600
AFTER = EXPIRY + 30 * 60
QUARTER = 900

WALLET = {"id": "w-1", "label": "eth-put-order", "address": "0xAbC0000000000000000000000000000000000001",
          "venue": "derive", "positions": []}


def held(fake):
    return sorted(fake.state.get("held") or {})


class WhatItWatches(unittest.TestCase):
    def test_nothing_is_set_and_every_position_is_watched(self):
        fake = run([EARLY], World(derive=[put(), call()]))
        self.assertEqual(held(fake), ["main|derive|ETH-20261030-2450-P|sold", "main|derive|ETH-20261030-2600-C|bought"])
        self.assertEqual(fake.notes, [])
        self.assertEqual(fake.statuses[-1], ("watching", {"count": 2, "when": "30 Oct"}))

    def test_no_positions_is_a_quiet_idle_watch(self):
        fake = run([EARLY], World())
        self.assertEqual((fake.notes, fake.statuses[-1]), ([], ("none", {})))

    def test_every_venue_of_the_main_wallet(self):
        world = World(derive=[put()],
                      paradex=[position("ETH-USD-30OCT26-2450-P", -0.5, 19.0, underlying="ETH", strike=2450,
                                        type="P", expirySec=EXPIRY)],
                      rysk=[position("HYPE-30OCT26-56.5-P", -10, 12.0)])
        fake = run([EARLY], world)
        self.assertEqual(held(fake), ["main|derive|ETH-20261030-2450-P|sold",
                                      "main|paradex|ETH-USD-30OCT26-2450-P|sold",
                                      "main|rysk|HYPE-30OCT26-56.5-P|sold"])
        rysk = fake.state["held"]["main|rysk|HYPE-30OCT26-56.5-P|sold"]
        self.assertEqual((rysk["underlying"], rysk["strike"], rysk["kind"], rysk["expiry"]),
                         ("HYPE", 56.5, "P", EXPIRY))

    def test_a_butler_wallets_own_account_is_found_by_its_platforms_row(self):
        world = World(wallets=[dict(WALLET, positions=[put(size=0.1, cost=1.12, strike=1300)])])
        fake = run([EARLY], world)
        self.assertEqual(held(fake), ["w-1|derive|ETH-20261030-1300-P|bought"])
        self.assertIn(("/options/account", {"walletId": "w-1", "venue": "derive"}), world.reads)

    def test_a_wallet_with_no_platforms_row_is_never_read(self):
        world = World(wallets=[dict(WALLET, positions=[put()], row=False)])
        fake = run([EARLY], world)
        self.assertEqual(held(fake), [])
        self.assertNotIn("walletId", str(world.reads))

    def test_with_no_wallet_rows_the_wallet_list_is_not_read(self):
        world = World(derive=[put()])
        run([EARLY], world)
        self.assertNotIn("/wallets", [path for path, _ in world.reads])

    def test_a_put_another_duty_delivers_is_left_alone(self):
        fake = run([EVE], World(derive=[put(), call()]), {"EXCEPT": ["eth-20261030-2450-p"]})
        self.assertEqual(held(fake), ["main|derive|ETH-20261030-2600-C|bought"])
        self.assertEqual(len(fake.notes), 1)

    def test_a_row_that_does_not_say_what_it_is_is_skipped(self):
        fake = run([EARLY], World(derive=[position("ETH-PERP", 1.0, 10.0)]))
        self.assertEqual(held(fake), [])
        self.assertIn("not watched", fake.logs[-1])


class TheDayBefore(unittest.TestCase):
    def test_a_sold_put_above_its_strike(self):
        fake = run([EVE, EVE + QUARTER], World(derive=[put()]))
        self.assertEqual(fake.notes, ["ETH $2,450 put, 30 Oct: ETH is at $2,500. Your note looks set to pay out "
                                      "in full. It settles in about 20 hours."])

    def test_a_sold_put_under_its_strike(self):
        fake = run([EVE], World(derive=[put()], index={"ETH": 2400.0}))
        self.assertIn("Your note is under your price, so you may end up buying ETH at $2,450.", fake.notes[0])

    def test_a_bought_call_out_of_the_money(self):
        fake = run([EVE], World(derive=[call()]))
        self.assertIn("Your call is out of the money: it pays nothing unless ETH ends above $2,600.", fake.notes[0])

    def test_a_bought_call_in_the_money(self):
        fake = run([EVE], World(derive=[call()], index={"ETH": 2700.0}))
        self.assertIn("Your call is in the money: if it ends here it pays about $20.00, against the $4.00 it cost.",
                      fake.notes[0])

    def test_no_index_waits_and_tells_on_the_next_run(self):
        world = World(derive=[put()], index={})
        fake = run([EVE], world)
        self.assertEqual(fake.notes, [])
        world.index = {"ETH": 2500.0}
        fake = run([EVE + QUARTER], world, state=fake.state)
        self.assertEqual(len(fake.notes), 1)

    def test_heads_up_hours_moves_it(self):
        fake = run([EXPIRY - 40 * 3600], World(derive=[put()]), {"HEADS_UP_HOURS": 48})
        self.assertEqual(len(fake.notes), 1)


class Settlement(unittest.TestCase):
    def after(self, first, settled, world_now=None, times=(AFTER,)):
        world = first.world if world_now is None else world_now
        world.main["derive"] = []  # the venue takes an expired position out of the account
        for wallet in world.wallets:
            wallet["positions"] = []
        world.settled = settled
        return run(list(times), world, state=first.state)

    def test_a_sold_put_that_expires_worthless(self):
        first = run([EARLY], World(derive=[put()]))
        fake = self.after(first, {("ETH", EXPIRY): 2500.0})
        self.assertEqual(fake.notes, ["ETH $2,450 put, 30 Oct: ETH settled at $2,500, above your $2,450. You kept "
                                      "your $1,225.00 and the $20.50 premium. What is left of your collateral is "
                                      "free cash in your Derive account."])
        self.assertEqual(held(fake), [])
        self.assertEqual(fake.statuses[-1], ("none", {}))

    def test_a_sold_put_assigned_is_a_loss_in_cash(self):
        first = run([EARLY], World(derive=[put()]))
        fake = self.after(first, {("ETH", EXPIRY): 2350.0})
        self.assertIn("Your note was assigned: you agreed to buy 0.5 ETH at $2,450, which is $50.00 more than they "
                      "are worth today. After the $20.50 premium you are down $29.50. Derive settles in cash, so "
                      "you are holding the loss in cash, not the ETH.", fake.notes[0])

    def test_a_bought_call_that_pays(self):
        first = run([EARLY], World(derive=[call()]))
        fake = self.after(first, {("ETH", EXPIRY): 2700.0})
        self.assertIn("ETH settled at $2,700, above your $2,600: your call paid $20.00 into your Derive account. "
                      "After the $4.00 it cost, you are up $16.00.", fake.notes[0])

    def test_a_bought_call_that_expires_worthless(self):
        first = run([EARLY], World(derive=[call()]))
        fake = self.after(first, {("ETH", EXPIRY): 2500.0})
        self.assertIn("at or under your $2,600: the call expired worthless, so the $4.00 you paid is lost.",
                      fake.notes[0])

    def test_a_sold_call(self):
        first = run([EARLY], World(derive=[call(size=-1.0, cost=30.0)]))
        fake = self.after(first, {("ETH", EXPIRY): 2700.0})
        self.assertIn("Your 1 ETH was sold at $2,600. You gave up $100.00 of further upside, and kept the $30.00 "
                      "premium.", fake.notes[0])

    def test_a_butler_wallets_position_names_its_account(self):
        world = World(wallets=[dict(WALLET, positions=[put(size=0.1, cost=1.12, strike=1300)])])
        first = run([EARLY], world)
        fake = self.after(first, {("ETH", EXPIRY): 1200.0})
        self.assertIn("your put paid $10.00 into your “eth-put-order” wallet's Derive account. After the "
                      "$1.12 it cost, you are up $8.88.", fake.notes[0])

    def test_it_is_told_from_what_was_last_seen_even_if_the_wallet_row_is_gone(self):
        world = World(wallets=[dict(WALLET, positions=[put(size=0.1, cost=1.12, strike=1300)])])
        first = run([EARLY], world)
        world.wallets = []
        fake = self.after(first, {("ETH", EXPIRY): 1200.0})
        self.assertEqual(len(fake.notes), 1)

    def test_inside_the_grace_it_waits_quietly(self):
        first = run([EARLY], World(derive=[put()]))
        fake = self.after(first, {("ETH", EXPIRY): 2500.0}, times=[EXPIRY + 300])
        self.assertEqual(fake.notes, [])
        self.assertEqual(fake.statuses[-1], ("settling", {"count": 1}))

    def test_no_price_yet_waits_and_says_so_once_after_six_hours(self):
        first = run([EARLY], World(derive=[put()]))
        fake = self.after(first, {}, times=[AFTER, EXPIRY + 7 * 3600, EXPIRY + 8 * 3600])
        self.assertEqual(len(fake.notes), 1)
        self.assertIn("it expired 7 hours ago and Derive has not published a settlement price yet", fake.notes[0])
        self.assertEqual(held(fake), ["main|derive|ETH-20261030-2450-P|sold"])
        fake = self.after(fake, {("ETH", EXPIRY): 2500.0}, times=[EXPIRY + 9 * 3600])
        self.assertEqual(len(fake.notes), 1)
        self.assertEqual(held(fake), [])

    def test_two_positions_settle_in_one_run_each_with_its_own_note(self):
        first = run([EARLY], World(derive=[put(), call()]))
        fake = self.after(first, {("ETH", EXPIRY): 2500.0})
        self.assertEqual(len(fake.notes), 2)

    def test_a_paradex_option_settles_by_its_own_name(self):
        name = "ETH-USD-30OCT26-2450-P"
        world = World(paradex=[position(name, -0.5, 19.0, underlying="ETH", strike=2450, type="P",
                                        expirySec=EXPIRY)])
        first = run([EARLY], world)
        world.main["paradex"] = []
        world.settled = {name: 2500.0}
        fake = run([AFTER], world, state=first.state)
        self.assertIn("free cash in your Paradex account.", fake.notes[0])
        self.assertIn(("/options/settlement", {"instrument": name, "venue": "paradex"}), world.reads)

    def test_the_cost_missing_from_the_account_is_left_out_not_guessed(self):
        first = run([EARLY], World(derive=[call(cost=None)]))
        fake = self.after(first, {("ETH", EXPIRY): 2500.0})
        self.assertTrue(fake.notes[0].endswith("the call expired worthless."))


class Rysk(unittest.TestCase):
    NAME = "HYPE-30OCT26-56.5-P"

    def world(self):
        return World(rysk=[position(self.NAME, -10, 12.0)], index={"HYPE": 60.0})

    def test_it_waits_for_the_payout_not_the_price(self):
        world = self.world()
        first = run([EARLY], world)
        world.main["rysk"] = []
        world.settled = {self.NAME: 60.0}
        fake = run([AFTER], world, state=first.state)
        self.assertEqual(fake.notes, [])
        world.rysk_paid = [{"instrument": "HYPE-30OCT26-56.50-P", "size": 10, "assigned": False,
                            "received": [{"amount": 565, "symbol": "USDT0"}]}]
        fake = run([AFTER + QUARTER], world, state=fake.state)
        self.assertEqual(fake.notes, ["HYPE $56.50 put, 30 Oct: HYPE settled at $60.00, at or above your $56.50. "
                                      "Your put expired worthless: Rysk returned 565 USDT0 to your HyperEVM "
                                      "wallet, and you keep the $12.00 premium."])

    def test_an_assigned_put_delivers_the_asset(self):
        world = self.world()
        first = run([EARLY], world)
        world.main["rysk"] = []
        world.settled = {self.NAME: 50.0}
        world.rysk_paid = [{"instrument": self.NAME, "size": 10, "assigned": True,
                            "received": [{"amount": 10, "symbol": "HYPE"}]}]
        fake = run([AFTER], world, state=first.state)
        self.assertIn("Your put was assigned: Rysk delivered 10 HYPE to your HyperEVM wallet, bought at $56.50 "
                      "each. That is $65.00 more than they were worth at settlement; after the $12.00 premium "
                      "you are down $53.00. The HYPE is yours to keep", fake.notes[0])


class ClosedOrUnreadable(unittest.TestCase):
    def test_a_position_gone_twice_running_is_dropped_without_a_note(self):
        world = World(derive=[put()])
        first = run([EARLY], world)
        world.main["derive"] = []
        once = run([EARLY + QUARTER], world, state=first.state)
        self.assertEqual(held(once), ["main|derive|ETH-20261030-2450-P|sold"])
        twice = run([EARLY + 2 * QUARTER], world, state=once.state)
        self.assertEqual((held(twice), twice.notes), ([], []))

    def test_one_empty_read_then_back_is_still_watched(self):
        world = World(derive=[put()])
        first = run([EARLY], world)
        world.main["derive"] = []
        once = run([EARLY + QUARTER], world, state=first.state)
        world.main["derive"] = [put()]
        back = run([EARLY + 2 * QUARTER, EARLY + 3 * QUARTER], world, state=once.state)
        self.assertEqual(back.state["held"]["main|derive|ETH-20261030-2450-P|sold"]["gone"], 0)

    def test_an_unreadable_venue_keeps_what_it_held(self):
        world = World(derive=[put()])
        first = run([EARLY], world)
        world.unreadable = {"venue:derive"}
        fake = run([EARLY + i * QUARTER for i in range(1, 5)], world, state=first.state)
        self.assertEqual(held(fake), ["main|derive|ETH-20261030-2450-P|sold"])

    def test_an_unreadable_wallet_keeps_what_it_held(self):
        world = World(wallets=[dict(WALLET, positions=[put(size=0.1, cost=1.12)])])
        first = run([EARLY], world)
        world.unreadable = {"wallet:w-1"}
        fake = run([EARLY + i * QUARTER for i in range(1, 5)], world, state=first.state)
        self.assertEqual(len(held(fake)), 1)

    def test_no_account_read_at_all_changes_nothing(self):
        world = World(derive=[put()])
        first = run([EARLY], world)
        world.unreadable = {"/options/account"}
        fake = run([EARLY + QUARTER], world, state=first.state)
        self.assertEqual(fake.statuses[-1], ("unreadable", {}))
        self.assertEqual(len(held(fake)), 1)

    def test_a_part_close_is_watched_at_what_is_left(self):
        world = World(derive=[put()])
        first = run([EARLY], world)
        world.main["derive"] = [put(size=-0.2, cost=8.2)]
        fake = run([EARLY + QUARTER], world, state=first.state)
        rec = fake.state["held"]["main|derive|ETH-20261030-2450-P|sold"]
        self.assertEqual((rec["size"], rec["usd"]), (-0.2, 8.2))

    def test_a_crash_in_one_run_does_not_end_the_watch(self):
        world = World(derive=[{"instrument": "ETH-20261030-2450-P", "size": "x"}, put()])
        fake = run([EARLY, EARLY + QUARTER], world)
        self.assertEqual(len(held(fake)), 1)


if __name__ == "__main__":
    unittest.main()
