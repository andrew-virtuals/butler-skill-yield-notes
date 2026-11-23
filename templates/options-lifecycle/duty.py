"""Watch every option the owner holds, on every venue and in every wallet, to its outcome.

One duty per owner, with nothing to set. It reads what the accounts hold, so it needs no
filing per trade: an option bought or sold from the chat, a resting order once it fills,
and a position a duty opened from a wallet of its own are all watched the same way. Two
moments matter and the owner should never have to ask about either:

    the day before   where the asset is, and which way the option is leaning
    settlement       what it paid or cost, or what they agreed to buy or sell

It only watches and reports: it runs no command, so it is filed as a duty that moves no
money and gets no pocket.

Where it looks, every run:

    the main wallet   `bevo.read("/options/account")`: every venue's account at once
    a Butler wallet   each "<platform> · <duty>" Platforms row Butler's server keeps
                      (`serverKept`) is one wallet's own Derive or Paradex account; it is
                      read with that wallet's id (`walletId`) and that venue

What it remembers of a position is what the account said last: its size, and what it cost
or brought in (`costUsd`, fees included). A position gone before expiry on two reads in a
row was closed, and is dropped without a word: the close had its own note. At expiry the
venue takes the position out of the account, so the outcome is told from what was last
seen. An account that cannot be read changes nothing.

Both prices come through the options rail: the heads-up reads the venue's own index for
the option (`/options/ticker`), the price it settles against, and the outcome reads
`/options/settlement`. Derive and Paradex settle in **cash**: an assigned put reduces
USDC and hands over no asset, and the duty says so. Rysk settles **physically**, and near
the strike its maker chooses whether to exercise, so a Rysk outcome is what Rysk paid out
(the account read's `settled`), never inferred from the price.

A sold put filed as `options-put-delivery` is that duty's to report: its name goes in
EXCEPT, and this duty leaves it alone.

Settings: HEADS_UP_HOURS, EXCEPT.
"""

import bevo
import datetime
import json
import os
import re
import time

PARAMS = json.loads(os.environ.get("PARAMS", "{}"))

HEADS_UP_SECONDS = float(PARAMS.get("HEADS_UP_HOURS") or 24) * 3600
EXCEPT = {str(name).strip().upper() for name in PARAMS.get("EXCEPT") or []}

VENUE_NAMES = {"derive": "Derive", "paradex": "Paradex", "rysk": "Rysk"}
#: The venues a Butler wallet holds an account of its own on.
WALLET_VENUES = ("derive", "paradex")

#: Settlement is published shortly after expiry, not at the stroke of it. Below this the
#: duty waits quietly rather than reporting a missing price as a problem.
SETTLE_GRACE_SECONDS = 20 * 60
#: Past this with still no price, say so out loud, once.
SETTLE_ALARM_SECONDS = 6 * 3600
#: A position missing on this many reads in a row, before expiry, was closed.
GONE_READS = 2

NAME_FORMS = {
    "derive": (re.compile(r"^([A-Z0-9]+)-(\d{8})-([0-9_]+)-([PC])$"), "%Y%m%d"),
    "paradex": (re.compile(r"^([A-Z0-9]+)-USD-(\d{1,2}[A-Z]{3}\d{2})-([0-9_]+)-([PC])$"), "%d%b%y"),
    "rysk": (re.compile(r"^([A-Z0-9]+)-(\d{1,2}[A-Z]{3}\d{2})-(\d+(?:\.\d+)?)-([PC])$"), "%d%b%y"),
}


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


def parse_name(venue, name):
    """(underlying, expiry, strike, kind) from the venue's own name, or None.

    Only a fallback: the account's row states each of them. The name gives the day at
    08:00 UTC, when every Derive, Rysk and Paradex crypto option expires; a Paradex
    stock, index or commodity option expires later that day, which the row's own
    `expirySec` says.
    """
    form = NAME_FORMS.get(venue)
    found = form[0].match(name) if form else None
    if not found:
        return None
    underlying, day, strike, kind = found.groups()
    try:
        # Pinned to UTC: read in a DST zone this is an hour out.
        moment = datetime.datetime.strptime(day.title() + " 08:00", form[1] + " %H:%M")
    except ValueError:
        return None
    expiry = int(moment.replace(tzinfo=datetime.timezone.utc).timestamp())
    return underlying, expiry, float(strike.replace("_", ".")), kind


def record(venue, wallet, where, row):
    """What is remembered of one position, or None for a row that is not an option held."""
    name = str(row.get("instrument") or "").strip().upper()
    try:
        size = float(row.get("size") or 0)
    except (TypeError, ValueError):
        return None
    if not name or not size:
        return None
    named = parse_name(venue, name) or (None, 0, 0.0, None)
    try:
        expiry = int(float(row.get("expirySec") or named[1]))
        strike = float(row.get("strike") or named[2])
    except (TypeError, ValueError):
        return None
    kind = str(row.get("type") or named[3] or "").upper()[:1]
    underlying = str(row.get("underlying") or named[0] or "").upper()
    if expiry <= 0 or strike <= 0 or kind not in ("P", "C") or not underlying:
        say("%s on %s: the account's row does not say what it is; not watched" % (name, venue))
        return None
    cost = row.get("costUsd")
    return {"venue": venue, "wallet": wallet, "where": where, "instrument": name, "size": size,
            "usd": abs(float(cost)) if cost not in (None, "") else None,
            "strike": strike, "kind": kind, "expiry": expiry, "underlying": underlying}


def key_of(rec):
    return "|".join((rec["wallet"] or "main", rec["venue"], rec["instrument"],
                     "bought" if rec["size"] > 0 else "sold"))


def host(url):
    text = str(url or "").lower().split("://")[-1].split("/")[0]
    return text[4:] if text.startswith("www.") else text


def main_accounts():
    """({venue: account or None}, {site host: venue}, Rysk's paid-out rows), or None when
    the read failed. An account is None when that venue could not be read."""
    try:
        body = bevo.read("/options/account") or {}
    except bevo.BevoError as exc:
        say("could not read the options accounts: %s" % exc)
        return None
    venues = body.get("venues")
    if not isinstance(venues, list):
        # A server from before venues: the body is Derive's own.
        venues = [dict(body, venue="derive", available=True)]
    accounts, hosts, paid = {}, {}, []
    for entry in venues:
        if not isinstance(entry, dict) or not entry.get("venue"):
            continue
        venue = str(entry["venue"])
        if entry.get("site"):
            hosts[host(entry["site"])] = venue
        account = entry.get("account")
        accounts[venue] = account if entry.get("available") is not False and isinstance(account, dict) else None
        if venue == "rysk" and accounts[venue]:
            paid = [r for r in account.get("settled") or [] if isinstance(r, dict)]
    return accounts, hosts, paid


def wallet_accounts(hosts):
    """[(walletId, label, venue, account or None)] for every Butler wallet with an options
    account of its own. A list that cannot be read is no wallets this run."""
    try:
        rows = [r for r in bevo.platform_balances() or [] if isinstance(r, dict) and r.get("serverKept")]
        if not rows:
            return []
        wallets = (bevo.read("/wallets") or {}).get("wallets") or []
    except bevo.BevoError as exc:
        say("could not list the Butler wallets' accounts: %s" % exc)
        return []
    by_address = {str(w.get("address") or "").lower(): w for w in wallets if isinstance(w, dict)}
    out = []
    for row in rows:
        venue = hosts.get(host(row.get("siteHost") or row.get("siteUrl")))
        wallet = by_address.get(str(row.get("account") or "").lower())
        if venue not in WALLET_VENUES or not wallet or not wallet.get("walletId"):
            continue
        try:
            body = bevo.read("/options/account", {"walletId": wallet["walletId"], "venue": venue}) or {}
            account = body.get("account") if isinstance(body.get("account"), dict) else None
        except bevo.BevoError as exc:
            say("could not read %s's %s account: %s" % (wallet.get("label"), venue, exc))
            account = None
        out.append((str(wallet["walletId"]), str(wallet.get("label") or ""), venue, account))
    return out


def label(rec):
    day = datetime.datetime.fromtimestamp(rec["expiry"], datetime.timezone.utc)
    return "%s %s %s, %d %s" % (rec["underlying"], price(rec["strike"]),
                                "call" if rec["kind"] == "C" else "put", day.day, day.strftime("%b"))


def account_name(rec):
    venue = VENUE_NAMES.get(rec["venue"], rec["venue"])
    return "“%s” wallet's %s account" % (rec["where"], venue) if rec["wallet"] else "%s account" % venue


def intrinsic(rec, at):
    worth = at - rec["strike"] if rec["kind"] == "C" else rec["strike"] - at
    return max(0.0, worth) * abs(rec["size"])


def venue_query(rec):
    return {} if rec["venue"] == "derive" else {"venue": rec["venue"]}


def heads_up(rec, now):
    """Once, the day before: where the asset is and which way this is leaning. True once sent."""
    try:
        body = bevo.read("/options/ticker", {"instrument": rec["instrument"], **venue_query(rec)}) or {}
        spot = float(body.get("index") or 0)
    except (bevo.BevoError, TypeError, ValueError) as exc:
        say("could not read the price for %s's heads-up: %s" % (rec["instrument"], exc))
        return False
    if spot <= 0:
        say("no index for %s this run; its heads-up waits" % rec["instrument"])
        return False
    asset, strike, call = rec["underlying"], rec["strike"], rec["kind"] == "C"
    kind = "call" if call else "put"
    if rec["size"] > 0:
        worth = intrinsic(rec, spot)
        if worth > 0:
            leaning = "Your %s is in the money: if it ends here it pays about %s" % (kind, usd(worth))
            if rec["usd"] is not None:
                leaning += ", against the %s it cost" % usd(rec["usd"])
        else:
            leaning = "Your %s is out of the money: it pays nothing unless %s ends %s %s" % (
                kind, asset, "above" if call else "below", price(strike))
    elif not call:
        leaning = ("Your note looks set to pay out in full" if spot >= strike else
                   "Your note is under your price, so you may end up buying %s at %s" % (asset, price(strike)))
    else:
        leaning = ("Your note looks set to pay out in full, and you keep your %s" % asset if spot <= strike else
                   "Your note is above your price, so your %s may be sold at %s" % (asset, price(strike)))
    hours = round(max(0, rec["expiry"] - now) / 3600.0)
    bevo.notify("%s: %s is at %s. %s. It settles in about %d hours." % (
        label(rec), asset, price(spot), leaning, hours))
    return True


def after(rec, text, net):
    """`text` with what the premium leaves the owner up or down, when the account said it."""
    if rec["usd"] is None:
        return ""
    return text % (usd(rec["usd"]), "down" if net < 0 else "up", usd(abs(net)))


def cash_outcome(rec, settled):
    """What a Derive or Paradex option did at `settled`, in the owner's terms."""
    asset, strike, size, call = rec["underlying"], rec["strike"], abs(rec["size"]), rec["kind"] == "C"
    kind, where = "call" if call else "put", account_name(rec)
    head = "%s settled at %s, " % (asset, price(settled))
    if rec["size"] > 0:
        paid = intrinsic(rec, settled)
        if paid > 0:
            return (head + "%s your %s: your %s paid %s into your %s.%s" % (
                "above" if call else "under", price(strike), kind, usd(paid), where,
                after(rec, " After the %s it cost, you are %s %s.", paid - (rec["usd"] or 0))))
        lost = ", so the %s you paid is lost" % usd(rec["usd"]) if rec["usd"] is not None else ""
        return head + "%s your %s: the %s expired worthless%s." % (
            "at or under" if call else "at or above", price(strike), kind, lost)
    kept = " and the %s premium" % usd(rec["usd"]) if rec["usd"] is not None else ""
    if not call:
        if settled >= strike:
            return (head + "above your %s. You kept your %s%s. What is left of your collateral is free "
                    "cash in your %s." % (price(strike), usd(strike * size), kept, where))
        shortfall = (strike - settled) * size
        return (head + "under your %s. Your note was assigned: you agreed to buy %s %s at %s, which is "
                "%s more than they are worth today.%s %s settles in cash, so you are holding the loss "
                "in cash, not the %s. What is left of your collateral is free cash in your %s." % (
                    price(strike), fmt(size), asset, price(strike), usd(shortfall),
                    after(rec, " After the %s premium you are %s %s.", (rec["usd"] or 0) - shortfall),
                    VENUE_NAMES.get(rec["venue"], rec["venue"]), asset, where))
    if settled <= strike:
        return (head + "under your %s. You kept your %s%s. Your %s collateral is free again in your %s." % (
            price(strike), asset, kept, asset, where))
    return (head + "above your %s. Your %s %s was sold at %s. You gave up %s of further upside%s. What "
            "is left of your %s collateral is free again in your %s." % (
                price(strike), fmt(size), asset, price(strike), usd((settled - strike) * size),
                (", and kept the %s premium" % usd(rec["usd"])) if rec["usd"] is not None else "",
                asset, where))


def option_key(name):
    """A Rysk name as (underlying, expiry, strike, type), so 95 and 95.0 are one strike."""
    found = NAME_FORMS["rysk"][0].match(str(name or "").upper())
    return (found.group(1), found.group(2), float(found.group(3)), found.group(4)) if found else None


def rysk_outcome(rec, row, settled):
    """What Rysk paid out, in the owner's terms. `settled` may still be None."""
    asset, strike, size = rec["underlying"], rec["strike"], abs(rec["size"])
    back = " + ".join("%s %s" % (fmt(leg["amount"]), leg["symbol"]) for leg in row.get("received") or [])
    at = ""
    if settled:
        at = " at %s, %s your %s" % (price(settled), "under" if settled < strike else "at or above",
                                     price(strike))
    if row.get("assigned"):
        text = ("%s settled%s. Your put was assigned: Rysk delivered %s to your HyperEVM wallet, "
                "bought at %s each." % (asset, at, back, price(strike)))
        if settled:
            shortfall = max(0.0, strike - settled) * size
            net = after(rec, "; after the %s premium you are %s %s", (rec["usd"] or 0) - shortfall)
            text += " That is %s more than they were worth at settlement%s." % (usd(shortfall), net)
        return text + " The %s is yours to keep; selling it is a separate trade." % asset
    ended = "was not exercised" if settled and settled < strike else "expired worthless"
    kept = ", and you keep the %s premium" % usd(rec["usd"]) if rec["usd"] is not None else ""
    return "%s settled%s. Your put %s: Rysk returned %s to your HyperEVM wallet%s." % (
        asset, at, ended, back or "your collateral", kept)


def settle(rec, now, rysk_paid):
    """Say what an expired option did. True once said; False while the venue has not."""
    try:
        query = ({"underlying": rec["underlying"], "expiry": rec["expiry"]} if rec["venue"] == "derive"
                 else {"instrument": rec["instrument"], "venue": rec["venue"]})
        settled = float((bevo.read("/options/settlement", query) or {}).get("price") or 0) or None
    except (bevo.BevoError, TypeError, ValueError) as exc:
        say("could not read %s's settlement: %s" % (rec["instrument"], exc))
        settled = None
    text = None
    if rec["venue"] == "rysk":
        rows = [r for r in rysk_paid or [] if option_key(r.get("instrument")) == option_key(rec["instrument"])]
        # One owner can sell the same put twice; this is the one of this size.
        sized = [r for r in rows if abs(abs(float(r.get("size") or 0)) - abs(rec["size"])) < 1e-9]
        row = (sized or rows or [None])[0]
        if row is not None:
            text = rysk_outcome(rec, row, settled)
    elif settled:
        text = cash_outcome(rec, settled)
    if text:
        bevo.notify("%s: %s" % (label(rec), text))
        return True
    late = now - rec["expiry"]
    if late > SETTLE_ALARM_SECONDS and not rec.get("alarm"):
        rec["alarm"] = True
        bevo.notify("%s: it expired %d hours ago and %s has not %s yet, so I will not guess. "
                    "Nothing is lost and I am still watching." % (
                        label(rec), round(late / 3600), VENUE_NAMES.get(rec["venue"], rec["venue"]),
                        "paid it out" if rec["venue"] == "rysk" else "published a settlement price"))
    return False


def fire():
    now = time.time()
    main = main_accounts()
    if main is None:
        bevo.status("unreadable")
        return
    accounts, hosts, rysk_paid = main
    scopes = {("", venue): account for venue, account in accounts.items()}
    labels = {}
    for wallet, where, venue, account in wallet_accounts(hosts):
        scopes[(wallet, venue)] = account
        labels[wallet] = where

    held = dict(bevo.state.get("held") or {})
    here = set()
    for (wallet, venue), account in scopes.items():
        if account is None:
            continue
        for row in account.get("positions") or []:
            rec = record(venue, wallet, labels.get(wallet, ""), row) if isinstance(row, dict) else None
            if rec is None or rec["instrument"] in EXCEPT:
                continue
            key = key_of(rec)
            here.add(key)
            old = held.get(key) or {}
            if rec["usd"] is None:
                rec["usd"] = old.get("usd")
            held[key] = dict(rec, told=bool(old.get("told")), alarm=bool(old.get("alarm")), gone=0)

    waiting = 0
    for key in sorted(held):
        rec = held[key]
        left = rec["expiry"] - now
        if rec["instrument"] in EXCEPT:
            del held[key]
        elif left > 0:
            if key not in here and scopes.get((rec["wallet"], rec["venue"])) is not None:
                rec["gone"] = int(rec.get("gone") or 0) + 1
                if rec["gone"] >= GONE_READS:
                    say("%s is no longer held; it was closed before expiry" % rec["instrument"])
                    del held[key]
            elif left <= HEADS_UP_SECONDS and not rec.get("told"):
                rec["told"] = heads_up(rec, now)
        elif -left >= SETTLE_GRACE_SECONDS and settle(rec, now, rysk_paid):
            del held[key]
        else:
            waiting += 1
    bevo.state["held"] = held

    open_ = [rec for rec in held.values() if rec["expiry"] > now]
    if waiting:
        bevo.status("settling", count=waiting)
    elif open_:
        first = datetime.datetime.fromtimestamp(min(r["expiry"] for r in open_), datetime.timezone.utc)
        bevo.status("watching", count=len(open_), when="%d %s" % (first.day, first.strftime("%b")))
    else:
        bevo.status("none")


for tick in bevo.ticks():
    try:
        fire()
    except Exception as exc:  # noqa: BLE001 - one bad run must not end the watch
        say("run skipped: %s" % exc)
