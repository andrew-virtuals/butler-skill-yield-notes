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


def run(world, ticks, rule=None, keep=False, **settings):
    """Runs the program for `ticks` runs five minutes apart; returns (notes, statuses, commands).
    keep=True carries on from the state of an earlier run, as a restarted duty does."""
    notes, statuses, commands = [], [], []
    world.setdefault("fates", [])
    world.setdefault("ledger", {})
    world.setdefault("cmd_ticks", [])
    world.setdefault("refuse", [])
    world.setdefault("positions", [])
    world.setdefault("seen", [])
    world.setdefault("quotes", [])
    bevo = types.ModuleType("bevo")
    bevo.BevoError = Exception
    bevo.SERVICE_ID = "svc"
    bevo.state = world["state"] = world["state"] if keep else dict(world.get("state0", {}))
    bevo.key = lambda *parts: ":".join(str(p) for p in parts)
    bevo.read = lambda path, q=None: {"account": {"exists": world["free"] is not None,
                                                  "freeForNewPutsUsd": world["free"] or 0,
                                                  "lockedForPutsUsd": world.get("locked", 0),
                                                  "positions": list(world["positions"])}}
    bevo.balance = lambda: types.SimpleNamespace(cash_usd=world["cash"])
    bevo.notify = lambda text, quiet=False, push=None: notes.append(text)
    bevo.log = lambda text: None

    def status(state, **values):
        statuses.append(state)
        world["seen"].append(values.get("seen"))
    bevo.status = status
    def settled(key, route=None, wait=0):
        if key not in world["ledger"]:
            if not world["fates"]:
                return "waiting"
            world["ledger"][key] = world["fates"].pop(0)
        return world["ledger"][key]
    bevo.settled = settled

    def done(text):
        notes.append(text)
        notes.append("DONE")
        raise Done()

    def ticker():
        for i in range(world.get("tick", -1) + 1 if keep else 0, (world.get("tick", -1) + 1 if keep else 0) + ticks):
            world["tick"] = i
            landing = world.get("landing")
            if landing and i >= landing[0]:
                world["free"], world["landing"] = (world["free"] or 0) + landing[1], None
            arriving = world.get("arriving")
            if arriving and i >= arriving[0]:
                world["cash"], world["arriving"] = world["cash"] + arriving[1], None
            world.update(world.get("script", {}).get(i, {}))
            yield i

    bevo.done, bevo.ticks = done, ticker

    def usdc():
        """Its wallet's USDC by chain: world["usdc"] when a test splits it, else all on Ethereum."""
        return world["usdc"] if "usdc" in world else {1: world["cash"]}

    def send_home(chain, amount):
        held = usdc()
        held[chain] = round(held[chain] - amount, 6)
        world["cash"] = sum(held.values()) if "usdc" in world else held[1]
        world.setdefault("sent", []).append((chain, amount))

    def fake_run(argv, **kwargs):
        if argv[0] == sys.executable:  # quote(): the helper
            world["quotes"].append(" ".join(argv[2:]))
            return types.SimpleNamespace(stdout=json.dumps(world["quote"]), stderr="", returncode=0)
        if argv[:2] == ["bevo-wallet", "list"]:  # a read: not one of the commands it files
            assert kwargs["env"]["BUTLER_OUTPUT"] == "json"
            rows = [{"chainId": c, "symbol": "USDC", "amount": "%.6f" % v} for c, v in usdc().items()]
            rows.append({"chainId": 1, "symbol": "ETH", "amount": "0.01"})
            answer = {"wallets": [{"label": "other", "balances": []},
                                  {"label": "eth-puts", "status": "active",
                                   "balances": None if world.get("wallet_unread") else rows}]}
            return types.SimpleNamespace(stdout=json.dumps(answer), stderr="", returncode=0)
        commands.append(" ".join(argv))
        world["cmd_ticks"].append(world["tick"])
        out, code = "{}", 0
        if argv[0] == "bevo-wallet":
            assert kwargs["env"]["BUTLER_OUTPUT"] == "json"
            chain, amount = int(argv[argv.index("--chain-id") + 1]), float(argv[argv.index("--amount") + 1])
            if world.get("home_fails", 0) > 0:
                world["home_fails"] -= 1
                if world.get("sent_anyway"):  # it went through, but answered with an error
                    send_home(chain, amount)
                answer = {"status": "unknown_outcome", "ok": False, "error": "unreachable"}
                return types.SimpleNamespace(stdout=json.dumps(answer), stderr="", returncode=1)
            if world.get("home_card"):
                answer = {"status": "manual_signing_required", "ok": True, "asked": True}
                return types.SimpleNamespace(stdout=json.dumps(answer), stderr="", returncode=0)
            send_home(chain, amount)
            answer = {"status": "executed", "ok": True, "asked": False, "executed": True}
            return types.SimpleNamespace(stdout=json.dumps(answer), stderr="", returncode=0)
        if argv[2] == "deposit":
            amount = float(argv[4])
            world["cash"] -= amount
            world["landing"] = (world["tick"] + 2, amount * 0.99)
        elif argv[2] == "withdraw" and not world["refuse"]:
            amount = float(argv[4])
            world.setdefault("withdrawn", []).append(amount)
            if world.get("withdraw_lost", 0) > 0:  # never ran, but its answer was unclear
                world["withdraw_lost"] -= 1
                return types.SimpleNamespace(stdout=out, stderr="", returncode=code)
            world["free"] -= amount
            world["arriving"] = (world["tick"] + 2, amount * 0.99)
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
    code = make_duty.RULE.sub(lambda _: rule or RULE, program)
    env = {"PARAMS": json.dumps({**SETTINGS, **settings})}
    with mock.patch.dict(sys.modules, {"bevo": bevo}), mock.patch.dict(os.environ, env), \
            mock.patch.object(subprocess, "run", fake_run), \
            mock.patch.object(time, "time", lambda: world.get("t0", 1e9) + world.get("tick", 0) * TICK):
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


PUT = {"instrument": "ETH-20261204-1500-P", "size": -3.33}
HOME = {"WITHDRAW_ON_FINISH": True, "WALLET_LABEL": "eth-puts", "TIMES": 5}
FUNDED = {"deposits": 1, "deposit_at": 0, "free_before": 0}  # its own wallet, deposited long ago
CHECK = "Checking its balance after a settlement"
def send(amount, n, chain=1):
    return ("bevo-wallet withdraw --wallet eth-puts --amount %s --token usdc --chain-id %d "
            "--idempotency-key home:svc:%d:%d" % (amount, chain, n, chain))


def kinds(commands):
    return [c.split()[0] if c.startswith("bevo-wallet") else c.split()[2] for c in commands]


def amounts(world):
    return world.get("withdrawn", [])


class Finishing(unittest.TestCase):
    def test_an_end_date_stops_new_trades_then_sends_everything_home(self):
        world = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: w["tick"] == 0,
                 "fates": ["executed", "executed"]}
        notes, statuses, commands = run(world, 8, END_AT=1e9 + 3 * TICK, **HOME)
        self.assertEqual(kinds(commands), ["open", "withdraw", "bevo-wallet"])
        self.assertIn("withdraw --amount 249.99 --idempotency-key withdraw:svc:0", commands[1])
        self.assertEqual(commands[2], send("247.49", 0))
        self.assertEqual(count(notes, "it reached its end date, so it makes no new trades"), 1)
        self.assertIn("$247.49 went back to your main wallet. 1 trade(s) made.", notes[-2])
        self.assertEqual(notes[-1], "DONE")
        self.assertIn("home", statuses)

    def test_what_it_holds_settles_before_the_money_moves(self):
        world = {"free": 300, "cash": 0, "px": 1480, "met": lambda w: False, "fates": ["executed"],
                 "positions": [PUT], "locked": 700, "script": {4: {"positions": [], "locked": 0}}}
        notes, statuses, commands = run(world, 9, STOP=True, **HOME)
        self.assertEqual(statuses[:4], ["finishing"] * 4)
        self.assertEqual(kinds(commands), ["withdraw", "bevo-wallet"])
        self.assertEqual(world["cmd_ticks"][0], 4)
        self.assertEqual(count(notes, "you stopped it, so it makes no new trades"), 1)
        self.assertEqual(notes[-1], "DONE")

    def test_collateral_still_locked_keeps_it_waiting(self):
        world = {"free": 300, "cash": 0, "px": 1480, "met": lambda w: False, "fates": ["executed"],
                 "locked": 700, "script": {3: {"locked": 0, "free": 1000}}}
        _, statuses, commands = run(world, 7, STOP=True, **HOME)
        self.assertEqual(statuses[:3], ["finishing"] * 3)
        self.assertEqual(amounts(world), [999.99])

    def test_a_last_trade_that_has_not_shown_yet_is_waited_for(self):
        # Review 1: the put shows two runs after its fill; the wind-down must not finish before it settles.
        world = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: w["tick"] == 0,
                 "fates": ["executed", "executed"],
                 "script": {2: {"positions": [PUT], "free": 250, "locked": 750},
                            6: {"positions": [], "free": 1010, "locked": 0}}}
        notes, statuses, commands = run(world, 10, **{**HOME, "TIMES": 1})
        self.assertEqual(kinds(commands), ["open", "withdraw", "bevo-wallet"])
        self.assertEqual(world["cmd_ticks"][1], 6)
        self.assertEqual(amounts(world), [1009.99])
        self.assertGreaterEqual(statuses.count("finishing"), 4)  # landing, then held, then settled
        self.assertIn("all 1 trade(s) made.", notes[-2])

    def test_a_deposit_still_landing_is_waited_for(self):
        # Review 2: the end date comes one run after the deposit; nothing may be left on the venue.
        world = {"free": None, "cash": 1020, "px": 1480, "met": lambda w: False, "fates": ["executed"]}
        notes, statuses, commands = run(world, 8, END_AT=1e9 + 1 * TICK, **HOME)
        self.assertEqual(kinds(commands), ["deposit", "withdraw", "bevo-wallet"])
        self.assertEqual(amounts(world), [1009.79])
        self.assertIn("finishing", statuses)
        self.assertEqual(notes[-1], "DONE")

    def test_settled_cash_that_lands_after_the_withdrawal_goes_too(self):
        world = {"free": 300, "cash": 0, "px": 1480, "met": lambda w: False,
                 "fates": ["executed", "executed"], "script": {2: {"free": 4000.0}}}
        notes, _, commands = run(world, 10, STOP=True, **HOME)
        self.assertEqual(amounts(world), [299.99, 3999.99])  # no haircut after a success
        self.assertEqual(kinds(commands), ["withdraw", "withdraw", "bevo-wallet"])
        self.assertEqual(notes[-1], "DONE")

    def test_the_loss_limit_counts_only_with_nothing_open_and_after_six_hours(self):
        world = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: w["tick"] == 0,
                 "fates": ["executed", "executed"], "state0": FUNDED,
                 "script": {1: {"positions": [PUT], "free": 50, "locked": 900},
                            3: {"positions": [], "free": 700, "locked": 0}}}
        notes, statuses, commands = run(world, 80, ALLOCATION_USD=1000, NEED_USD=100,
                                        MAX_LOSS_USD=200, **HOME)
        self.assertNotIn(CHECK, world["seen"][:2])  # $50 free while the put is open: not a loss
        self.assertEqual(world["seen"].count(CHECK), 72)  # six hours of five-minute runs
        self.assertEqual(count(notes, "Top it up"), 0)
        self.assertEqual(kinds(commands), ["open", "withdraw", "bevo-wallet"])
        self.assertEqual(amounts(world), [699.99])
        self.assertEqual(count(notes, "its losses reached $200, so it makes no new trades"), 1)
        self.assertEqual(notes[-1], "DONE")

    def test_a_shortfall_from_late_settled_cash_is_not_a_loss(self):
        world = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: w["tick"] in (0, 4, 8),
                 "fates": ["executed", "executed"], "state0": FUNDED,
                 "script": {1: {"positions": [PUT], "free": 50, "locked": 900},
                            3: {"positions": [], "free": 50, "locked": 0},
                            6: {"free": 950}}}
        notes, statuses, commands = run(world, 10, ALLOCATION_USD=1000, NEED_USD=100,
                                        MAX_LOSS_USD=200, **HOME)
        self.assertIn(CHECK, world["seen"])
        self.assertEqual(world["cmd_ticks"], [0, 8])  # nothing traded while checking (tick 4)
        self.assertEqual(count(notes, "losses reached"), 0)

    def test_a_loss_counts_from_what_it_deposited(self):
        # $1,020 deposited for $1,000 set aside: back to $1,000 is a $20 loss, past a $15 limit.
        world = {"free": None, "cash": 1020, "px": 1480, "met": lambda w: False, "fates": ["executed"],
                 "script": {6: {"free": 1000.0}}}
        notes, statuses, commands = run(world, 90, ALLOCATION_USD=1000, NEED_USD=100,
                                        MAX_LOSS_USD=15, **HOME)
        self.assertEqual(world["state"]["deposited"], 1020)
        self.assertEqual(count(notes, "its losses reached $15, so it makes no new trades"), 1)
        self.assertEqual(kinds(commands), ["deposit", "withdraw", "bevo-wallet"])

    def test_a_main_wallet_never_reads_a_loss_limit(self):
        # Review 6: the main wallet's account holds the owner's other money and positions.
        world = {"free": 700, "cash": 0, "px": 1480, "met": lambda w: w["tick"] == 2, "fates": ["executed"]}
        notes, statuses, commands = run(world, 4, OWN_WALLET=False, ALLOCATION_USD=1000, NEED_USD=100,
                                        MAX_LOSS_USD=200)
        self.assertNotIn(CHECK, world["seen"])
        self.assertEqual(kinds(commands), ["open"])

    def test_stop_false_does_not_stop_it(self):
        # Review 7.
        for no in ("false", "0", False):
            world = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: w["tick"] == 1, "fates": ["executed"]}
            notes, statuses, commands = run(world, 3, STOP=no, **{**HOME, "TIMES": 2})
            self.assertEqual(kinds(commands), ["open"], no)
            self.assertEqual(count(notes, "you stopped it"), 0)

    def test_its_last_trade_hands_over_to_the_wind_down(self):
        world = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: True,
                 "fates": ["executed", "executed"]}
        notes, _, commands = run(world, 10, **{**HOME, "TIMES": 1})
        self.assertEqual(kinds(commands), ["open", "withdraw", "bevo-wallet"])
        self.assertIn("all 1 trade(s) made.", notes[-2])

    def test_without_the_wind_down_an_end_date_stops_at_once(self):
        world = {"free": 1000, "cash": 0, "px": 1480, "met": lambda w: False}
        notes, _, commands = run(world, 5, OWN_WALLET=False, END_AT=1e9 + 2 * TICK,
                                 WITHDRAW_ON_FINISH=True)  # a main wallet's money is home already
        self.assertEqual(commands, [])
        self.assertEqual(notes[-2:], ["ETH puts: it reached its end date.", "DONE"])

    def test_a_refused_withdrawal_is_said_once_and_tried_again(self):
        busy = {"status": "refused", "ok": False, "code": "OPTIONS_BUSY_X", "httpStatus": 400,
                "error": "a deposit is still landing"}
        world = {"free": 300, "cash": 0, "px": 1480, "met": lambda w: False,
                 "fates": ["dropped", "executed"], "refuse": [busy]}
        notes, _, commands = run(world, 10, STOP=True, **HOME)
        self.assertEqual([c.rsplit(" ", 1)[1] for c in commands if " withdraw " in c and "options" in c],
                         ["withdraw:svc:0", "withdraw:svc:1"])
        self.assertEqual([c.split()[4] for c in commands if "options withdraw" in c], ["299.99", "299.99"])
        self.assertEqual(count(notes, "was refused (a deposit is still landing)"), 1)
        self.assertEqual(notes[-1], "DONE")

    def test_only_more_than_is_free_asks_for_less(self):
        # Review 8: the haircut is for the server's own "only $N is free", nothing else.
        short = {"status": "refused", "ok": False, "code": "OPTIONS_WITHDRAW_TOO_MUCH", "httpStatus": 400,
                 "error": "only $299.98 is free; the rest backs open notes until they settle"}
        world = {"free": 300, "cash": 0, "px": 1480, "met": lambda w: False,
                 "fates": ["dropped", "executed"], "refuse": [short]}
        notes, _, commands = run(world, 10, STOP=True, **HOME)
        self.assertEqual([c.split()[4] for c in commands if "options withdraw" in c], ["299.99", "298.49"])
        self.assertEqual(notes[-1], "DONE")

    def test_an_unclear_withdrawal_is_tried_again_after_an_hour(self):
        # Review 3: unclear, and the money still on the venue: never stuck, never sent twice at once.
        world = {"free": 300, "cash": 0, "px": 1480, "met": lambda w: False,
                 "fates": ["unknown", "executed"], "withdraw_lost": 1}
        notes, _, commands = run(world, 20, STOP=True, **HOME)
        self.assertEqual([c.rsplit(" ", 1)[1] for c in commands if "options withdraw" in c],
                         ["withdraw:svc:0", "withdraw:svc:1"])
        self.assertGreaterEqual(world["cmd_ticks"][1] - world["cmd_ticks"][0], 12)
        self.assertEqual(count(notes, "is unclear"), 1)
        self.assertEqual(notes[-1], "DONE")

    def test_cash_already_in_its_wallet_does_not_count_as_arrived(self):
        # Review 4: $50 sat in its wallet; it waits for the withdrawal itself before sending.
        world = {"free": 300, "cash": 50, "px": 1480, "met": lambda w: False, "fates": ["executed"]}
        notes, _, commands = run(world, 8, STOP=True, **HOME)
        self.assertEqual(world["cmd_ticks"][1], 2)  # sent once the withdrawal landed, not at once
        self.assertIn("$346.99 went back to your main wallet", notes[-2])

    def test_a_send_that_went_through_with_an_error_is_not_resent(self):
        # Review 5.
        world = {"free": 300, "cash": 0, "px": 1480, "met": lambda w: False, "fates": ["executed"],
                 "home_fails": 1, "sent_anyway": True}
        notes, _, commands = run(world, 14, STOP=True, **HOME)
        self.assertEqual([c for c in commands if c.startswith("bevo-wallet")], [send("296.99", 0)])
        self.assertEqual(count(notes, "did not go through"), 0)
        self.assertEqual(notes[-1], "DONE")

    def test_sending_home_is_tried_again_and_said_once(self):
        world = {"free": 300, "cash": 0, "px": 1480, "met": lambda w: False, "fates": ["executed"],
                 "home_fails": 1}
        notes, _, commands = run(world, 14, STOP=True, **HOME)
        self.assertEqual([c for c in commands if c.startswith("bevo-wallet")],
                         [send("296.99", 0), send("296.99", 1)])
        self.assertEqual(count(notes, "did not go through"), 1)
        self.assertEqual(notes[-1], "DONE")

    def test_a_restart_mid_wind_down_carries_on_where_it_was(self):
        world = {"free": 300, "cash": 0, "px": 1480, "met": lambda w: False, "fates": ["executed"]}
        run(world, 2, STOP=True, **HOME)  # withdrawal filed, then the duty restarts
        notes, _, commands = run(world, 6, keep=True, STOP=True, **HOME)
        self.assertEqual(amounts(world), [299.99])  # never filed twice
        self.assertEqual(kinds(commands), ["bevo-wallet"])
        self.assertEqual(count(notes, "so it makes no new trades"), 0)  # said before the restart
        self.assertEqual(notes[-1], "DONE")

    def test_each_chain_is_sent_home_with_the_amount_read_from_the_wallet(self):
        # Its Base change from the deposit and the Ethereum withdrawal, each its own send; dust stays.
        world = {"free": 300, "cash": 40.0, "usdc": {8453: 40.0, 1: 0.0, 42161: 0.4},
                 "px": 1480, "met": lambda w: False, "fates": ["executed"],
                 "script": {2: {"usdc": {8453: 40.0, 1: 296.991234, 42161: 0.4}, "cash": 336.991234}}}
        notes, _, commands = run(world, 8, STOP=True, **HOME)
        self.assertEqual([c for c in commands if c.startswith("bevo-wallet")],
                         [send("296.99", 0), send("40.00", 0, 8453)])
        self.assertEqual(world["sent"], [(1, 296.99), (8453, 40.0)])
        self.assertIn("$336.99 went back to your main wallet", notes[-2])
        self.assertEqual(notes[-1], "DONE")

    def test_a_card_instead_of_a_send_is_left_for_the_owner(self):
        # Finishing withdraws a card still waiting, so it finishes only once the wallet is empty.
        world = {"free": 300, "cash": 0, "px": 1480, "met": lambda w: False, "fates": ["executed"],
                 "home_card": True, "script": {9: {"cash": 0.5}}}
        notes, statuses, commands = run(world, 12, STOP=True, **HOME)
        self.assertEqual([c for c in commands if c.startswith("bevo-wallet")], [send("296.99", 0)])
        self.assertEqual(count(notes, "Approve the card to send it"), 1)
        self.assertEqual(count(notes, "did not go through"), 0)
        self.assertIn("$296.99 went back to your main wallet", notes[-2])
        self.assertEqual(notes[-1], "DONE")

    def test_an_unread_wallet_sends_nothing(self):
        world = {"free": 300, "cash": 0, "px": 1480, "met": lambda w: False, "fates": ["executed"],
                 "wallet_unread": True}
        notes, _, commands = run(world, 6, STOP=True, **HOME)
        self.assertEqual([c for c in commands if c.startswith("bevo-wallet")], [])
        self.assertEqual(count(notes, "did not go through"), 1)
        self.assertNotEqual(notes[-1], "DONE")

    def test_nothing_to_send_home_finishes_quietly(self):
        world = {"free": 0, "cash": 0, "px": 1480, "met": lambda w: False}
        notes, _, commands = run(world, 3, STOP=True, **HOME)
        self.assertEqual(commands, [])
        self.assertIn("Nothing was left to send home", notes[-2])


class AutoRoll(unittest.TestCase):
    QUOTE = {"instrument": "ETH-20261204-1500-P", "size": 3.33, "min_premium_usd": 48.88,
             "collateral": {"amount": 4995}, "apr_pct": 34.0, "tradeable": True, "waivable": False}
    SETTINGS = {"UNDERLYING": "ETH", "ALLOCATION_USD": 5000, "NEED_USD": 150, "TIMES": 3,
                "WITHDRAW_ON_FINISH": True, "WALLET_LABEL": "weekly-eth-puts"}
    EXPIRY = 1796371200  # 4 Dec 2026, 08:00 UTC

    def test_sells_holds_waits_for_settlement_then_sells_the_next(self):
        # Runs every five minutes from 04:40 UTC on 4 Dec: funded at once, on Derive two runs later,
        # the put shows from run 4, expires at 08:00 (run 40) and settles at 08:10 (run 42).
        world = {"t0": self.EXPIRY - 40 * TICK, "free": None, "cash": 5100, "quote": self.QUOTE,
                 "fates": ["executed", "executed"],
                 "script": {4: {"positions": [PUT], "free": 54, "locked": 4995},
                            42: {"positions": [], "free": 5040, "locked": 0}}}
        notes, statuses, commands = run(world, 46, rule=make_duty.AUTO_ROLL, **self.SETTINGS)
        self.assertEqual(kinds(commands), ["deposit", "open", "open"])
        self.assertTrue(commands[1].endswith(
            "open --instrument ETH-20261204-1500-P --size 3.33 --min-premium 48.88 "
            "--max-collateral 4995 --idempotency-key trade:svc:0:0"))
        self.assertTrue(commands[2].endswith("--idempotency-key trade:svc:1:0"))
        self.assertEqual(world["cmd_ticks"][2], 44)  # 08:20: twenty minutes after expiry
        self.assertIn("--collateral 5049.00 --tenor weekly --otm-pct 8 --max-delta 0.15", world["quotes"][0])
        self.assertIn("Its new put is on its way", world["seen"])  # the put not yet in the account
        self.assertIn("Holding $1,500 put, 4 Dec", world["seen"])
        self.assertIn("Its last put is settling", world["seen"])
        self.assertEqual(count(notes, "Placing: sell 3.33 ETH $1,500 put, 4 Dec for at least $48.88, "
                                      "about 34% a year"), 2)
        self.assertEqual(count(notes, "Top it up"), 0)  # its collateral is locked, not short

    def test_collateral_still_locked_means_still_settling(self):
        world = {"t0": self.EXPIRY + 3600, "free": 54, "cash": 0, "quote": self.QUOTE, "fates": [],
                 "locked": 4995, "state0": FUNDED, "script": {3: {"locked": 0, "free": 5040}}}
        notes, statuses, commands = run(world, 5, rule=make_duty.AUTO_ROLL, **self.SETTINGS)
        self.assertEqual(world["seen"][:3], ["Its last put is settling"] * 3)
        self.assertEqual(world["cmd_ticks"], [3])

    def test_its_rule_passes_the_builders_checks(self):
        make_duty.check_rule(make_duty.AUTO_ROLL)


if __name__ == "__main__":
    unittest.main()
