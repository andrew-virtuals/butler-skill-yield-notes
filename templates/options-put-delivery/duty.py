"""Watch one sold put to its outcome, and buy the asset if it is assigned.

A note is one cash-secured put the owner sold on Derive or Paradex (VENUE),
fully collateralised. The options-trading skill files this duty instead of
`options-lifecycle` only when the owner asked, before the open, to end up
owning the asset. Three moments matter and the owner should never have to ask
about any of them:

    the day before   where the asset is, and which way the note is leaning
    settlement       what they kept, or what they agreed to buy
    after that       the asset itself, bought for them

Derive and Paradex settle options in **cash**. An in-the-money put reduces
USDC; it does not hand over ETH. So "you now own 2.04 ETH" is only true once
the spot buy here has actually executed. Until then the duty says the owner is
holding the loss in cash, because that is what has happened.

Both prices come through the options rail: the heads-up reads the venue's own
index for this option (`bevo.read("/options/ticker")`) and the settlement
comes from `bevo.read("/options/settlement")`. TOKEN_ID pins the token the
delivery buy trades, on its own chain.

Rysk settles physically, so an assigned Rysk put needs no buy: it is watched
by `options-lifecycle`.

Settings: VENUE, INSTRUMENT, UNDERLYING, TOKEN_ID, STRIKE, SIZE, PREMIUM_USD,
COLLATERAL_USD, HEADS_UP_HOURS.
"""

import bevo
import datetime
import json
import math
import os
import re
import subprocess
import time

PARAMS = json.loads(os.environ.get("PARAMS", "{}"))

VENUE = str(PARAMS.get("VENUE") or "derive").strip().lower()
VENUE_NAME = {"derive": "Derive", "paradex": "Paradex"}.get(VENUE, VENUE)
#: Every options read names the venue, except Derive's, as options-lifecycle does.
VENUE_QUERY = {} if VENUE == "derive" else {"venue": VENUE}
INSTRUMENT = str(PARAMS.get("INSTRUMENT") or "").strip().upper()
UNDERLYING = str(PARAMS.get("UNDERLYING") or "").strip().upper()
TOKEN_ID = str(PARAMS.get("TOKEN_ID") or "").strip()
STRIKE = float(PARAMS.get("STRIKE") or 0)
SIZE = float(PARAMS.get("SIZE") or 0)
PREMIUM_USD = float(PARAMS.get("PREMIUM_USD") or 0)
COLLATERAL_USD = float(PARAMS.get("COLLATERAL_USD") or 0)
HEADS_UP_HOURS = float(PARAMS.get("HEADS_UP_HOURS") or 24)

NAME = os.environ.get("BEVO_SERVICE_NAME") or "your note"

#: Settlement is published shortly after expiry, not at the stroke of it. Below this the duty waits quietly rather than reporting a
#: missing price as a problem.
SETTLE_GRACE_SECONDS = 20 * 60

#: Past this with still no price, say so out loud: a settlement that never
#: lands is an incident, not a delay.
SETTLE_ALARM_SECONDS = 6 * 3600

PROBLEM = ""


def say(text):
    """`bevo.log()` on one line: an echoed error must not forge a log line."""
    bevo.log(" ".join(str(text).split()))


def fmt(number):
    return ("%.8f" % float(number)).rstrip("0").rstrip(".")


def usd(number):
    return "$%s" % format(round(float(number), 2), ",.2f")


def price(number):
    """Prices are read aloud, so trim them to something a person says."""
    n = float(number)
    return "$%s" % format(round(n, 2 if n < 100 else 0), ",.2f" if n < 100 else ",.0f")


def answer_of(text):
    """The JSON `acp` printed, or None. None is NOT a refusal."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = json.loads(text)
    except ValueError:
        start = text.find("{")
        if start < 0:
            return None
        try:
            value, _ = json.JSONDecoder().raw_decode(text, start)
        except ValueError:
            return None
    return value if isinstance(value, dict) else None


def parse_instrument(name):
    """Pull expiry and option type back out of ETH-20261030-2450-P (Derive) or
    ETH-USD-30OCT26-2450-P (Paradex).

    The strike is parsed but never trusted over the STRIKE setting. The name
    gives the day at 08:00 UTC, when every Derive and Paradex crypto option
    expires; a Paradex stock, index or commodity option expires later that
    day, which `stated_expiry()` reads.
    """
    if VENUE == "paradex":
        m = re.match(r"^([A-Z0-9]+)-USD-(\d{1,2}[A-Z]{3}\d{2})-([0-9_]+)-([PC])$", name)
        day_format = "%d%b%y"
    else:
        m = re.match(r"^([A-Z0-9]+)-(\d{8})-([0-9_]+)-([PC])$", name)
        day_format = "%Y%m%d"
    if not m:
        return None
    _, day, _strike, kind = m.groups()
    try:
        # Pinned to UTC: read in a DST zone this is an hour out, enough to
        # call settlement before it has happened.
        moment = datetime.datetime.strptime(day.title() + " 08:00", day_format + " %H:%M")
        expiry = int(moment.replace(tzinfo=datetime.timezone.utc).timestamp())
    except ValueError:
        return None
    return {"expiry": expiry, "kind": kind}


def parse_pin(pin):
    """`native:<chainId>` or `<address>:<chainId>` → (token-out, chain id). None otherwise.

    A tokenized stock (`stock:<TICKER>:0`) is no option's underlying, so it is
    not accepted here.
    """
    m = re.match(r"^(native|0x[0-9a-fA-F]{40}):([0-9]+)$", pin)
    if not m:
        return None
    token, chain = m.groups()
    return ("eth" if token == "native" else token), int(chain)


DETAIL = parse_instrument(INSTRUMENT) if INSTRUMENT else None
PIN = parse_pin(TOKEN_ID) if TOKEN_ID else None

EXAMPLE = "ETH-USD-30OCT26-2450-P" if VENUE == "paradex" else "ETH-20261030-2450-P"

if VENUE not in ("derive", "paradex"):
    PROBLEM = ("VENUE must be derive or paradex, not %r: an assigned Rysk put delivers the asset "
               "itself, so options-lifecycle watches it" % VENUE)
elif not DETAIL:
    PROBLEM = "INSTRUMENT %r is not a %s option name like %s" % (INSTRUMENT, VENUE_NAME, EXAMPLE)
elif DETAIL["kind"] != "P":
    PROBLEM = "%s is a call: only a sold put is assigned into buying the asset" % INSTRUMENT
elif not INSTRUMENT.startswith(UNDERLYING + "-"):
    PROBLEM = "%s is not an option on UNDERLYING %s" % (INSTRUMENT, UNDERLYING)
elif SIZE <= 0 or STRIKE <= 0:
    PROBLEM = "SIZE and STRIKE must both be above zero"
elif not PIN:
    PROBLEM = ("TOKEN_ID %r is not a pinned token like native:8453 or <address>:<chainId>"
               % TOKEN_ID)

EXPIRY = DETAIL["expiry"] if DETAIL else 0


def stated_expiry():
    """Moves EXPIRY to the instant Paradex states, once it has been read.

    A Paradex stock, index or commodity option expires at its market's close,
    not at the name's 08:00 UTC. The ticker states it (`expirySec`), and it is
    kept, since an expired market may no longer be listed. Until it is read the
    name's 08:00 stands, which can only be early.
    """
    global EXPIRY
    if VENUE != "paradex" or not DETAIL:
        return
    kept = bevo.state.get("expiry_sec")
    if kept:
        EXPIRY = int(kept)
        return
    try:
        body = bevo.read("/options/ticker", {"instrument": INSTRUMENT, **VENUE_QUERY}) or {}
    except bevo.BevoError as exc:
        if not bevo.state.get("expiry_unread"):
            bevo.state["expiry_unread"] = True
            say("could not read when %s expires, so its name's 08:00 UTC stands: %s" % (INSTRUMENT, exc))
        return
    try:
        stated = int(body.get("expirySec") or 0)
    except (TypeError, ValueError):
        stated = 0
    # The same day as the name, or it is not this option's.
    if 0 <= stated - DETAIL["expiry"] < 86400:
        bevo.state["expiry_sec"] = stated
        EXPIRY = stated


def still_held():
    """Whether the account still holds this put sold. None when unreadable."""
    try:
        body = (bevo.read("/options/account", VENUE_QUERY) if VENUE_QUERY
                else bevo.read("/options/account")) or {}
    except bevo.BevoError as exc:
        say("could not read the account: %s" % exc)
        return None
    account = body.get("account")
    if not isinstance(account, dict):
        return None
    for row in account.get("positions") or []:
        if row.get("instrument") == INSTRUMENT and float(row.get("size") or 0) < 0:
            return True
    return False


def closed_early():
    """"closed", "unsure" or "held", from this tick's account read.

    Two "not held" reads in a row, 15 minutes apart, before it counts: ending
    early on one empty read would cost an owner who still holds the put its
    heads-up, its outcome and its delivery. An unreadable account is held.
    """
    held = still_held()
    if held is False:
        misses = int(bevo.state.get("not_held_reads") or 0) + 1
        bevo.state["not_held_reads"] = misses
        return "closed" if misses >= 2 else "unsure"
    if held is True:
        bevo.state["not_held_reads"] = 0
    return "held"


def spot_now():
    """The venue's index for this option right now, or None for no price this run."""
    body = bevo.read("/options/ticker", {"instrument": INSTRUMENT, **VENUE_QUERY}) or {}
    value = body.get("index")
    if value in (None, ""):
        return None
    spot = float(value)
    return spot if spot > 0 else None


def settlement_price():
    """The settlement the venue printed for this option. None means not published yet.

    A BevoError means the rail cannot answer at all, which settle() reports
    rather than guessing, and never buys on.
    """
    # Paradex keys a settlement by the option itself; Derive by asset and expiry.
    query = ({"instrument": INSTRUMENT, **VENUE_QUERY} if VENUE_QUERY
             else {"underlying": UNDERLYING, "expiry": EXPIRY})
    body = bevo.read("/options/settlement", query) or {}
    value = body.get("price")
    if value in (None, ""):
        return None
    settled = float(value)
    return settled if settled > 0 else None


def heads_up():
    """Once, the day before: where the asset is and which way this is leaning."""
    try:
        spot = spot_now()
    except bevo.BevoError as exc:
        say("could not read the price for the heads-up: %s" % exc)
        return
    if spot is None:
        say("no index for %s this run; the heads-up waits for the next tick" % INSTRUMENT)
        return
    hours = max(0, (EXPIRY - time.time()) / 3600.0)
    leaning = ("looks set to pay out in full" if spot >= STRIKE else
               "is under your price, so you may end up buying %s at %s; if it settles there, "
               "I will buy the %s for you" % (UNDERLYING, price(STRIKE), UNDERLYING))
    bevo.notify("%s: %s is at %s. Your note %s. It settles in about %d hours."
                % (NAME, UNDERLYING, price(spot), leaning, round(hours)))
    bevo.state["heads_up_sent"] = True


def deliver(settled):
    """Buy the asset the owner has just agreed to buy. One key, never retried.

    It buys the pinned token (TOKEN_ID) on the pin's own chain, never a bare
    ticker. `acp trade` spends USDC, so SIZE of the asset is bought as SIZE x
    the settlement price in USDC, rounded up to the cent: roughly SIZE units,
    since the market has moved on since expiry.

    Returns "done", "pending", "refused" or "unknown". An unparseable answer
    is "unknown", never "refused": the request may have landed, and only
    `bevo.exec_status(key)` can say.
    """
    key = "note:%s:deliver" % bevo.SERVICE_ID
    token_out, chain = PIN
    spend = math.ceil(SIZE * settled * 100) / 100.0
    done = subprocess.run(
        ["acp", "trade", "--token-in", "usdc", "--chain-in", str(chain),
         "--amount-in", "%.2f" % spend, "--token-out", token_out,
         "--chain-out", str(chain), "--idempotency-key", key],
        capture_output=True, text=True, timeout=180, check=False,
    )
    answer = answer_of(done.stdout)
    if answer is None:
        state = (bevo.exec_status(key) or {}).get("state")
        say("delivery buy outcome UNKNOWN (exec_status: %s) - not retried" % state)
        return "unknown"
    if answer.get("executed"):
        return "done"
    if answer.get("asked") or answer.get("ok"):
        return "pending"
    if answer.get("unrecognized"):
        say("delivery buy: unrecognised answer %r - treated as unknown" % answer.get("status"))
        return "unknown"
    say("delivery buy refused: %s" % (answer.get("error") or answer.get("status")))
    return "refused"


def settle():
    """Read the settlement, say what happened, buy the asset if assigned, and finish."""
    late = time.time() - EXPIRY
    try:
        settled = settlement_price()
    except bevo.BevoError as exc:
        say("could not read settlement: %s" % exc)
        if late > SETTLE_ALARM_SECONDS and not bevo.state.get("settle_alarm"):
            bevo.state["settle_alarm"] = True
            bevo.notify("%s: your note has expired and I cannot read what it settled at, so I "
                        "will not guess, and I will buy nothing until I can. Your money is not "
                        "at risk from this - it is my read that is broken. I will keep trying."
                        % NAME)
        bevo.status("settling")
        bevo.fail("settlement unreadable: %s" % exc)
        return

    if settled is None:
        if late > SETTLE_ALARM_SECONDS and not bevo.state.get("settle_alarm"):
            bevo.state["settle_alarm"] = True
            bevo.notify("%s: your note expired %d hours ago and %s has not published a "
                        "settlement price yet. Nothing is lost and I am still watching."
                        % (NAME, round(late / 3600), VENUE_NAME))
        else:
            say("settlement not published yet (%d min past expiry)" % round(late / 60))
        bevo.status("settling")
        return

    bevo.state["settled_price"] = settled
    tail = " What is left of your collateral is free cash in your %s account." % VENUE_NAME
    if settled >= STRIKE:
        kept = COLLATERAL_USD or (STRIKE * SIZE)
        bevo.status("done", price=settled)
        bevo.done("%s: %s settled at %s, above your %s. You kept your %s and the %s premium, "
                  "so there was nothing to buy.%s"
                  % (NAME, UNDERLYING, price(settled), price(STRIKE), usd(kept), usd(PREMIUM_USD), tail))
        return

    shortfall = (STRIKE - settled) * SIZE
    net = PREMIUM_USD - shortfall
    headline = ("%s settled at %s, under your %s. Your note was assigned: you agreed to buy "
                "%s %s at %s, which is %s more than they are worth today. After the %s premium "
                "you are %s %s."
                % (UNDERLYING, price(settled), price(STRIKE), fmt(SIZE), UNDERLYING,
                   price(STRIKE), usd(shortfall), usd(PREMIUM_USD),
                   "down" if net < 0 else "up", usd(abs(net))))

    # The last account read before expiry did not find the put, so it may have
    # been bought back in the final minutes: a buy now could be for a note the
    # owner no longer has.
    if int(bevo.state.get("not_held_reads") or 0) > 0:
        bought = (" Your put was missing from your %s account at my last check before expiry, so "
                  "I did not buy the %s; check your positions." % (VENUE_NAME, UNDERLYING))
    else:
        result = deliver(settled)
        if result == "done":
            bought = " I have bought the %s for you, so you now own about %s %s." % (
                UNDERLYING, fmt(SIZE), UNDERLYING)
        elif result == "pending":
            bought = (" Buying the %s is waiting on your approval; until it goes through "
                      "you are holding the loss in cash, not the %s." % (UNDERLYING, UNDERLYING))
        elif result == "refused":
            bought = " I could not buy the %s, so you are holding the loss in cash." % UNDERLYING
        else:
            bought = (" I am not certain whether the %s purchase went through; check before "
                      "buying again." % UNDERLYING)

    bevo.status("done", price=settled)
    bevo.done("%s: %s%s%s" % (NAME, headline, bought, tail))


def fire():
    stated_expiry()
    left = EXPIRY - time.time()

    if left > 0:
        seen = closed_early()
        if seen == "closed":
            bevo.status("closed")
            bevo.done("%s: your %s was bought back before expiry, so there is nothing left to "
                      "watch or buy." % (NAME, INSTRUMENT))
            return
        if seen == "unsure":
            say("%s is not in the account on this read; checking again next tick" % INSTRUMENT)
            bevo.status("unseen")
            return

        if left >= 2 * 86400:
            bevo.status("days", days=int(left // 86400))
        elif left >= 2 * 3600:
            bevo.status("hours", hours=int(left // 3600))
        else:
            bevo.status("soon")

    if left > HEADS_UP_HOURS * 3600:
        say("%s: %.1f days to expiry" % (INSTRUMENT, left / 86400.0))
        return

    if left > 0:
        if not bevo.state.get("heads_up_sent"):
            heads_up()
        else:
            say("%s: %.1f hours to expiry, heads-up already sent" % (INSTRUMENT, left / 3600.0))
        return

    if -left < SETTLE_GRACE_SECONDS:
        say("%s expired %d min ago; waiting for the settlement price" % (INSTRUMENT, round(-left / 60)))
        bevo.status("settling")
        return

    settle()


if PROBLEM:
    bevo.notify("%s does nothing until its settings are fixed: %s." % (NAME, PROBLEM))
    bevo.status("paused")

for tick in bevo.ticks():
    if PROBLEM:
        bevo.status("paused")
        bevo.fail("settings: %s" % PROBLEM)
        continue
    fire()
