"""Keep every options venue's account on the wallet's Platforms tab.

One read of the options rail answers for every venue bevo-server trades
(`venues`), and each account that exists gets one Platforms row, keyed by the
venue's site and the owner's wallet. The row's name, site and worth all come
from that read: the worth is the venue's own (`worthUsd`), so no venue's
accounting lives here, and a venue the server adds appears on the next check
with nothing refiled.

A venue that fails to read, or reads with no worth, writes nothing, so its row
keeps its last good value; the other venues are written regardless. Zero is
written only for an account that read fine and holds nothing.

The one note it sends is a deposit landing, and only on a venue whose deposits
are credited after their card has closed (`depositsLandLater`: Derive's
bridge). bevo-server's own note covers every deposit card, open, buy, close and
withdrawal, and the options-lifecycle duty reports expiries and settlements.
"""

import bevo
import random
import time

#: A smaller rise in USDC is noise, not a deposit.
DEPOSIT_MIN_USD = 1.0

#: A settlement or a close pays USDC in. A rise this soon after a position
#: changed is that cash, not a deposit.
QUIET_AFTER_POSITION_CHANGE = 3600


def say(text):
    """`bevo.log()` on one line: an echoed error must not forge a log line."""
    bevo.log(" ".join(str(text).split()))


def usd(number):
    return format(round(float(number), 2), ",.2f")


def holdings(account):
    """Open positions as sorted [instrument, size] pairs: what "unchanged" compares."""
    rows = []
    for row in account.get("positions") or []:
        size = float(row.get("size") or 0)
        if size:
            rows.append([str(row.get("instrument")), size])
    return sorted(rows)


def listed(account):
    """The row's positions, bought and sold, in the owner's words, at most 20."""
    rows = []
    for row in account.get("positions") or []:
        size = float(row.get("size") or 0)
        if not size or row.get("valueUsd") is None:
            continue
        kind = "call" if row.get("type") == "C" else "put"
        title = "%s %s %s %s %s" % ("Bought" if size > 0 else "Sold", format(abs(size), "g"),
                                    row.get("underlying") or "", format(float(row.get("strike") or 0), ",g"), kind)
        value = float(row["valueUsd"])
        details = [{"label": "Expires", "value": str(row.get("expiresIn") or "")}]
        if row.get("pnlUsd") is not None:
            details.append({"label": "Up/down", "value": "$%s" % format(round(float(row["pnlUsd"]), 2), ",.2f")})
        rows.append({"title": " ".join(title.split()), "subtitle": str(row.get("instrument") or ""),
                     "valueUsd": round(value if size > 0 else -value, 2), "details": details})
    return rows[:20]


def landed(venue, usdc, held):
    """The USDC a deposit just added to `venue`, or 0. Moves the baseline on either way.

    Each venue's baseline is its own flat keys in `bevo.state`, which saves on
    assignment and never sees a nested dict change. The first check has
    nothing to compare with, so it never reports a deposit.
    """
    now = time.time()
    usdc_key, held_key, changed_key = "usdc:" + venue, "positions:" + venue, "changed:" + venue
    seen = usdc_key in bevo.state
    before_usdc = float(bevo.state.get(usdc_key) or 0)
    before_held = bevo.state.get(held_key)
    if seen and held != before_held:
        bevo.state[changed_key] = now
    quiet = now - float(bevo.state.get(changed_key) or 0) >= QUIET_AFTER_POSITION_CHANGE
    bevo.state[usdc_key] = usdc
    bevo.state[held_key] = held
    if seen and held == before_held and quiet and usdc - before_usdc >= DEPOSIT_MIN_USD:
        return usdc - before_usdc
    return 0.0


def write(entry, wallet):
    """One venue's row. Answers (outcome, worth, open positions, USDC credited)."""
    name, site, venue = entry.get("name"), entry.get("site"), str(entry.get("venue") or "")
    if entry.get("available") is False:
        if entry.get("error"):
            say("could not read the %s account: %s" % (name or venue, entry["error"]))
            return "unreadable", 0, 0, 0
        return "off", 0, 0, 0  # a venue this server does not trade right now
    if not site or not name or not venue:
        say("a venue in the account read named no site; its row keeps its last value")
        return "unreadable", 0, 0, 0
    account = entry.get("account")
    if not isinstance(account, dict):
        return "signer_off", 0, 0, 0
    late = entry.get("depositsLandLater") is True
    if not account.get("exists"):
        # Before the first deposit the account holds nothing, so that deposit
        # is a rise from zero. A baseline already seen is kept: one odd read
        # must not turn the next good one into a deposit.
        if late and "usdc:" + venue not in bevo.state:
            bevo.state["usdc:" + venue] = 0.0
            bevo.state["positions:" + venue] = []
        return "no_account", 0, 0, 0

    worth = account.get("worthUsd")
    if worth is None or float(worth) < 0:
        say("the %s account has no worth this run; the row keeps its last value" % name)
        return "unpriced", 0, 0, 0
    value = round(float(worth), 2)
    positions = listed(account)
    bevo.platform_balance(site, name, value, account=entry.get("wallet") or wallet,
                          positions=positions)
    credit = landed(venue, float(account.get("usdc") or 0), holdings(account)) if late else 0.0
    if credit:
        bevo.notify("Your %s deposit landed: $%s USDC credited. The account is worth $%s now."
                    % (name, usd(credit), usd(value)), push="%s deposit credited" % name)
    return "ok", value, len(positions), credit


def check():
    try:
        body = bevo.read("/options/account") or {}
    except bevo.BevoError as exc:
        say("could not read the options accounts: %s" % exc)
        bevo.status("unreadable")
        return
    venues = body.get("venues")
    if not isinstance(venues, list):
        say("the account read listed no venues; every row keeps its last value")
        bevo.status("unreadable")
        return

    outcomes, value, positions, credit = [], 0.0, 0, 0.0
    for entry in venues:
        if not isinstance(entry, dict):
            continue
        outcome, worth, held, credited = write(entry, body.get("wallet") or "")
        outcomes.append(outcome)
        value += worth
        positions += held
        credit += credited

    written = outcomes.count("ok")
    missed = outcomes.count("unreadable") + outcomes.count("unpriced")
    if written and missed:
        bevo.status("partial", value=round(value, 2), skipped=missed)
    elif written and credit:
        bevo.status("credited", credit=round(credit, 2), value=round(value, 2), positions=positions)
    elif written:
        bevo.status("ok", value=round(value, 2), positions=positions)
    elif "unreadable" in outcomes:
        bevo.status("unreadable")
    elif "unpriced" in outcomes:
        bevo.status("unpriced")
    elif "no_account" in outcomes:
        bevo.status("no_account")
    elif "signer_off" in outcomes:
        say("Butler's signer is off, so no options account can be read")
        bevo.status("signer_off")
    else:
        bevo.status("no_account")


def run_check():
    try:
        check()
    except Exception as exc:
        # Never bevo.fail(): a venue out of reach is not this duty failing, and
        # every row keeps its last good value meanwhile.
        say("check skipped: %s" % exc)


run_check()

for tick in bevo.ticks():
    # Spreads every owner's read across the minute instead of the timer's edge.
    time.sleep(random.uniform(0, 60))
    run_check()
