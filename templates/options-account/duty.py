"""Keep one options venue's account on the wallet's Platforms tab.

Every check reads the account through the options rail for VENUE and writes
what it is worth to one Platforms row, keyed by the venue's site and the
owner's wallet. The row's name and site come from the read itself, so a new
venue needs only a new VENUE value, never a new template. Derive keeps its own
`derive-account` duty, whose row this would duplicate.

A read that fails writes nothing, so the row keeps its last good value. Zero is
written only for an account that read fine and holds nothing.

It sends no notes: bevo-server's own note covers every deposit, open, buy and
close, and the options-lifecycle duty reports expiries and settlements.
"""

import bevo
import json
import os
import random
import time

PARAMS = json.loads(os.environ.get("PARAMS", "{}"))

VENUE = str(PARAMS.get("VENUE") or "").strip().lower()


def say(text):
    """`bevo.log()` on one line: an echoed error must not forge a log line."""
    bevo.log(" ".join(str(text).split()))


def index_of(underlying, positions):
    """The venue's index for `underlying`, read off an option on it, or None."""
    for row in positions:
        instrument = str(row.get("instrument") or "")
        if not instrument.startswith(underlying + "-"):
            continue
        try:
            body = bevo.read("/options/ticker", {"venue": VENUE, "instrument": instrument}) or {}
        except bevo.BevoError as exc:
            say("could not read the %s index: %s" % (underlying, exc))
            return None
        value = body.get("index")
        if value in (None, ""):
            return None
        index = float(value)
        return index if index > 0 else None
    return None


def worth(account):
    """USDC, plus bought positions, less sold ones, plus collateral assets at index.

    None when any part has no price: an unknown is never counted as zero.
    """
    total = float(account.get("usdc") or 0)
    positions = account.get("positions") or []
    for row in positions:
        size = float(row.get("size") or 0)
        if not size:
            continue
        value = row.get("valueUsd")
        if value is None:
            return None
        total += float(value) if size > 0 else -float(value)
    for underlying, asset in (account.get("assets") or {}).items():
        held = float((asset or {}).get("held") or 0)
        if held <= 0:
            continue
        index = index_of(underlying, positions)
        if index is None:
            return None
        total += held * index
    return total if total >= 0 else None


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


def check():
    try:
        body = bevo.read("/options/account", {"venue": VENUE}) or {}
    except bevo.BevoError as exc:
        say("could not read the %s account: %s" % (VENUE, exc))
        bevo.status("unreadable")
        return
    site, name = body.get("site"), body.get("name")
    if not site or not name:
        say("the %s account read named no site; the row keeps its last value" % VENUE)
        bevo.status("unreadable")
        return
    account = body.get("account")
    if not isinstance(account, dict):
        say("Butler's signer is off, so the %s account cannot be read" % name)
        bevo.status("signer_off")
        return
    if not account.get("exists"):
        bevo.status("no_account")
        return

    value = worth(account)
    if value is None:
        say("part of the %s account has no price this run; the row keeps its last value" % name)
        bevo.status("unpriced")
        return

    positions = listed(account)
    bevo.platform_balance(site, name, round(value, 2), account=body.get("wallet") or "",
                          positions=positions)
    bevo.status("ok", value=round(value, 2), positions=len(positions))


def run_check():
    try:
        check()
    except Exception as exc:
        # Never bevo.fail(): a venue out of reach is not this duty failing, and
        # the row keeps its last good value meanwhile.
        say("check skipped: %s" % exc)


if not VENUE:
    say("no VENUE is set, so there is no account to read")
    bevo.status("unreadable")
else:
    run_check()

for tick in bevo.ticks():
    if not VENUE:
        continue
    # Spreads every owner's read across the minute instead of the timer's edge.
    time.sleep(random.uniform(0, 60))
    run_check()
