"""Keep the owner's Derive options account on the wallet's Platforms tab.

Every check reads the account through the options rail and writes what it is
worth to one Platforms row, keyed by the owner's wallet, so the wallet page
shows Derive beside every other outside platform. The figures are Derive's own:
`bevo.read("/options/account")` for cash and each position at mark, and
`bevo.read("/options/ticker")` for the index of an asset held as collateral.

A read that fails writes nothing, so the row keeps its last good value. Zero is
written only for an account that read fine and holds nothing.

The one note it sends is a deposit landing. bevo-server already sends one for
each open, buy, close and withdrawal, and the options-lifecycle duty reports
expiries and settlements, so the rest would be a second copy.
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


def index_of(underlying, positions):
    """Derive's index for `underlying`, or None for no price this run.

    The ticker is per option, so it is read off an option on that asset. The
    account lists an asset only while a sold call holds it as collateral, so
    there is always one.
    """
    for row in positions:
        instrument = str(row.get("instrument") or "")
        if not instrument.startswith(underlying + "-"):
            continue
        try:
            body = bevo.read("/options/ticker", {"instrument": instrument}) or {}
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


def landed(usdc, held):
    """The USDC a deposit just added, or 0. Moves the baseline on either way.

    The first check has nothing to compare with, so it never reports a deposit.
    """
    now = time.time()
    seen = "usdc" in bevo.state
    before_usdc = float(bevo.state.get("usdc") or 0)
    before_held = bevo.state.get("positions")
    if seen and held != before_held:
        bevo.state["positions_changed_at"] = now
    quiet = now - float(bevo.state.get("positions_changed_at") or 0) >= QUIET_AFTER_POSITION_CHANGE
    rise = usdc - before_usdc
    bevo.state.update(usdc=usdc, positions=held)
    if seen and held == before_held and quiet and rise >= DEPOSIT_MIN_USD:
        return rise
    return 0.0


def check():
    try:
        body = bevo.read("/options/account") or {}
    except bevo.BevoError as exc:
        say("could not read the Derive account: %s" % exc)
        bevo.status("unreadable")
        return
    account = body.get("account")
    if not isinstance(account, dict):
        say("Butler's signer is off, so the Derive account cannot be read")
        bevo.status("signer_off")
        return
    if not account.get("exists"):
        # Before the first deposit the account holds nothing, so that deposit
        # is a rise from zero. A baseline already seen is kept: one odd read
        # must not turn the next good one into a deposit.
        if "usdc" not in bevo.state:
            bevo.state.update(usdc=0.0, positions=[])
        bevo.status("no_account")
        return

    value = worth(account)
    if value is None:
        say("part of the Derive account has no price this run; the row keeps its last value")
        bevo.status("unpriced")
        return

    bevo.platform_balance("https://www.derive.xyz", "Derive", round(value, 2),
                          account=body.get("wallet") or "")
    held = holdings(account)
    credit = landed(float(account.get("usdc") or 0), held)
    if credit:
        bevo.notify("Your Derive deposit landed: $%s USDC credited. The account is worth $%s now."
                    % (usd(credit), usd(value)), push="Derive deposit credited")
        bevo.status("credited", credit=round(credit, 2), value=round(value, 2), positions=len(held))
    else:
        bevo.status("ok", value=round(value, 2), positions=len(held))


def run_check():
    try:
        check()
    except Exception as exc:
        # Never bevo.fail(): Derive out of reach is not this duty failing, and
        # the row keeps its last good value meanwhile.
        say("check skipped: %s" % exc)


run_check()

for tick in bevo.ticks():
    # Spreads every owner's read across the minute instead of the timer's edge.
    time.sleep(random.uniform(0, 60))
    run_check()
