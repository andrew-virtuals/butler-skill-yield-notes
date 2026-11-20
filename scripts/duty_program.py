"""The program of a duty that trades options (references/duty.md).

Never edited by hand for a duty: scripts/make_duty.py copies it and puts the duty's own
trigger() and order() between the rule marks. Everything else is the same for every duty:
its money is on the venue before it watches, it never deposits when it fires, it says
when it is ready, short, fired and how each order ended, and each trouble once.
"""
import json, math, os, subprocess, sys, time
import bevo

P = json.loads(os.environ.get("PARAMS") or "{}")
NAME = P["NAME"]
VENUE = str(P.get("VENUE") or "derive").lower()
OWN = bool(P.get("OWN_WALLET"))
ALLOCATION = float(P["ALLOCATION_USD"])
NEED = float(P["NEED_USD"])
TIMES = int(P.get("TIMES", 1))
QUOTE_PY = P["QUOTE_PY"]
Q = {} if VENUE == "derive" else {"venue": VENUE}
FROM = ["--from", "8453"] if VENUE == "derive" else ["--venue", VENUE]
WHERE = VENUE.title()
S = bevo.state


HELD = {"pocket_pending": "is waiting for you to hold its Start card",
        "pocket_empty": "has used up its limit; raise it and it carries on",
        "OPTIONS_DUTY_CARD_PENDING": "is waiting for you to answer its last card"}


def acp(key, *args):
    """Runs it; returns which of HELD refused it, or ""."""
    run = subprocess.run(["acp", "options", *args, "--idempotency-key", key],
                         capture_output=True, text=True, timeout=170, check=False)
    return next((code for code in HELD if code in run.stdout + run.stderr), "")


def say(kind, text, push):
    """One note per kind of trouble until it clears; a repeat goes to the log only."""
    if kind in S.get("said", []):
        bevo.log(text)
        return
    S["said"] = S.get("said", []) + [kind]
    bevo.notify(text, push=push)


def quote(*args):
    """The helper (helper.md), e.g. quote("quote", "--side", "buy", ...): its JSON, or
    {"error": why} when it failed."""
    try:
        run = subprocess.run([sys.executable, QUOTE_PY, *args], capture_output=True,
                             text=True, timeout=120, check=False)
        if run.returncode == 0:
            return json.loads(run.stdout)
        return {"error": (run.stderr or "no answer").strip()[-200:]}
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)[:200]}


def free_on_venue():
    """Its free USDC there: 0 before its first deposit, None when unread."""
    try:
        account = (bevo.read("/options/account", Q) or {}).get("account")
    except bevo.BevoError:
        return None
    if not isinstance(account, dict):
        return None
    return float(account.get("freeForNewPutsUsd") or 0) if account.get("exists") else 0.0


# >>> rule: trigger() and order(), written for each duty (make_duty.py puts them here)
def trigger():
    """The owner's rule. (True, "ETH at $1,480") to trade now, else (False, "ETH at $1,790")."""
    raise NotImplementedError


def order():
    """The trade, quoted now with quote(): (argv after `acp options`, a line saying it),
    or (None, why) when the quote failed or is not tradeable."""
    raise NotImplementedError
# <<< rule


def move_in(free):
    """Its own wallet's USDC onto the venue. True when it deposited: that run trades nothing."""
    if not OWN or time.time() - S.get("deposit_at", 0) < 600:
        return False
    cash = bevo.balance().cash_usd
    if cash is None or cash < 10:
        return False
    n = S.get("deposits", 0)
    acp(bevo.key("deposit", bevo.SERVICE_ID, n), "deposit", "--amount", str(int(cash)), *FROM)
    S["deposits"], S["deposit_at"], S["free_before"] = n + 1, time.time(), free
    bevo.status("moving", amount=int(cash), venue=WHERE)
    return True


def short(free, met, seen):
    """Short of the next trade: tell the owner once per balance, and once per missed fire."""
    gap = math.ceil(NEED - free)
    ask = max(gap, 10) if OWN else gap  # its wallet moves nothing to the venue under $10
    if S.get("low_at") != round(free):
        S["low_at"] = round(free)
        bevo.notify(f"{NAME}: ${free:,.0f} free on {WHERE}; its next trade needs ${NEED:,.0f}. "
                    f"Top it up by ${ask:,} and it carries on.", push=f"{NAME} is ${gap:,} short")
    if met and not S.get("missed"):
        S["missed"] = True
        bevo.notify(f"{NAME}: {seen}, but it is ${gap:,} short on {WHERE}, so nothing traded. "
                    f"Top it up and it trades the next time.", push=f"{NAME} fired, short ${gap:,}")
    bevo.status("short", gap=gap, venue=WHERE)


def follow_up():
    """How a placed order ended, told once. True while it is still running."""
    key = S.get("key")
    if not key:
        return False
    fate = bevo.settled(key, route="options", wait=60)
    if fate in ("waiting", "approval"):
        bevo.status("placed", order=S.get("placing") or "the order", venue=WHERE)
        return True
    line = S.pop("placing", "the order")
    del S["key"]
    held = HELD.get(S.pop("refused", ""))
    if fate == "dropped" or held:  # a held-back trade never ran, whatever the ledger says
        S["tries"], S["retry_at"] = S.get("tries", 0) + 1, time.time() + 300
        if held:
            say("held", f"{NAME}: {line} was not placed: it {held}. Nothing traded.",
                f"{NAME} needs you")
        else:
            say("missed", f"{NAME}: {line} did not fill at its bound; nothing traded. It "
                f"keeps trying while its trigger holds.", f"{NAME}: not filled")
        return False
    S.pop("said", None)
    S["done"], S["traded_at"] = S.get("done", 0) + 1, time.time()  # a rule reads traded_at
    if fate == "executed":
        bevo.notify(f"{NAME}: done, {line}. Trade {S['done']} of {TIMES}.", push=f"{NAME}: filled")
    else:
        bevo.notify(f"{NAME}: {line} may have gone through; your options account on {WHERE} "
                    f"says for sure. It is counted, never sent again.", push=f"{NAME}: unclear")
    return False


for tick in bevo.ticks():
    if follow_up():
        continue
    if S.get("done", 0) >= TIMES:
        bevo.done(f"{NAME}: all {TIMES} trade(s) made.")
    free = free_on_venue()
    if free is None:
        bevo.status("unreadable")
        continue
    if move_in(free):
        continue
    arriving = OWN and (not S.get("deposits") or (free <= S["free_before"] + 1
                                                   and time.time() - S["deposit_at"] < 1800))
    if free < NEED and arriving:
        if S.get("deposits") or time.time() - S.setdefault("born", time.time()) < 1800:
            bevo.status("setting_up", free=round(free), allocation=round(ALLOCATION), venue=WHERE)
            continue
        if not S.get("unfunded"):  # funding card declined or never answered
            S["unfunded"] = True
            bevo.notify(f"{NAME}: its wallet is still empty, so it has not started. Approve "
                        f"its funding card, or ask Butler to fund it.",
                        push=f"{NAME} is not funded")
        bevo.status("unfunded")
        continue
    if not S.get("ready") and free >= NEED:
        S["ready"] = True
        bevo.notify(f"{NAME}: ${free:,.0f} ready on {WHERE}. Watching now.",
                    push=f"{NAME} is ready")
    met, seen = trigger()
    if free < NEED:
        short(free, met, seen)
        continue
    S.pop("low_at", None)
    S.pop("missed", None)
    if not met:
        S.pop("said", None)
        S.pop("noquote", None)
        bevo.status("watching", seen=seen, free=round(free), venue=WHERE)
        continue
    if time.time() < S.get("retry_at", 0):  # five minutes between tries
        bevo.status("retrying", seen=seen)
        continue
    argv, line = order()
    if not argv:
        S["noquote"], S["retry_at"] = S.get("noquote", 0) + 1, time.time() + 300
        if S["noquote"] >= 3:  # a blip is logged; a quote still failing is told once
            say("noquote", f"{NAME}: {seen}, but {line}; nothing traded. It keeps trying.",
                f"{NAME} cannot quote")
        else:
            bevo.log(f"{seen}, but {line}")
        bevo.status("retrying", seen=seen)
        continue
    S.pop("noquote", None)
    key = bevo.key("trade", bevo.SERVICE_ID, S.get("done", 0), S.get("tries", 0))
    say("fired", f"{NAME}: {seen}. Placing: {line}.", f"{NAME} fired")
    S["refused"] = acp(key, *argv)
    S["key"], S["placing"] = key, line
    follow_up()
