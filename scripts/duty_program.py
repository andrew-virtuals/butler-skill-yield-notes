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
END_AT = float(P.get("END_AT") or 0)  # an epoch: no new trade from then on
MAX_LOSS = float(P.get("MAX_LOSS_USD") or 0)  # no new trade once this much of ALLOCATION is gone
STOP = P.get("STOP") is True or str(P.get("STOP")).strip().lower() == "true"  # never "false" or "0"
WITHDRAW = OWN and bool(P.get("WITHDRAW_ON_FINISH"))  # at the end, everything back to the main wallet
LABEL = str(P.get("WALLET_LABEL") or "")
HOME_WAIT = 24 * 3600  # how long a venue withdrawal may take to reach its wallet
Q = {} if VENUE == "derive" else {"venue": VENUE}
FROM = ["--from", "8453"] if VENUE == "derive" else ["--venue", VENUE]
WHERE = VENUE.title()
S = bevo.state


HELD = {"pocket_pending": "is waiting for you to hold its Start card",
        "pocket_empty": "has used up its limit; raise it and it carries on",
        "OPTIONS_DUTY_CARD_PENDING": "is waiting for you to answer its last card"}


def acp(key, *args):
    """Runs it. A refusal the server gave outright (nothing filed, nothing ran) comes back
    as [code, why]; anything else, an outage included, as None: the ledger tells."""
    if VENUE != "derive" and "--venue" not in args:
        args = (*args, "--venue", VENUE)
    run = subprocess.run(["acp", "options", *args, "--idempotency-key", key],
                         capture_output=True, text=True, timeout=170, check=False)
    text = run.stdout + run.stderr
    held = next((code for code in HELD if code in text), None)
    if held:
        return [held, HELD[held]]
    try:
        answer = json.loads(run.stdout[run.stdout.index("{"):])
    except ValueError:
        return None
    status = answer.get("httpStatus")
    if (run.returncode == 0 or answer.get("status") not in ("refused", "conflict")
            or not isinstance(status, int) or status >= 500 or status == 429
            or str(answer.get("code")).startswith("IDEMPOTEN")):  # the key is on the ledger
        return None
    return [str(answer.get("code") or "refused"), str(answer.get("error") or "refused")[:160]]


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
        if VENUE != "derive" and "--venue" not in args:
            args = (*args, "--venue", VENUE)
        run = subprocess.run([sys.executable, QUOTE_PY, *args], capture_output=True,
                             text=True, timeout=120, check=False)
        if run.returncode == 0:
            return json.loads(run.stdout)
        return {"error": (run.stderr or "no answer").strip()[-200:]}
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)[:200]}


ACCOUNT = {}  # the last account read: locked collateral comes back when a put settles


def free_on_venue():
    """Its free USDC there: 0 before its first deposit, None when unread."""
    global ACCOUNT
    try:
        account = (bevo.read("/options/account", Q) or {}).get("account")
    except bevo.BevoError:
        return None
    if not isinstance(account, dict):
        return None
    ACCOUNT = account
    return float(account.get("freeForNewPutsUsd") or 0) if account.get("exists") else 0.0


def held():
    """Its open options there: [] when none (or no account yet), None when unread."""
    global ACCOUNT
    try:
        account = (bevo.read("/options/account", Q) or {}).get("account")
    except bevo.BevoError:
        return None
    if not isinstance(account, dict):
        return None
    ACCOUNT = account
    if not account.get("exists"):
        return []
    return [row for row in account.get("positions") or [] if float(row.get("size") or 0)]


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
    S["deposited"] = S.get("deposited", 0) + int(cash)  # what a loss is counted from
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
    refused = S.pop("refused", None)
    if fate != "executed" and (fate == "dropped" or refused):  # a refused order never ran
        S["tries"], S["retry_at"] = S.get("tries", 0) + 1, time.time() + 300
        if refused and refused[0] in HELD:
            say("held", f"{NAME}: {line} was not placed: it {refused[1]}. Nothing traded.",
                f"{NAME} needs you")
        elif refused and refused[0] != "OPTIONS_NOT_FILLED":
            say("refused", f"{NAME}: {line} was refused ({refused[1]}). Nothing traded. It "
                f"tries again every five minutes; stop it if this cannot clear.",
                f"{NAME}: refused")
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


def stop_reason():
    """Why it makes no new trade, or None. The loss limit is read in the loop, with the account."""
    if STOP:
        return "you stopped it"
    if S.get("done", 0) >= TIMES:
        return f"all {TIMES} trade(s) made"
    if END_AT and time.time() >= END_AT:
        return "it reached its end date"
    return None


CHECKING = "Checking its balance after a settlement"
LOSS_HOLD = 6 * 3600  # a shortfall must last this long: settled cash can land after its position
# goes, and while it is checked nothing trades, so waiting costs nothing


def loss_check(free):
    """None, "pending" or "hit": MAX_LOSS_USD or more gone from what it deposited (the amount set
    aside before its first deposit), counted on its own account (free plus locked), read only
    with nothing open (a position's swing before it settles never stops it), and still gone six
    hours later (settled cash that lands late is not a loss). While pending it makes no trade.
    Its own wallet only: a main wallet holds the owner's other money and positions."""
    base = S.get("deposited") or ALLOCATION
    if not (MAX_LOSS and OWN) or free is None or base - free < MAX_LOSS:
        S.pop("loss_seen", None)
        return None
    positions = held()
    if positions is None:
        return "pending" if S.get("loss_seen") else None
    locked = float(ACCOUNT.get("lockedForPutsUsd") or 0)
    if positions or locked >= 1 or base - (free + locked) < MAX_LOSS:
        S.pop("loss_seen", None)
        return None
    first = S.setdefault("loss_seen", time.time())
    return "hit" if time.time() - first >= LOSS_HOLD else "pending"


def wallet_cash():
    """USDC in its own wallet; None when unread."""
    try:
        return bevo.balance().cash_usd
    except bevo.BevoError:
        return None


def wallet_home(key):
    """Every dollar in its own wallet back to the owner's main wallet. True once sent."""
    try:
        run = subprocess.run(["bevo-wallet", "withdraw", "--wallet", LABEL, "--idempotency-key", key],
                             capture_output=True, text=True, timeout=170, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return run.returncode == 0


def depositing(free):
    """A deposit on its way to the venue: made in the last 30 minutes and not landed yet."""
    return (OWN and bool(S.get("deposits")) and free <= S.get("free_before", 0) + 1
            and time.time() - S.get("deposit_at", 0) < 1800)


def done_home(reason):
    cash = S.get("home_cash")
    sent = f"${cash:,.2f}" if cash and cash >= 2 else "What was in its wallet"
    bevo.done(f"{NAME}: {reason}. {sent} went back to your main wallet. "
              f"{S.get('done', 0)} trade(s) made.")


def finish(reason):
    """No new trade from here. Without WITHDRAW_ON_FINISH it stops now. With it, it waits until
    nothing ties money to the venue (no position, no locked collateral, no fill or deposit still
    landing), takes all its USDC off the venue, waits for that to reach its wallet, sends
    everything in its wallet back to the main wallet (`bevo-wallet withdraw`), and then stops.
    Money that shows up on the venue before the end sends it back to the withdrawal."""
    if not WITHDRAW:
        bevo.done(f"{NAME}: {reason}.")
        return
    if not S.get("finishing_said"):
        S["finishing_said"] = True
        bevo.notify(f"{NAME}: {reason}, so it makes no new trades. Once what it holds has "
                    f"settled, it sends all its money back to your main wallet.",
                    push=f"{NAME} is finishing")
    now, positions = time.time(), held()
    if positions is None:
        bevo.status("unreadable")
        return
    free = float(ACCOUNT.get("freeForNewPutsUsd") or 0) if ACCOUNT.get("exists") else 0.0
    locked = float(ACCOUNT.get("lockedForPutsUsd") or 0)
    phase = S.get("phase", "settle")
    if phase != "withdrawing":
        if positions or locked >= 1:
            S["phase"] = "settle"
            bevo.status("finishing", venue=WHERE)
            return
        if now - S.get("traded_at", 0) < 900 or depositing(free):  # a fill or deposit landing
            S["phase"] = "settle"
            bevo.status("finishing", venue=WHERE)
            return
        if phase == "home" and free >= 10:  # settled cash that landed after the withdrawal
            phase = S["phase"] = "settle"
    if phase == "settle":
        if free >= 1:
            if now >= S.get("wretry_at", 0):
                # A cent under the figure read (the server may round it up), and 0.5% less for
                # each "only $N is free" refusal.
                cut = 1 - 0.005 * min(S.get("wrefusals", 0), 10)
                amount = math.floor((free - 0.01) * cut * 100) / 100
                n = S.get("withdrawals", 0)
                S.setdefault("wbase", wallet_cash() or 0.0)  # its wallet before any withdrawal
                S.update(wkey=bevo.key("withdraw", bevo.SERVICE_ID, n), withdrawals=n + 1,
                         phase="withdrawing", wamount=amount, wsent_at=now)
                S["refused"] = acp(S["wkey"], "withdraw", "--amount", f"{amount:.2f}")
            bevo.status("home")
            return
        phase = S["phase"] = "home"
        S["home_from"] = now
    if phase == "withdrawing":
        fate = bevo.settled(S["wkey"], route="options", wait=60)
        if fate in ("waiting", "approval"):
            bevo.status("home")
            return
        refused = S.pop("refused", None)
        if fate == "executed" or (fate != "dropped" and not refused and free < 1):
            # It ran, or its answer is unclear but the money has left the venue.
            S["wtotal"] = S.get("wtotal", 0) + S.get("wamount", 0)
            S["wrefusals"] = 0
            S["phase"], S["home_from"] = "home", now
        elif fate == "dropped" or refused:  # never ran: try again in five minutes
            S["phase"], S["wretry_at"] = "settle", now + 300
            why = refused[1] if refused else "it was not filed"
            if "free" in why.lower():
                S["wrefusals"] = S.get("wrefusals", 0) + 1
            say("withdraw", f"{NAME}: taking its money off {WHERE} was refused ({why}). It tries "
                f"again every five minutes.", f"{NAME}: withdrawal refused")
            bevo.status("home")
            return
        else:  # unclear and the money is still there: an hour, then a new try, as the venue
            # pays out no more than is free, and only to this wallet
            if now - S.get("wsent_at", now) < 3600:
                say("withdraw_unclear", f"{NAME}: its withdrawal from {WHERE} is unclear; it "
                    f"checks again within the hour before trying once more.",
                    f"{NAME}: withdrawal unclear")
            else:
                S["phase"] = "settle"
            bevo.status("home")
            return
    # Home: wait for what was withdrawn to reach its wallet, then send everything back.
    cash = wallet_cash()
    if S.get("homes") and cash is not None and cash < 2:  # an earlier send went through after all
        done_home(reason)
        return
    waited = now - S.get("home_from", now)
    want = S.get("wbase", 0) + 0.9 * S.get("wtotal", 0)
    if waited < HOME_WAIT and (cash is None or (S.get("wtotal") and cash < want)):
        bevo.status("home")
        return
    if not S.get("wtotal") and cash is not None and cash < 2:
        bevo.done(f"{NAME}: {reason}. Nothing was left to send home. "
                  f"{S.get('done', 0)} trade(s) made.")
        return
    if now < S.get("home_retry", 0):
        bevo.status("home")
        return
    n = S.get("homes", 0)
    S["homes"] = n + 1
    S.setdefault("home_cash", cash)
    if wallet_home(bevo.key("home", bevo.SERVICE_ID, n)):
        done_home(reason)
        return
    after = wallet_cash()
    if cash is not None and cash >= 2 and after is not None and after < 2:  # it went through
        done_home(reason)
        return
    S["home_retry"] = now + 1800
    say("home", f"{NAME}: sending its money back to your main wallet did not go through. It "
        f"tries again every 30 minutes.", f"{NAME}: not sent home yet")
    bevo.status("home")


for tick in bevo.ticks():
    if follow_up():
        continue
    reason = S.get("finishing") or stop_reason()
    if reason:
        S["finishing"] = reason
        finish(reason)
        continue
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
    loss = loss_check(free) if S.get("ready") else None
    if loss == "hit":
        S["finishing"] = f"its losses reached ${MAX_LOSS:,.0f}"
        finish(S["finishing"])
        continue
    if loss == "pending":
        bevo.status("watching", seen=CHECKING, free=round(free), venue=WHERE)
        continue
    met, seen = trigger()
    # Collateral an open put locks comes back when it settles: short only if it fired now, or
    # free and locked together cannot pay for the next trade.
    locked = float(ACCOUNT.get("lockedForPutsUsd") or 0)
    if free < NEED and (met or free + locked < NEED):
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
