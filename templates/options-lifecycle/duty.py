"""Watch one yield note from open to outcome, and say what happened.

A note is one option the owner sold on Derive, Paradex or Rysk (VENUE), fully
collateralised; a bought option is one they paid a premium for. The options-trading skill opens either
and files this duty with the fill's own numbers.
Two moments matter and the owner should never have to ask about either:

    the day before   where the asset is, and which way the note is leaning
    settlement       what they kept, or what they agreed to buy or sell

It only watches and reports: it runs no command, so it files as a duty that
moves no money and gets no pocket. A sold put whose owner asked to end up
owning the asset is filed as `options-put-delivery` instead, which buys it.

A duty has no network of its own, so both prices come through the options
rail: the heads-up reads Derive's own index for this option
(`bevo.read("/options/ticker")`), the price it will settle against, and the
settlement comes from `bevo.read("/options/settlement")`. That works for every
currency Derive lists options on.

Derive and Paradex settle options in **cash**. An in-the-money put reduces
USDC; it does not hand over ETH. So the duty never says "you now own 2.04 ETH":
it says the owner is holding the loss in cash, because that is what has happened.

Rysk settles **physically**: an assigned put delivers the asset to the owner's
HyperEVM wallet, so there is no delivery buy. Near the strike the maker holding
the option chooses whether to exercise it, so the outcome is what Rysk paid out
(the account read's `settled`), never inferred from the price.

Settings: VENUE, INSTRUMENT, PRODUCT, UNDERLYING, STRIKE, SIZE,
PREMIUM_USD, COLLATERAL_USD, HEADS_UP_HOURS.
"""

import bevo
import datetime
import json
import os
import re
import time

PARAMS = json.loads(os.environ.get("PARAMS", "{}"))

VENUE = str(PARAMS.get("VENUE") or "derive").strip().lower()
VENUE_NAME = {"derive": "Derive", "paradex": "Paradex", "rysk": "Rysk"}.get(VENUE, VENUE)
#: Every options read names the venue, except Derive's: a Derive duty reads exactly
#: what it read before venues existed.
VENUE_QUERY = {} if VENUE == "derive" else {"venue": VENUE}
INSTRUMENT = str(PARAMS.get("INSTRUMENT") or "").strip().upper()
PRODUCT = str(PARAMS.get("PRODUCT") or "").strip()
UNDERLYING = str(PARAMS.get("UNDERLYING") or "").strip().upper()
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


def parse_instrument(name):
    """Pull expiry and option type back out of ETH-20261030-2450-P (Derive),
    ETH-USD-30OCT26-2450-P (Paradex) or ETH-30OCT26-2450-P (Rysk).

    Derive and Paradex write a decimal strike with an underscore
    (ADA-...-0_25-P), Rysk with a point (HYPE-6NOV26-56.5-P), so the strike is
    parsed but never trusted over the STRIKE setting. The name gives the day at
    08:00 UTC, when every Derive, Rysk and Paradex crypto option expires; a
    Paradex stock, index or commodity option expires later that day, which
    `stated_expiry()` reads.
    """
    if VENUE == "rysk":
        m = re.match(r"^([A-Z0-9]+)-(\d{1,2}[A-Z]{3}\d{2})-(\d+(?:\.\d+)?)-([PC])$", name)
        day_format = "%d%b%y"
    elif VENUE == "paradex":
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


DETAIL = parse_instrument(INSTRUMENT) if INSTRUMENT else None

#: Sold notes (income) and bought options, by the option type each must be.
PRODUCT_KIND = {"cash_secured_put": "P", "covered_call": "C", "long_call": "C", "long_put": "P"}

EXAMPLE = {"paradex": "ETH-USD-30OCT26-2450-P", "rysk": "ETH-30OCT26-2450-P"}.get(VENUE, "ETH-20261030-2450-P")

if VENUE not in ("derive", "paradex", "rysk"):
    PROBLEM = "VENUE must be derive, paradex or rysk, not %r" % VENUE
elif not DETAIL:
    PROBLEM = "INSTRUMENT %r is not a %s option name like %s" % (INSTRUMENT, VENUE_NAME, EXAMPLE)
elif VENUE == "rysk" and PRODUCT != "cash_secured_put":
    PROBLEM = "on Rysk only a sold put (cash_secured_put) is watched, not %r" % PRODUCT
elif PRODUCT not in PRODUCT_KIND:
    PROBLEM = "PRODUCT must be one of %s, not %r" % (", ".join(sorted(PRODUCT_KIND)), PRODUCT)
elif DETAIL["kind"] != PRODUCT_KIND[PRODUCT]:
    PROBLEM = "%s is a %s but PRODUCT says %s" % (
        INSTRUMENT, "put" if DETAIL["kind"] == "P" else "call", PRODUCT)
elif not INSTRUMENT.startswith(UNDERLYING + "-"):
    PROBLEM = "%s is not an option on UNDERLYING %s" % (INSTRUMENT, UNDERLYING)
elif SIZE <= 0 or STRIKE <= 0:
    PROBLEM = "SIZE and STRIKE must both be above zero"

EXPIRY = DETAIL["expiry"] if DETAIL else 0
IS_PUT = PRODUCT == "cash_secured_put"


def stated_expiry():
    """Moves EXPIRY to the instant Paradex states, once it has been read.

    A Paradex stock, index or commodity option expires at its market's close
    (META at 20:00 or 21:00 UTC, CL at 18:30 or 19:30), not at the name's 08:00
    UTC. The ticker states it (`expirySec`), and it is kept, since an expired
    market may no longer be listed. Until it is read the name's 08:00 stands,
    which can only be early: the heads-up comes sooner and the duty waits
    longer for the settlement price, which it says it is doing.
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
IS_LONG = PRODUCT in ("long_call", "long_put")
IS_CALL = PRODUCT_KIND.get(PRODUCT) == "C"


def intrinsic(px):
    """What the option is worth at `px`: what a bought one is paid at expiry."""
    return max(0.0, (px - STRIKE) if IS_CALL else (STRIKE - px)) * SIZE


def still_held():
    """Whether the account still holds this option, bought or sold. None when unreadable.

    A bought option can be sold back, and a sold note bought back, before expiry;
    the skill deletes this duty when it is, and this is the duty's own check in
    case that was missed.
    """
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
        size = float(row.get("size") or 0)
        if row.get("instrument") == INSTRUMENT and (size > 0 if IS_LONG else size < 0):
            return True
    return False


def closed_early():
    """"closed", "unsure" or "held", from this tick's account read.

    Two "not held" reads in a row, 15 minutes apart, before it counts: ending
    early on one empty read would cost an owner who still holds the option its
    heads-up and its outcome. An unreadable account is held; it never ends a duty.
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
    """Derive's index for this option's underlying right now, or None for no price this run.

    For the heads-up only; settlement never reads this. It is the venue's own
    index, the number the option settles against, so it needs no token pin and
    works for any currency Derive lists. An empty answer is a gap, not a zero.
    """
    body = bevo.read("/options/ticker", {"instrument": INSTRUMENT, **VENUE_QUERY}) or {}
    value = body.get("index")
    if value in (None, ""):
        return None
    spot = float(value)
    return spot if spot > 0 else None


def settlement_price():
    """The settlement Derive printed for this expiry.

    None means not published yet. A BevoError means the rail cannot answer at
    all — a different thing, and the owner is told about it rather than being
    given a guess.
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


def option_key(name):
    """A Rysk name as (underlying, expiry, strike, type), so 95 and 95.0 are one strike."""
    m = re.match(r"^([A-Z0-9]+)-(\d{1,2}[A-Z]{3}\d{2})-(\d+(?:\.\d+)?)-([PC])$", str(name or ""))
    return (m.group(1), m.group(2), float(m.group(3)), m.group(4)) if m else None


def rysk_payout():
    """This put's row in the account's `settled` once Rysk has paid it out, else None.

    A BevoError means the account cannot be read, which settle() reports as such.
    """
    body = bevo.read("/options/account", VENUE_QUERY) or {}
    rows = [r for r in ((body.get("account") or {}).get("settled") or [])
            if option_key(r.get("instrument")) == option_key(INSTRUMENT)]
    # One owner can sell the same put twice; this duty is the one of this size.
    sized = [r for r in rows if abs(float(r.get("size") or 0) - SIZE) < 1e-9]
    return (sized or rows or [None])[0]


def rysk_outcome(row, settled):
    """What Rysk paid out, in the owner's terms. `settled` may still be None."""
    back = " + ".join("%s %s" % (fmt(leg["amount"]), leg["symbol"]) for leg in row.get("received") or [])
    at = ""
    if settled:
        at = " at %s, %s your %s" % (price(settled), "under" if settled < STRIKE else "at or above",
                                     price(STRIKE))
    if row.get("assigned"):
        text = ("%s settled%s. Your put was assigned: Rysk delivered %s to your HyperEVM wallet, "
                "bought at %s each." % (UNDERLYING, at, back, price(STRIKE)))
        if settled:
            shortfall = max(0.0, STRIKE - settled) * SIZE
            net = PREMIUM_USD - shortfall
            text += (" That is %s more than they were worth at settlement; after the %s premium "
                     "you are %s %s." % (usd(shortfall), usd(PREMIUM_USD),
                                         "down" if net < 0 else "up", usd(abs(net))))
        return text + " The %s is yours to keep; selling it is a separate trade." % UNDERLYING
    ended = "was not exercised" if settled and settled < STRIKE else "expired worthless"
    return ("%s settled%s. Your put %s: Rysk returned %s to your HyperEVM wallet, and you keep "
            "the %s premium." % (UNDERLYING, at, ended, back or "your collateral", usd(PREMIUM_USD)))


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
    if IS_LONG:
        kind = "call" if IS_CALL else "put"
        worth = intrinsic(spot)
        if worth > 0:
            leaning = ("is in the money: if it ends here it pays about %s, against the %s it cost"
                       % (usd(worth), usd(PREMIUM_USD)))
        else:
            leaning = ("is out of the money: it pays nothing unless %s ends %s %s"
                       % (UNDERLYING, "above" if IS_CALL else "below", price(STRIKE)))
        bevo.notify("%s: %s is at %s. Your %s %s. It settles in about %d hours."
                    % (NAME, UNDERLYING, price(spot), kind, leaning, round(hours)))
        bevo.state["heads_up_sent"] = True
        return
    if IS_PUT:
        leaning = ("looks set to pay out in full" if spot >= STRIKE else
                   "is under your price, so you may end up buying %s at %s"
                   % (UNDERLYING, price(STRIKE)))
    else:
        leaning = ("looks set to pay out in full, and you keep your %s" % UNDERLYING
                   if spot <= STRIKE else
                   "is above your price, so your %s may be sold at %s"
                   % (UNDERLYING, price(STRIKE)))
    bevo.notify("%s: %s is at %s. Your note %s. It settles in about %d hours."
                % (NAME, UNDERLYING, price(spot), leaning, round(hours)))
    bevo.state["heads_up_sent"] = True


def outcome_sentences(settled):
    """What actually happened, in the owner's terms. Returns (headline, assigned).

    The assigned-put headline says "agreed to buy", not "have bought": Derive
    and Paradex settle in cash, so the owner owns no asset.
    """
    if IS_LONG:
        kind = "call" if IS_CALL else "put"
        side = "above" if settled > STRIKE else "under"
        paid = intrinsic(settled)
        if paid > 0:
            net = paid - PREMIUM_USD
            return ("%s settled at %s, %s your %s: your %s paid %s into your %s account. After "
                    "the %s it cost, you are %s %s."
                    % (UNDERLYING, price(settled), side, price(STRIKE), kind, usd(paid), VENUE_NAME,
                       usd(PREMIUM_USD), "down" if net < 0 else "up", usd(abs(net))), False)
        return ("%s settled at %s, %s your %s: the %s expired worthless, so the %s you paid is lost."
                % (UNDERLYING, price(settled), "at or under" if IS_CALL else "at or above",
                   price(STRIKE), kind, usd(PREMIUM_USD)), False)
    if IS_PUT:
        if settled >= STRIKE:
            kept = COLLATERAL_USD or (STRIKE * SIZE)
            return ("%s settled at %s, above your %s. You kept your %s and the %s premium."
                    % (UNDERLYING, price(settled), price(STRIKE), usd(kept), usd(PREMIUM_USD)), False)
        shortfall = (STRIKE - settled) * SIZE
        net = PREMIUM_USD - shortfall
        return ("%s settled at %s, under your %s. Your note was assigned: you agreed to buy "
                "%s %s at %s, which is %s more than they are worth today. After the %s premium "
                "you are %s %s."
                % (UNDERLYING, price(settled), price(STRIKE), fmt(SIZE), UNDERLYING,
                   price(STRIKE), usd(shortfall), usd(PREMIUM_USD),
                   "down" if net < 0 else "up", usd(abs(net))), True)
    if settled <= STRIKE:
        return ("%s settled at %s, under your %s. You kept your %s and the %s premium."
                % (UNDERLYING, price(settled), price(STRIKE), UNDERLYING, usd(PREMIUM_USD)), False)
    given_up = (settled - STRIKE) * SIZE
    return ("%s settled at %s, above your %s. Your %s %s was sold at %s. You gave up %s of "
            "further upside, and kept the %s premium."
            % (UNDERLYING, price(settled), price(STRIKE), fmt(SIZE), UNDERLYING,
               price(STRIKE), usd(given_up), usd(PREMIUM_USD)), True)


def settle():
    """Read the settlement, say what happened, and finish."""
    late = time.time() - EXPIRY
    try:
        settled = settlement_price()
    except bevo.BevoError as exc:
        say("could not read settlement: %s" % exc)
        if late > SETTLE_ALARM_SECONDS and not bevo.state.get("settle_alarm"):
            bevo.state["settle_alarm"] = True
            bevo.notify("%s: your note has expired and I cannot read what it settled at, so I "
                        "will not guess. Your money is not at risk from this - it is my read "
                        "that is broken. I will keep trying." % NAME)
        bevo.status("settling")
        bevo.fail("settlement unreadable: %s" % exc)
        return

    if VENUE == "rysk":
        settle_rysk(late, settled)
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

    headline, assigned = outcome_sentences(settled)
    bevo.state["settled_price"] = settled

    tail = ""
    if assigned and IS_PUT:
        tail = (" %s settles in cash, so you are holding the loss in cash, not the %s."
                % (VENUE_NAME, UNDERLYING))
    if IS_LONG:
        if intrinsic(settled) > 0:
            tail += " The payout is free cash in your %s account." % VENUE_NAME
    elif IS_PUT:
        tail += " What is left of your collateral is free cash in your %s account." % VENUE_NAME
    else:
        tail += " What is left of your %s collateral is free again in your %s account." % (
            UNDERLYING, VENUE_NAME)

    bevo.status("done", price=settled)
    bevo.done("%s: %s%s" % (NAME, headline, tail))


def settle_rysk(late, settled):
    """Finish once Rysk has paid out; until then wait, as for a missing price."""
    try:
        row = rysk_payout()
    except bevo.BevoError as exc:
        say("could not read the Rysk account: %s" % exc)
        row = None
    if row is None:
        if late > SETTLE_ALARM_SECONDS and not bevo.state.get("settle_alarm"):
            bevo.state["settle_alarm"] = True
            bevo.notify("%s: your put expired %d hours ago and Rysk has not paid it out yet. "
                        "Nothing is lost and I am still watching." % (NAME, round(late / 3600)))
        else:
            say("Rysk has not paid out %s yet (%d min past expiry)" % (INSTRUMENT, round(late / 60)))
        bevo.status("settling")
        return
    if settled:
        bevo.state["settled_price"] = settled
        bevo.status("done", price=settled)
    else:
        bevo.status("paid")
    bevo.done("%s: %s" % (NAME, rysk_outcome(row, settled)))


def fire():
    stated_expiry()
    left = EXPIRY - time.time()

    # Every tick until expiry, so a close the skill forgot to clean up still ends
    # the duty. After expiry the position is gone either way and says nothing.
    # A Rysk put cannot be closed early.
    if left > 0 and VENUE != "rysk":
        seen = closed_early()
        if seen == "closed":
            bevo.status("closed")
            bevo.done("%s: your %s was %s before expiry, so there is nothing left to watch."
                      % (NAME, INSTRUMENT, "sold back" if IS_LONG else "bought back"))
        if seen == "unsure":
            say("%s is not in the account on this read; checking again next tick" % INSTRUMENT)
            bevo.status("unseen")
            return

    # The owner's Duties row: recipe.json `status` words each state.
    if left > 0:
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
