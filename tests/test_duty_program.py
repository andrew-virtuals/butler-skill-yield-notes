"""scripts/duty_program.py, run against a fake duty runtime: what it tells the owner, and when."""

import json
import os
import subprocess
import sys
import time
import types
import unittest
from unittest import mock

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import make_duty  # noqa: E402

RULE = '''
def trigger():
    return WORLD["met"](WORLD), "ETH at $%d" % WORLD["px"]


def order():
    if WORLD.get("noquote", 0) > 0:
        WORLD["noquote"] -= 1
        return None, "the quote failed (venue unreachable)"
    quote  # the helper is there for a real rule
    return ["open", "--instrument", "ETH-P", "--size", "0.5", "--min-premium", "40",
            "--max-collateral", "750"], "sell a 0.5 ETH $1,500 put"
'''
SETTINGS = {"NAME": "ETH puts", "VENUE": "derive", "OWN_WALLET": True, "ALLOCATION_USD": 1000,
            "NEED_USD": 750, "TIMES": 1, "QUOTE_PY": "/x/quote.py"}
TICK = 300


class Done(Exception):
    pass


def run(world, ticks, **settings):
    """Runs the program for `ticks` runs five minutes apart; returns (notes, statuses, commands)."""
    notes, statuses, commands = [], [], []
    world.setdefault("fates", [])
    world.setdefault("refuse", [])
    bevo = types.ModuleType("bevo")
    bevo.BevoError = Exception
    bevo.SERVICE_ID = "svc"
    bevo.state = world["state"] = {}
    bevo.key = lambda *parts: ":".join(str(p) for p in parts)
    bevo.read = lambda path, q=None: {"account": {"exists": world["free"] is not None,
                                                  "freeForNewPutsUsd": world["free"] or 0}}
    bevo.balance = lambda: types.SimpleNamespace(cash_usd=world["cash"])
    bevo.notify = lambda text, quiet=False, push=None: notes.append(text)
    bevo.log = lambda text: None
    bevo.status = lambda state, **values: statuses.append(state)
    bevo.settled = lambda key, route=None, wait=0: world["fates"].pop(0) if world["fates"] else "waiting"

    def done(text):
        notes.append("DONE")
        raise Done()

    def ticker():
        for i in range(ticks):
            world["tick"] = i
            landing = world.get("landing")
            if landing and i >= landing[0]:
                world["free"], world["landing"] = (world["free"] or 0) + landing[1], None
            world.update(world.get("script", {}).get(i, {}))
            yield i

    bevo.done, bevo.ticks = done, ticker

    def fake_run(argv, **kwargs):
        commands.append(" ".join(argv))
        out, code = "{}", 0
        if argv[2] == "deposit":
            amount = float(argv[4])
            world["cash"] -= amount
            world["landing"] = (world["tick"] + 2, amount * 0.99)
        elif world["refuse"]:
            answer = world["refuse"].pop(0)
            if isinstance(answer, dict):
                out, code = json.dumps(answer), 1
            else:
                out = json.dumps({"code": answer})
        elif world["fates"][:1] == ["executed"]:
            world["free"] -= settings.get("NEED_USD", SETTINGS["NEED_USD"])
        return types.SimpleNamespace(stdout=out, stderr="", returncode=code)

    program = make_duty.read(make_duty.PROGRAM)
    code = make_duty.RULE.sub(lambda _: RULE, program)
    env = {"PARAMS": json.dumps({**SETTINGS, **settings})}
    with mock.patch.dict(sys.modules, {"bevo": bevo}), mock.patch.dict(os.environ, env), \
            mock.patch.object(subprocess, "run", fake_run), \
            mock.patch.object(time, "time", lambda: 1e9 + world.get("tick", 0) * TICK):
        try:
            exec(compile(code, "duty.py", "exec"), {"WORLD": world, "__name__": "duty"})
        except Done:
            pass
    return notes, statuses, commands


def count(notes, words):
    return sum(1 for n in notes if words in n)


class OwnWallet(unittest.TestCase):
    def test_deposits_then_ready_then_trades_once(self):
        world = {"free": None, "cash": 0, "px": 1800, "fates": ["executed"],
                 "met": lambda w: w["px"] < 1500, "script": {1: {"cash": 1020}, 6: {"px": 1480}}}
        notes, statuses, commands = run(world, 12)
        self.assertEqual([c.split()[2] for c in commands], ["deposit", "open"])
        self.assertIn("--amount 1020 --from 8453 --idempotency-key deposit:svc:0", commands[0])
        self.assertTrue(commands[1].endswith("--idempotency-key trade:svc:0:0"))
        order = [next(i for i, n in enumerate(notes) if w in n) for w in ("ready on Derive", "Placing", "done,")]
        self.assertEqual(order, sorted(order))
        self.assertEqual(notes[-1], "DONE")
        self.assertIn("setting_up", statuses)

    def test_a_fill_is_timed_for_the_rule_and_a_miss_is_not(self):
        missed = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: True, "fates": ["dropped"] * 3}
        run(missed, 3, OWN_WALLET=False)
        self.assertNotIn("traded_at", missed["state"])
        filled = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: True, "fates": ["executed"]}
        run(filled, 3, OWN_WALLET=False)
        self.assertGreater(filled["state"]["traded_at"], 0)


    def test_never_deposits_in_the_run_that_trades(self):
        world = {"free": None, "cash": 1020, "px": 1480, "fates": ["executed"], "met": lambda w: True}
        _, _, commands = run(world, 8)
        self.assertEqual([c.split()[2] for c in commands], ["deposit", "open"])

    def test_short_is_said_once_and_asks_at_least_ten(self):
        world = {"free": None, "cash": 11, "px": 1480, "fates": ["executed", "executed"],
                 "met": lambda w: w["tick"] in (4, 9, 12, 16), "script": {7: {"cash": 5}, 11: {"cash": 15}}}
        notes, _, commands = run(world, 20, ALLOCATION_USD=10, NEED_USD=9.79, TIMES=2)
        self.assertEqual(count(notes, "Top it up by $10 and it carries on"), 1)
        self.assertEqual(count(notes, "so nothing traded. Top it up"), 1)
        self.assertEqual([c.split()[4] for c in commands if " deposit " in c], ["11", "15"])
        self.assertEqual(count(notes, "done,"), 2)

    def test_a_wallet_never_funded_is_said_once_after_thirty_minutes(self):
        world = {"free": None, "cash": 0, "px": 1480, "fates": ["executed"],
                 "met": lambda w: w["tick"] >= 16, "script": {12: {"cash": 1020}}}
        notes, statuses, _ = run(world, 20)
        self.assertEqual(count(notes, "its wallet is still empty"), 1)
        self.assertIn("unfunded", statuses)
        self.assertEqual(notes[-1], "DONE")
        self.assertLess(statuses.index("setting_up"), statuses.index("unfunded"))


class MainWallet(unittest.TestCase):
    def test_never_deposits_and_warns_when_short(self):
        world = {"free": 300, "cash": 5000, "px": 1800, "met": lambda w: w["tick"] == 3}
        notes, statuses, commands = run(world, 5, OWN_WALLET=False)
        self.assertEqual(commands, [])
        self.assertEqual(count(notes, "Top it up by $450"), 1)
        self.assertEqual(statuses[-1], "short")

    def test_a_held_back_trade_names_the_start_card_once(self):
        world = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: True,
                 "fates": ["dropped"] * 4 + ["executed"], "refuse": ["pocket_pending"] * 4}
        notes, _, commands = run(world, 12, OWN_WALLET=False)
        self.assertEqual(count(notes, "waiting for you to hold its Start card"), 1)
        self.assertEqual(count(notes, "did not fill"), 0)
        self.assertEqual(count(notes, "Placing"), 1)
        self.assertEqual(len(commands), 5)
        self.assertEqual(notes[-1], "DONE")

    def test_a_held_back_trade_is_never_counted_as_done(self):
        world = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: True,
                 "fates": ["unknown"], "refuse": ["pocket_pending"]}
        notes, _, _ = run(world, 2, OWN_WALLET=False)
        self.assertEqual(count(notes, "may have gone through"), 0)
        self.assertNotIn("DONE", notes)

    def test_an_order_the_server_refused_outright_is_never_counted(self):
        no = {"status": "refused", "ok": False, "code": "OPTIONS_BAD_COMMAND", "httpStatus": 400,
              "error": "no such instrument on Derive"}
        world = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: True,
                 "fates": ["unknown"] * 3 + ["executed"], "refuse": [no] * 3}
        notes, _, commands = run(world, 12, OWN_WALLET=False)
        self.assertEqual(count(notes, "was refused (no such instrument on Derive)"), 1)
        self.assertEqual(count(notes, "may have gone through"), 0)
        self.assertEqual(len(commands), 4)
        self.assertEqual(count(notes, "done,"), 1)

    def test_an_outage_answer_is_left_to_the_ledger(self):
        down = {"status": "refused", "ok": False, "code": "HTTP_503", "httpStatus": 503, "error": "x"}
        world = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: True,
                 "fates": ["unknown"], "refuse": [down]}
        notes, _, commands = run(world, 4, OWN_WALLET=False)
        self.assertEqual(len(commands), 1)
        self.assertEqual(count(notes, "may have gone through"), 1)

    def test_a_key_the_ledger_already_holds_is_left_to_the_ledger(self):
        twice = {"status": "conflict", "ok": False, "code": "IDEMPOTENCY_KEY_REUSED", "httpStatus": 409,
                 "error": "This idempotency key was already used for a different request"}
        world = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: True,
                 "fates": ["executed"], "refuse": [twice]}
        notes, _, commands = run(world, 4, OWN_WALLET=False)
        self.assertEqual(len(commands), 1)
        self.assertEqual(count(notes, "done,"), 1)

    def test_another_venue_is_named_on_every_command(self):
        world = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: True, "fates": ["executed"]}
        _, _, commands = run(world, 3, OWN_WALLET=False, VENUE="paradex")
        self.assertIn("--venue paradex --idempotency-key", commands[0])

    def test_a_missed_order_is_said_once_and_retried_under_new_keys(self):
        world = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: True,
                 "fates": ["dropped"] * 5 + ["executed"]}
        notes, _, commands = run(world, 14, OWN_WALLET=False)
        self.assertEqual(count(notes, "did not fill at its bound"), 1)
        self.assertEqual([c.rsplit(":", 1)[1] for c in commands], ["0", "1", "2", "3", "4", "5"])
        self.assertEqual(count(notes, "done,"), 1)

    def test_a_failing_quote_is_said_once_on_the_third_failure(self):
        world = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: True,
                 "fates": ["executed"], "noquote": 5}
        notes, statuses, _ = run(world, 10, OWN_WALLET=False)
        self.assertEqual(count(notes, "the quote failed"), 1)
        self.assertIn("retrying", statuses)
        self.assertEqual(notes[-1], "DONE")

    def test_an_unclear_order_is_counted_and_never_sent_again(self):
        world = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: True, "fates": ["unknown"]}
        notes, _, commands = run(world, 4, OWN_WALLET=False)
        self.assertEqual(len(commands), 1)
        self.assertEqual(count(notes, "may have gone through"), 1)
        self.assertEqual(notes[-1], "DONE")

    def test_every_status_it_writes_has_its_line(self):
        program = make_duty.read(make_duty.PROGRAM)
        import re
        self.assertEqual(set(re.findall(r'bevo\.status\("(\w+)"', program)), set(make_duty.STATUS))


if __name__ == "__main__":
    unittest.main()
