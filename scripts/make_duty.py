#!/usr/bin/env python3
"""Builds a duty that trades options (references/duty.md), so nothing is retyped.

It copies scripts/duty_program.py, puts the duty's own trigger() and order() into it,
saves the program in the workspace and prints the whole `duty_create` payload: the
title, the timer, the status lines, the settings and what funds it. Stdlib only, no
network, no secret; it files nothing and moves nothing.

  python3 make_duty.py --name 'ETH puts below $1,500' --spec '<the owner ask>' \\
      --wallet own --wallet-label eth-puts --set-aside 1000 --need 750 --times 1 \\
      --every 300 --rule ~/duties/eth-puts/rule.py --param STRIKE=1500 --param SIZE=0.5

  python3 make_duty.py --name 'Weekly ETH puts' --spec '<the owner ask>' --preset auto-roll \\
      --wallet own --wallet-label weekly-eth-puts --set-aside 5000 --need 150 --times 14 \\
      --end-at 2027-02-23 --max-loss 500 --param UNDERLYING=ETH

`--preset auto-roll` is a rule this script holds (AUTO_ROLL, duty.md "Auto-roll"): a weekly
put sold whenever nothing is open, from its own wallet, with everything sent back to the
main wallet at the end.

Exit 0: one JSON object on stdout. Exit 2: the request cannot be built, with why on
stderr. `"deposit_first"` in the answer means the main wallet is short on the venue:
deposit that, and build again once it shows free.
"""

import argparse
import ast
import datetime
import json
import math
import os
import re
import sys
import time
import types

HERE = os.path.dirname(os.path.realpath(__file__))
PROGRAM = os.path.join(HERE, "duty_program.py")
QUOTE_PY = os.path.join(HERE, "quote.py")
RULE = re.compile(r"# >>> rule.*?# <<< rule\n", re.S)
NAME_MAX = 38
MIN_VENUE_DEPOSIT = 11


def with_bridge(usd):
    """What to send for `usd` to arrive: 2% for the bridge, at most $2, rounded up."""
    return math.ceil(usd + min(usd * 0.02, 2))


OWN_SETTINGS = ("NAME", "VENUE", "OWN_WALLET", "ALLOCATION_USD", "NEED_USD", "TIMES", "QUOTE_PY",
                "END_AT", "MAX_LOSS_USD", "WITHDRAW_ON_FINISH", "WALLET_LABEL", "STOP")
PROGRAM_PARTS = {"acp", "say", "quote", "free_on_venue", "held", "move_in", "short", "follow_up",
                 "stop_reason", "loss_check", "wallet_cash", "wallet_home", "depositing",
                 "done_home", "finish"}
STATUS = {
    "moving": "Moving ${amount} to {venue}",
    "setting_up": "Setting up: ${free} of ${allocation} on {venue}",
    "unfunded": "Waiting for its funding card",
    "watching": "{seen} · ${free} free on {venue}",
    "short": "${gap} short on {venue} · top it up to trade",
    "placed": "Placed: {order} · waiting on {venue}",
    "retrying": "{seen} · not placed yet, trying again",
    "unreadable": "Couldn't read the options account · retrying",
    "finishing": "Finishing: waiting for {venue} to settle",
    "home": "Finishing: bringing its money home",
}

# duty.md "Auto-roll": a weekly put whenever nothing is open, the strike nearest spot at least
# MIN_BELOW_PCT under it with a delta of MAX_DELTA or less, sized to all its free USDC.
AUTO_ROLL = '''UNDERLYING = str(P["UNDERLYING"]).upper()
BELOW = float(P.get("MIN_BELOW_PCT", 8))
ODDS = float(P.get("MAX_DELTA", 0.15))
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
SETTLE_GRACE = 1200  # after a put's 08:00 UTC expiry, before the next one is sold


def expiry_of(name):
    """ETH-20261204-1500-P's expiry, 08:00 UTC that day, as an epoch; 0 when unreadable."""
    try:
        day = str(name).split("-")[1]
        y, m, d = int(day[:4]), int(day[4:6]), int(day[6:8])
    except (IndexError, ValueError):
        return 0
    y -= m <= 2  # days since 1 January 1970, counted on the calendar, not read off a clock
    era, yoe = y // 400, y % 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    days = era * 146097 + yoe * 365 + yoe // 4 - yoe // 100 + doy - 719468
    return days * 86400 + 8 * 3600


def put_line(name):
    """ETH-20261204-1500-P as "$1,500 put, 4 Dec"."""
    try:
        _, day, strike, _ = str(name).split("-")
        return "$%s put, %d %s" % (format(float(strike.replace("_", ".")), ",.0f"), int(day[6:]),
                                   MONTHS[int(day[4:6]) - 1])
    except (ValueError, IndexError):
        return str(name)


def trigger():
    """The next put is due once nothing is open and the last one has settled: no collateral
    locked, and 20 minutes past its expiry. Or none was sold yet."""
    positions = held()
    if positions is None:
        return False, "Its account unread"
    if positions:
        S["ar_expiry"] = max(expiry_of(row.get("instrument")) for row in positions)
        return False, "Holding " + put_line(positions[0].get("instrument"))
    if float(ACCOUNT.get("lockedForPutsUsd") or 0) > 0 or time.time() < S.get("ar_expiry", 0) + SETTLE_GRACE:
        return False, "Its last put is settling"
    if time.time() - S.get("traded_at", 0) < 900:
        return False, "Its new put is on its way"
    return True, "nothing open, so the next put is due"


def order():
    """This week's put by the rule, sized to all its free USDC."""
    free = free_on_venue()
    if not free:
        return None, "its free USDC unread"
    q = quote("quote", "--product", "cash_secured_put", "--underlying", UNDERLYING,
              "--collateral", "%.2f" % free, "--tenor", "weekly",
              "--otm-pct", "%g" % BELOW, "--max-delta", "%g" % ODDS)
    if q.get("error"):
        return None, "the quote failed (%s)" % q["error"]
    if not q.get("tradeable") or q.get("waivable"):
        return None, "the quote is not tradeable now"
    return (["open", "--instrument", q["instrument"], "--size", "%g" % q["size"],
             "--min-premium", "%g" % q["min_premium_usd"],
             "--max-collateral", "%g" % q["collateral"]["amount"]],
            "sell %g %s %s for at least $%s, about %d%% a year" % (
                q["size"], UNDERLYING, put_line(q["instrument"]),
                format(q["min_premium_usd"], ",.2f"), round(q["apr_pct"])))
'''
PRESETS = {"auto-roll": AUTO_ROLL}


class Refused(Exception):
    pass


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def check_rule(source):
    """The rule file is Python that defines trigger() and order(), and quotes with quote()."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise Refused("the rule file is not valid Python: line %s: %s" % (exc.lineno, exc.msg))
    defined = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    for name in ("trigger", "order"):
        if name not in defined:
            raise Refused("the rule file defines no %s()" % name)
    fixed = defined & PROGRAM_PARTS
    if fixed:
        raise Refused("the rule file redefines %s; write only trigger() and order() (and helpers of "
                      "your own)" % ", ".join(sorted(fixed)))
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    if "quote" not in calls:
        raise Refused("order() must price the trade now with quote(...), the helper's own figures")
    for verb, bounds in (("open", ("--min-premium", "--max-collateral")), ("buy", ("--max-cost",))):
        if '"%s"' % verb in source or "'%s'" % verb in source:
            for flag in bounds:
                if flag not in source:
                    raise Refused("order() files `%s` without %s: every order carries the bound "
                                  "from its quote" % (verb, flag))
    if not any('"%s"' % v in source or "'%s'" % v in source for v in ("open", "buy", "close")):
        raise Refused("order() returns no `open`, `buy` or `close` argv")
    for clock in ("tm_hour", "tm_wday", "tm_mday", ".hour", ".weekday(", "strftime("):
        if clock in source:
            raise Refused("the rule reads the clock with `%s`, which the agent refuses under this "
                          "timer: compare timestamps (time.time() against an epoch, or an anchor "
                          "plus whole periods), as duty.md's schedule does" % clock)
    for banned, why in (("--limit", "a duty takes the order book or an RFQ at the quote's bound"),
                        ("--min-price", "a resting order is filed from chat (resting.md)"),
                        ("--max-price", "a resting order is filed from chat (resting.md)"),
                        ("quote.py", "call quote(...), never the helper by a path"),
                        ("python3", "call quote(...), never python3"),
                        ("bevo.notify", "the program sends the notes; return the line to say"),
                        ("bevo.status", "the program writes the status; return what trigger() saw"),
                        ("bevo.done", "the program stops itself after TIMES trades"),
                        ("bevo-wallet", "the program sends the money home itself (--withdraw-on-finish)"),
                        ("idempotency", "the program adds the key; order() returns the argv without one")):
        if banned in source:
            raise Refused("the rule file has `%s`: %s" % (banned, why))


def try_trigger(rule, params):
    """Runs trigger() once against stand-ins: it must answer (True or False, a line to say).
    A rule that cannot run on stand-in figures is left to its first real run."""
    stand_in = types.SimpleNamespace(read=lambda *a, **k: {}, BevoError=Exception,
                                     balance=lambda: types.SimpleNamespace(cash_usd=0.0))
    scope = {"P": dict(params), "S": {}, "time": time, "math": math, "json": json, "bevo": stand_in,
             "quote": lambda *a: {"spot": 1.0, "error": "a stand-in"}}
    try:
        exec(compile(rule, "rule.py", "exec"), scope)
        answer = scope["trigger"]()
    except Exception:
        return
    if not (isinstance(answer, tuple) and len(answer) == 2 and isinstance(answer[0], bool)
            and isinstance(answer[1], str) and answer[1].strip()):
        raise Refused("trigger() answered %r: it returns (True or False, \"what it saw\"), "
                      "True only at the moment to trade" % (answer,))


def setting(text):
    key, sep, raw = text.partition("=")
    if not sep or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
        raise Refused("--param takes KEY=VALUE with an UPPER_CASE key, got %r" % text)
    if key in OWN_SETTINGS:
        raise Refused("--param %s is set by this script's own flags" % key)
    try:
        return key, json.loads(raw)
    except ValueError:
        return key, raw


def build(a):
    name = a.name.strip()
    if not name or len(name) > NAME_MAX:
        raise Refused("--name is the duty's title: 1 to %d characters, what it does and when "
                      "(got %d)" % (NAME_MAX, len(name)))
    for flag, text in (("--name", name), ("--spec", a.spec)):
        if re.search(r"(^|\s),\d{3}\b", text):
            raise Refused("%s reads %r: the shell ate a $ figure. Put --name and --spec in "
                          "single quotes" % (flag, text))
    if a.times is None:  # auto-roll: a put a week to its end date, and one more
        a.times = 1
        if a.preset == "auto-roll" and a.end_at:
            try:
                ends = datetime.datetime.strptime(a.end_at, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
                a.times = max(1, math.ceil((ends.timestamp() - time.time()) / (7 * 86400)) + 1)
            except ValueError:
                pass
    if a.need <= 0 or a.set_aside <= 0 or a.times < 1:
        raise Refused("--need and --set-aside are dollars above 0, --times at least 1")
    if a.need > a.set_aside:
        raise Refused("one trade needs $%g, more than the $%g set aside: ask the owner for a "
                      "bigger total or a smaller trade" % (a.need, a.set_aside))
    own = a.wallet == "own"
    if own and not a.wallet_label:
        raise Refused("--wallet own needs --wallet-label, the label `bevo-wallet create` was given")
    if own and a.set_aside < MIN_VENUE_DEPOSIT:
        raise Refused("its own wallet needs at least $%d set aside, the venue's minimum deposit; "
                      "recommend the main wallet" % MIN_VENUE_DEPOSIT)
    if not own and a.free is None:
        raise Refused("--wallet main needs --free, `freeForNewPutsUsd` on that venue from this "
                      "turn's `acp options account`")
    if a.preset:
        if not own:
            raise Refused("--preset %s trades from its own wallet only: --wallet own" % a.preset)
        if a.venue != "derive" or a.every != 300:
            raise Refused("--preset %s runs on Derive, every 300 seconds: leave out --venue and "
                          "--every" % a.preset)
        rule, a.withdraw_on_finish = PRESETS[a.preset], True
    else:
        try:
            rule = read(os.path.expanduser(a.rule))
        except OSError as exc:
            raise Refused("the rule file could not be read: %s" % exc)
    check_rule(rule)
    if a.withdraw_on_finish and not own:
        raise Refused("--withdraw-on-finish is for its own wallet; a main-wallet duty's money is "
                      "home already")
    if a.max_loss is not None and not own:
        raise Refused("--max-loss is for its own wallet: a main-wallet duty shares the account "
                      "with the owner's other money and positions")
    if a.max_loss is not None and not 0 < a.max_loss <= a.set_aside:
        raise Refused("--max-loss is dollars above 0 and at most the $%g set aside" % a.set_aside)
    end_at = None
    if a.end_at:
        try:
            end_at = int(datetime.datetime.strptime(a.end_at, "%Y-%m-%d").replace(
                tzinfo=datetime.timezone.utc).timestamp())
        except ValueError:
            raise Refused("--end-at is a date, YYYY-MM-DD, got %r" % a.end_at)
        if end_at <= time.time():
            raise Refused("--end-at %s has already passed" % a.end_at)

    if not own and a.free < a.set_aside:
        gap = a.set_aside - a.free
        return {"deposit_first": {
            "amount_usdc": max(MIN_VENUE_DEPOSIT, with_bridge(gap)),
            "venue": a.venue,
            "why": "the owner set aside $%g and $%g is free on %s; deposit this (SKILL.md step 4), "
                   "ask them to approve its card, file nothing more this turn, and build again "
                   "once the account shows it free" % (a.set_aside, a.free, a.venue.title()),
        }}

    extra = dict(setting(p) for p in a.param)
    if a.preset == "auto-roll" and (not a.end_at or a.max_loss is None):
        raise Refused("--preset auto-roll needs --end-at and --max-loss: the owner's end date and "
                      "loss limit (duty.md offers 13 weeks and 10%% of the amount set aside)")
    if a.preset == "auto-roll" and not str(extra.get("UNDERLYING") or "").strip():
        raise Refused("--preset auto-roll needs --param UNDERLYING=ETH (or BTC): the asset it "
                      "sells puts on")
    try_trigger(rule, extra)

    program = read(PROGRAM)
    if len(RULE.findall(program)) != 1:
        raise Refused("duty_program.py has lost its rule marks; reinstall the skill")
    code = RULE.sub(lambda _: "# the rule\n" + rule.strip("\n") + "\n", program)
    compile(code, "duty.py", "exec")

    # Letters only: the agent refuses a name carrying a figure that is one of its settings.
    slug = a.slug or re.sub(r"[^a-z]+", "-", name.lower()).strip("-")[:60] or "options-duty"
    if not re.fullmatch(r"[a-z][a-z-]{1,63}", slug):
        raise Refused("--slug is lower-case letters and dashes, no figures")
    out_dir = os.path.expanduser(a.out or os.path.join("~", "duties", slug))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "duty.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)

    params = {"NAME": name, "VENUE": a.venue, "OWN_WALLET": own, "ALLOCATION_USD": a.set_aside,
              "NEED_USD": a.need, "TIMES": a.times, "QUOTE_PY": QUOTE_PY}
    if end_at:
        params["END_AT"] = end_at
    if a.max_loss is not None:
        params["MAX_LOSS_USD"] = a.max_loss
    if a.withdraw_on_finish:
        params["WITHDRAW_ON_FINISH"], params["WALLET_LABEL"] = True, a.wallet_label
    params.update(extra)
    payload = {
        "name": slug,
        "spec": a.spec,
        "title": "{NAME}",
        "movesFunds": True,
        "triggers": [{"kind": "timer", "intervalSeconds": a.every, "untilDone": True}],
        "spendBasis": {"perTrade": "NEED_USD", "times": "TIMES"},
        # Both as JSON text: that is the type the duty_create tool declares for them.
        "statusTemplate": json.dumps(STATUS, ensure_ascii=False),
        "params": json.dumps(params, ensure_ascii=False),
        "codePath": os.path.relpath(os.path.realpath(path), os.path.realpath(os.path.expanduser("~"))),
    }
    if own:
        payload["walletId"] = a.wallet_label
        payload["fundUsdc"] = with_bridge(a.set_aside)
        then = ("one funding card for $%d moves it to the duty's wallet; the duty deposits it on "
                "%s itself and says when it is ready" % (payload["fundUsdc"], a.venue.title()))
    else:
        payload["pocketUsdc"] = 0 if a.card_each_trade else a.set_aside
        then = ("every trade asks with its own card" if a.card_each_trade else
                "one Start card proposes a $%g limit; once the owner holds it, each trade it covers "
                "runs with no card" % a.set_aside)
    return {"duty_create": payload, "saved": path, "say": then,
            "next": "pass `duty_create` to the duty_create tool exactly as printed; never retype "
                    "the program or send `code`"}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", required=True, help="its title, at most %d characters" % NAME_MAX)
    p.add_argument("--spec", required=True, help="the owner's ask, in their words")
    p.add_argument("--wallet", required=True, choices=("own", "main"))
    p.add_argument("--wallet-label", help="own: the label given to `bevo-wallet create`")
    p.add_argument("--set-aside", required=True, type=float, help="dollars the owner set aside in total")
    p.add_argument("--need", required=True, type=float, help="dollars one trade needs")
    p.add_argument("--times", type=int, default=None,
                   help="how many trades, then it stops (1; auto-roll: the weeks to --end-at, plus one)")
    p.add_argument("--venue", default="derive", choices=("derive", "paradex"))
    p.add_argument("--every", type=int, default=300, choices=(60, 300),
                   help="seconds between runs: 60 for a set time, 300 for a price or a schedule")
    how = p.add_mutually_exclusive_group(required=True)
    how.add_argument("--rule", help="the .py file with this duty's trigger() and order()")
    how.add_argument("--preset", choices=sorted(PRESETS),
                     help="a rule this script holds: auto-roll (duty.md), its own wallet only")
    p.add_argument("--param", action="append", default=[], metavar="KEY=VALUE",
                   help="one of the rule's figures, read from P in the rule; repeat it")
    p.add_argument("--free", type=float, help="main: free USDC on the venue now")
    p.add_argument("--card-each-trade", action="store_true",
                   help="main: only when the owner asked for a card on every trade")
    p.add_argument("--end-at", help="YYYY-MM-DD: no new trade from that day (00:00 UTC) on")
    p.add_argument("--max-loss", type=float,
                   help="dollars: no new trade once this much of the amount set aside is gone")
    p.add_argument("--withdraw-on-finish", action="store_true",
                   help="own: at the end, let what it holds settle, then send everything back to "
                        "the main wallet (always on with --preset auto-roll)")
    p.add_argument("--slug", help="its name; made from --name when left out")
    p.add_argument("--out", help="where to save duty.py; ~/duties/<slug> when left out")
    a = p.parse_args(argv)
    try:
        print(json.dumps(build(a), indent=2, ensure_ascii=False))
    except Refused as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
