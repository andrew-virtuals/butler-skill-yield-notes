"""duty.py run against scripted reads, clocks and acp answers.

    python3 -m unittest discover -s tests -v

The first half is the stand-in for the `bevo` SDK the tests run duty.py against:

A scripted stand-in for the `bevo` SDK, for running duty.py offline.

`run(...)` installs a fresh fake as `bevo`, sets PARAMS, pins the clock to each
tick's time, intercepts `subprocess.run`, executes duty.py to the end of its
ticks (or to `bevo.done()`), and returns the fake for assertions.
"""

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent

EXPIRY = 1793347200  # ETH-20261030-2450-P: 2026-10-30T08:00:00Z

PUT = {
    "INSTRUMENT": "ETH-20261030-2450-P",
    "UNDERLYING": "ETH",
    "TOKEN_ID": "native:8453",
    "STRIKE": 2450,
    "SIZE": 2.04,
    "PREMIUM_USD": 55.17,
    "COLLATERAL_USD": 4998,
}


class BevoError(Exception):
    pass


class FakeBevo:
    BevoError = BevoError
    SERVICE_ID = "svc-1"

    def __init__(self, times, reads, acp, statuses, state):
        self.times = list(times)
        self.reads = dict(reads)
        self.acp_replies = list(acp)
        self.statuses = dict(statuses)
        self.state = dict(state)
        self.now = None
        self.logs, self.notes, self.fails, self.dones = [], [], [], []
        self.lines = []
        self.read_calls, self.acp_calls = [], []

    def log(self, message):
        self.logs.append(str(message))

    def notify(self, text, quiet=False, push=None):
        self.notes.append(str(text))
        return {"ok": True}

    def fail(self, reason):
        self.fails.append(str(reason))

    def done(self, summary=None):
        self.dones.append(summary)
        raise SystemExit(0)

    def read(self, path, params=None):
        self.read_calls.append((path, dict(params or {})))
        value = self.reads.get(path)
        if callable(value):
            value = value(params or {})
        if isinstance(value, BaseException):
            raise value
        if value is None:
            raise BevoError("no fixture for %s" % path)
        return value

    def status(self, next, last=None, next_at=None, **values):
        self.lines.append((next, values))

    def exec_status(self, key, route="trade"):
        return self.statuses.get(key, {"state": "not_found"})

    def ticks(self):
        for at in self.times:
            self.now = at
            yield {"kind": "timer"}

    def _run(self, argv, **_kwargs):
        self.acp_calls.append(list(argv))
        stdout = self.acp_replies.pop(0) if self.acp_replies else ""
        return subprocess.CompletedProcess(argv, 0, stdout, "")


def run(params, times, reads=None, acp=(), statuses=None, state=None, name="ETH note"):
    fake = FakeBevo(times, reads or {}, acp, statuses or {}, state or {})
    sys.modules["bevo"] = fake
    os.environ["PARAMS"] = json.dumps(params)
    os.environ["BEVO_SERVICE_NAME"] = name
    spec = importlib.util.spec_from_file_location("duty_under_test", ROOT / "duty.py")
    module = importlib.util.module_from_spec(spec)
    real_time = time.time
    with mock.patch("time.time", lambda: fake.now if fake.now is not None else real_time()), \
            mock.patch("subprocess.run", fake._run):
        try:
            spec.loader.exec_module(module)
        except SystemExit:
            pass
    return fake


def hours(n):
    return int(n * 3600)


def answer(**fields):
    return json.dumps(fields)


SOURCE = (Path(__file__).resolve().parent.parent / "duty.py").read_text()
ASKS = re.compile(r"\?|\bsay the word\b|\bwant me to\b|\bshall i\b|\bshould i\b|\breply\b", re.I)

SETTLED_AT = EXPIRY + hours(1)
KEY = "note:svc-1:deliver"


def priced(value):
    return {"/options/ticker": {"instrument": "ETH-20261030-2450-P", "index": value, "mark": "12.3"}}


def settled(value):
    return {"/options/settlement": {"price": value}}


def held(*rows):
    return {"/options/account": {"network": "mainnet", "account": {"exists": True, "positions": list(rows)}}}


SOLD = held({"instrument": PUT["INSTRUMENT"], "size": -2.04})


class HeadsUp(unittest.TestCase):
    def test_once_inside_the_window(self):
        fake = run(PUT, [EXPIRY - hours(30), EXPIRY - hours(20), EXPIRY - hours(19)], dict(priced("2705.5"), **SOLD))
        self.assertEqual(len(fake.notes), 1)
        self.assertIn("ETH is at $2,706. Your note looks set to pay out in full", fake.notes[0])

    def test_under_the_strike_says_it_will_buy(self):
        fake = run(PUT, [EXPIRY - hours(5)], dict(priced("2300"), **SOLD))
        self.assertIn("you may end up buying ETH at $2,450; if it settles there, I will buy the ETH",
                      fake.notes[0])


class Settlement(unittest.TestCase):
    def test_out_of_the_money_keeps_everything_and_buys_nothing(self):
        fake = run(PUT, [SETTLED_AT], settled("2600"), acp=[answer(executed=True)])
        self.assertEqual(fake.acp_calls, [])
        self.assertIn("You kept your $4,998.00 and the $55.17 premium, so there was nothing to buy",
                      fake.dones[0])

    def test_at_the_strike_buys_nothing(self):
        fake = run(PUT, [SETTLED_AT], settled("2450"), acp=[answer(executed=True)])
        self.assertEqual(fake.acp_calls, [])

    def test_unpublished_buys_nothing_and_says_so_once_after_six_hours(self):
        fake = run(PUT, [SETTLED_AT, EXPIRY + hours(7), EXPIRY + hours(8)], settled(None),
                   acp=[answer(executed=True)])
        self.assertEqual(fake.acp_calls, [])
        self.assertEqual(len(fake.notes), 1)
        self.assertEqual(fake.dones, [])

    def test_a_broken_read_never_buys(self):
        fake = run(PUT, [SETTLED_AT, EXPIRY + hours(7)], {"/options/settlement": BevoError("503")},
                   acp=[answer(executed=True)])
        self.assertEqual(fake.acp_calls, [])
        self.assertIn("I will buy nothing until I can", fake.notes[0])

    def test_a_zero_price_never_buys(self):
        fake = run(PUT, [SETTLED_AT], settled("0"), acp=[answer(executed=True)])
        self.assertEqual(fake.acp_calls, [])
        self.assertEqual(fake.dones, [])


class Delivery(unittest.TestCase):
    def test_buys_size_times_settlement_of_the_pinned_token_with_one_literal_key(self):
        fake = run(PUT, [SETTLED_AT], settled("2200"), acp=[answer(executed=True)])
        self.assertEqual(fake.acp_calls, [[
            "acp", "trade", "--token-in", "usdc", "--chain-in", "8453",
            "--amount-in", "4488.00", "--token-out", "eth", "--chain-out", "8453",
            "--idempotency-key", KEY,
        ]])
        self.assertIn("you agreed to buy 2.04 ETH at $2,450", fake.dones[0])
        self.assertIn("you now own about 2.04 ETH", fake.dones[0])

    def test_the_buy_never_costs_more_than_the_collateral(self):
        fake = run(PUT, [SETTLED_AT], settled("2449.99"), acp=[answer(executed=True)])
        argv = fake.acp_calls[0]
        self.assertLessEqual(float(argv[argv.index("--amount-in") + 1]), PUT["COLLATERAL_USD"])

    def test_an_approval_card_is_pending_not_owned(self):
        fake = run(PUT, [SETTLED_AT], settled("2200"), acp=[answer(asked=True, status="manual")])
        self.assertIn("waiting on your approval", fake.dones[0])
        self.assertNotIn("you now own", fake.dones[0])

    def test_an_unreadable_answer_is_unknown_and_checked_not_retried(self):
        fake = run(PUT, [SETTLED_AT, SETTLED_AT + 900], settled("2200"), acp=["Error: socket hang up"],
                   statuses={KEY: {"state": "in_flight"}})
        self.assertEqual(len(fake.acp_calls), 1)
        self.assertIn("not certain whether the ETH purchase went through", fake.dones[0])
        self.assertTrue(any("exec_status: in_flight" in line for line in fake.logs))

    def test_a_refusal_holds_the_loss_in_cash(self):
        fake = run(PUT, [SETTLED_AT], settled("2200"), acp=[answer(error="wallet_short")])
        self.assertIn("could not buy the ETH", fake.dones[0])

    def test_a_token_pin_is_bought_by_its_address_on_its_own_chain(self):
        cbbtc = "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf"
        btc = dict(PUT, INSTRUMENT="BTC-20261030-75000-P", UNDERLYING="BTC",
                   TOKEN_ID=cbbtc + ":8453", STRIKE=75000, SIZE=0.06, COLLATERAL_USD=4500)
        fake = run(btc, [SETTLED_AT], settled("70000"), acp=[answer(executed=True)])
        argv = fake.acp_calls[0]
        self.assertEqual(argv[argv.index("--token-out") + 1], cbbtc)
        self.assertEqual(argv[argv.index("--chain-out") + 1], "8453")
        self.assertEqual(argv[argv.index("--amount-in") + 1], "4200.00")  # 0.06 x 70,000

    def test_paradex_settles_by_the_option_and_still_buys(self):
        put = dict(PUT, VENUE="paradex", INSTRUMENT="ETH-USD-30OCT26-2450-P")
        reads = dict(settled("2200"), **{"/options/ticker": {"index": "2200", "expirySec": EXPIRY}})
        fake = run(put, [SETTLED_AT], reads, acp=[answer(executed=True)])
        self.assertIn(("/options/settlement", {"instrument": "ETH-USD-30OCT26-2450-P", "venue": "paradex"}),
                      fake.read_calls)
        self.assertEqual(len(fake.acp_calls), 1)
        self.assertIn("free cash in your Paradex account", fake.dones[0])


class ClosedEarly(unittest.TestCase):
    def test_a_note_bought_back_early_finishes_and_never_buys(self):
        fake = run(PUT, [EXPIRY - hours(5), EXPIRY - hours(5) + 900, SETTLED_AT],
                   dict(priced("2300"), **settled("2200"), **held()), acp=[answer(executed=True)])
        self.assertEqual(len(fake.dones), 1)
        self.assertIn("was bought back before expiry, so there is nothing left to watch or buy", fake.dones[0])
        self.assertEqual(fake.acp_calls, [])

    def test_missing_at_the_last_check_before_expiry_never_buys(self):
        # Bought back in the final 15 minutes: one empty read, then expiry.
        fake = run(PUT, [EXPIRY - 600, SETTLED_AT], dict(settled("2200"), **held()),
                   acp=[answer(executed=True)])
        self.assertEqual(fake.acp_calls, [])
        self.assertIn("missing from your Derive account at my last check before expiry", fake.dones[0])
        self.assertIn("did not buy the ETH", fake.dones[0])

    def test_a_blip_then_held_still_buys(self):
        queue = [held()["/options/account"], SOLD["/options/account"]]
        reads = dict(priced("2300"), **settled("2200"))
        reads["/options/account"] = lambda _params: queue.pop(0) if len(queue) > 1 else queue[0]
        fake = run(PUT, [EXPIRY - 1800, EXPIRY - 900, SETTLED_AT], reads, acp=[answer(executed=True)])
        self.assertEqual(len(fake.acp_calls), 1)

    def test_an_unreadable_account_still_buys(self):
        reads = dict(priced("2300"), **settled("2200"))
        reads["/options/account"] = BevoError("503")
        fake = run(PUT, [EXPIRY - 900, SETTLED_AT], reads, acp=[answer(executed=True)])
        self.assertEqual(len(fake.acp_calls), 1)


class Settings(unittest.TestCase):
    def assert_paused(self, params, why):
        fake = run(params, [SETTLED_AT], settled("2200"), acp=[answer(executed=True)])
        self.assertIn("does nothing until its settings are fixed", fake.notes[0])
        self.assertIn(why, fake.notes[0])
        self.assertEqual(fake.read_calls, [])
        self.assertEqual(fake.acp_calls, [])

    def test_only_a_put(self):
        self.assert_paused(dict(PUT, INSTRUMENT="ETH-20261030-2450-C"), "is a call")

    def test_not_on_rysk(self):
        self.assert_paused(dict(PUT, VENUE="rysk", INSTRUMENT="ETH-30OCT26-2450-P"), "delivers the asset itself")

    def test_a_pin_is_required_and_must_be_one(self):
        for pin in ["", "ETH", "stock:ETH:0", "native:base"]:
            self.assert_paused(dict(PUT, TOKEN_ID=pin), "is not a pinned token")

    def test_the_underlying_must_match_the_instrument(self):
        self.assert_paused(dict(PUT, UNDERLYING="BTC"), "not an option on UNDERLYING BTC")


class Boundary(unittest.TestCase):
    def test_its_one_acp_call_carries_a_literal_idempotency_key(self):
        calls = [n for n in ast.walk(ast.parse(SOURCE))
                 if isinstance(n, ast.Call) and ast.unparse(n.func) == "subprocess.run"]
        self.assertEqual(len(calls), 1)
        literals = [e.value for e in calls[0].args[0].elts if isinstance(e, ast.Constant)]
        self.assertEqual(literals[:2], ["acp", "trade"])
        self.assertIn("--idempotency-key", literals)

    def test_no_note_asks_the_owner_anything(self):
        worlds = [
            run(PUT, [EXPIRY - hours(5)], dict(priced("2300"), **SOLD)),
            run(PUT, [SETTLED_AT], settled("2600")),
            run(PUT, [SETTLED_AT], settled("2200"), acp=[answer(executed=True)]),
            run(PUT, [SETTLED_AT], settled("2200"), acp=[answer(asked=True)]),
            run(PUT, [SETTLED_AT], settled("2200"), acp=["?"]),
            run(PUT, [SETTLED_AT, EXPIRY + hours(7)], settled(None)),
            run(PUT, [SETTLED_AT, EXPIRY + hours(7)], {"/options/settlement": BevoError("x")}),
        ]
        for fake in worlds:
            for text in fake.notes + [d for d in fake.dones if d]:
                self.assertIsNone(ASKS.search(text), text)


if __name__ == "__main__":
    unittest.main()
