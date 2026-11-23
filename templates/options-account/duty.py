"""Keep every options venue's account on the wallet's Platforms tab.

One read of the options rail answers for every venue bevo-server trades
(`venues`), and each account that exists gets one Platforms row, keyed by the
venue's site and the owner's wallet. The row's name, site and worth all come
from that read: the worth is the venue's own (`worthUsd`), so no venue's
accounting lives here, and a venue the server adds appears on the next check
with nothing refiled. A venue that holds its USDC itself (`cashLine`: Paradex)
lists that cash first on its row, so the row's lines add up to its worth; a
venue whose USDC is the owner's own wallet (Rysk) does not, since the wallet's
Tokens tab already counts it.

A venue whose account is split into subaccounts (`accounts`: Derive's risk
universes) gets one row per subaccount instead, keyed by its name ("PRIME",
"RWA"), at the subaccount's own worth, listing its cash first and then its
positions. Once every one of them is written, the venue's other rows (the
single row it had before, a subaccount it no longer has) are removed, so the
wallet never counts an account twice. A row Butler's server keeps (`serverKept`:
a Butler wallet's own account, which the server writes) is never removed.

A venue that fails to read, or reads with no worth, writes nothing, so its row
keeps its last good value; the other venues are written regardless. Zero is
written only for an account that read fine and holds nothing.

It sends two notes. One is a deposit landing, and only on a venue whose deposits
are credited after their card has closed (`depositsLandLater`: Derive's
bridge). bevo-server's own note covers every deposit card, open, buy, close and
withdrawal, and the options-lifecycle duty reports expiries and settlements.

The other is the order guard. A resting order sits at the price its owner chose
and nothing moves it, so once the venue's own mark has passed that price the
order hands the difference to whoever takes it: a sale under the mark, a buy
over it. Each order still resting is compared with its option's mark, and one
past it by GIFT_SHARE and GIFT_MIN_USD is said once, with what it gives away.
The owner decides: this duty cancels and re-prices nothing.
"""

import bevo
import random
import subprocess
import time

#: A smaller rise in USDC is noise, not a deposit.
DEPOSIT_MIN_USD = 1.0

#: A settlement or a close pays USDC in. A rise this soon after a position
#: changed is that cash, not a deposit.
QUIET_AFTER_POSITION_CHANGE = 3600
# A resting order's line on its row (the server's `RESTING_STATUS`): how the lines are found again.
RESTING = "Resting"

#: The order guard speaks when the mark is this share past the order's price, and the
#: order would give away at least this much. Under either, it is the mark's own noise.
GIFT_SHARE = 0.02
GIFT_MIN_USD = 1.0
#: A mark older than this says nothing about now.
MARK_MAX_AGE = 120
#: The most orders priced in one check, so an owner with many costs a bounded number of reads.
GUARD_MAX_ORDERS = 10


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
        if not size:
            continue
        kind = "call" if row.get("type") == "C" else "put"
        strike = float(row.get("strike") or 0)
        title = "%s %s %s %s %s" % ("Bought" if size > 0 else "Sold", format(abs(size), "g"),
                                    row.get("underlying") or "", format(strike, ",g"), kind)
        line = {"title": " ".join(title.split()), "subtitle": str(row.get("instrument") or "")}
        if row.get("valueUsd") is not None:
            value = float(row["valueUsd"])
            details = [{"label": "Expires", "value": str(row.get("expiresIn") or "")}]
            if row.get("pnlUsd") is not None:
                details.append({"label": "Up/down", "value": "$%s" % usd(row["pnlUsd"])})
            line.update(valueUsd=round(value if size > 0 else -value, 2), details=details)
        else:
            line["details"] = unmarked(row, size, strike, kind)
            if row.get("expiresIn") == "expired":
                line["status"] = "Awaiting settlement"
        rows.append(line)
    return rows[:20]


def unmarked(row, size, strike, kind):
    """Details for a position its venue puts no mark on, listed without a value.

    The account's worth already counts it, at what it would settle to; the premium
    shown as its value would read as owed when it was paid to the owner.
    """
    details = []
    if row.get("expiresIn") and row["expiresIn"] != "expired":
        details.append({"label": "Expires", "value": str(row["expiresIn"])})
    if row.get("costUsd") is not None:
        details.append({"label": "Received" if size < 0 else "Paid", "value": "$%s" % usd(row["costUsd"])})
    if size < 0 and kind == "put" and strike:
        details.append({"label": "Collateral", "value": "$%s" % usd(strike * abs(size))})
    return details


def resting(account, shown):
    """The account's resting orders as its row's last lines, each the server's own line for it.

    The account read hands every open order the line its Platforms row shows
    (`platformLine`), so this duty and Butler's server write the same row. A read that
    could not see orders (`ordersUnread`: Derive's public read) keeps the lines the row
    already shows rather than wiping an order it cannot see; an order that ended drops
    off on the next read that can see it.
    """
    if account.get("ordersUnread"):
        return list(shown or [])
    return [o["platformLine"] for o in account.get("openOrders") or []
            if isinstance(o, dict) and isinstance(o.get("platformLine"), dict)]


def open_orders(account):
    """Every order still resting in the account, each subaccount's included."""
    holders = [account] + [sub for sub in account.get("accounts") or [] if isinstance(sub, dict)]
    orders = {}
    for holder in holders:
        for order in holder.get("openOrders") or []:
            if isinstance(order, dict) and order.get("orderId") and order.get("status", "open") == "open":
                orders[str(order["orderId"])] = order
    return orders


def gift(order, venue):
    """What the order gives away at the venue's mark now, as (mark, dollars), or None when
    it gives nothing worth saying or the mark cannot be read."""
    try:
        left = float(order.get("size") or 0) - float(order.get("filledSize") or 0)
        limit = float(order.get("limitPricePerUnitUsd") or 0)
        if left <= 0 or limit <= 0 or order.get("side") not in ("buy", "sell"):
            return None
        body = bevo.read("/options/ticker", {"instrument": order["instrument"], "venue": venue}) or {}
        mark = float(body.get("mark") or 0)
        age = time.time() - float(body.get("asOf") or 0) / 1000.0
    except (bevo.BevoError, KeyError, TypeError, ValueError) as exc:
        say("could not price the resting order on %s: %s" % (order.get("instrument"), exc))
        return None
    if mark <= 0 or age > MARK_MAX_AGE:
        return None
    past = mark - limit if order["side"] == "sell" else limit - mark
    if past <= GIFT_SHARE * mark or past * left < GIFT_MIN_USD:
        return None
    return mark, past * left


def guard(entry, account):
    """Say once, for each resting order, that the market has passed its price."""
    if account.get("ordersUnread"):
        return  # this read saw no orders: nothing is known, and nothing is forgotten
    venue, name = str(entry.get("venue") or ""), entry.get("name")
    orders = open_orders(account)
    prefix = "gift:%s:" % venue
    for key in [k for k in list(bevo.state) if str(k).startswith(prefix)]:
        if key[len(prefix):] not in orders:
            bevo.state.pop(key)
    for order_id, order in list(orders.items())[:GUARD_MAX_ORDERS]:
        key = prefix + order_id
        if bevo.state.get(key):
            continue
        found = gift(order, venue)
        if found is None:
            continue
        mark, given = found
        selling = order["side"] == "sell"
        left = float(order["size"]) - float(order.get("filledSize") or 0)
        bevo.notify(
            "Your resting %s order on %s, %s %s at $%s each, is now %s %s's own price for it, $%s: "
            "filled there it gives away about $%s. It is still on the book. Tell me to cancel it "
            "or to set a new price."
            % (name, order["instrument"], "to sell" if selling else "to buy", "%g" % left,
               usd(order["limitPricePerUnitUsd"]), "under" if selling else "over", name, usd(mark),
               usd(given)),
            push="A resting %s order is priced %s the market" % (name, "under" if selling else "over"))
        bevo.state[key] = True


def shown_resting(site):
    """The resting lines each of the site's rows shows now, by account. Read only when needed."""
    host = site_host(site)
    try:
        rows = bevo.platform_balances()
    except bevo.BevoError as exc:
        say("could not list the Platforms rows, so their resting orders are not kept: %s" % exc)
        return {}
    return {row.get("account"): [p for p in row.get("positions") or []
                                 if isinstance(p, dict) and p.get("status") == RESTING]
            for row in rows if row.get("siteHost") == host}


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


def site_host(url):
    """The host a Platforms row is keyed by, as the server derives it: lowercased, no "www."."""
    host = str(url).split("://", 1)[-1].split("/", 1)[0].split("@")[-1].split(":")[0].lower()
    return host[4:] if host.startswith("www.") else host


def cash_line(usdc, orders=()):
    """An account's spendable USDC as its row's first line.

    What its resting orders hold back is on those orders' lines (their `valueUsd`), so Cash
    is what can be spent and the lines still add up to the account's worth.
    """
    held = sum(float(o.get("valueUsd") or 0) for o in orders)
    return {"title": "Cash", "valueUsd": round(max(0.0, float(usdc or 0) - held), 2)}


def subaccount_rows(subs, unread=False, shown=None):
    """(account, worth, positions, open count) per subaccount, or None when one has no worth.

    A subaccount's cash is part of its worth, so it is listed as the row's first line; its
    resting orders come last.
    """
    rows = []
    for sub in subs:
        worth = sub.get("worthUsd")
        if worth is None or float(worth) < 0:
            return None
        named = " ".join(str(sub.get("universe") or "").split())
        account = named or "Subaccount %s" % sub.get("subaccountId")
        held = listed(sub)
        orders = resting(dict(sub, ordersUnread=unread), (shown or {}).get(account))
        rows.append((account, round(float(worth), 2),
                     ([cash_line(sub.get("usdc"), orders)] + held + orders)[:20], len(held)))
    return rows


def retire(site, keep):
    """Remove the site's rows whose account is not in `keep`, never one the server keeps."""
    host = site_host(site)
    try:
        rows = bevo.platform_balances()
    except bevo.BevoError as exc:
        say("could not list the Platforms rows, so none was retired: %s" % exc)
        return
    for row in rows:
        if row.get("siteHost") != host or row.get("account") in keep or not row.get("id"):
            continue
        if row.get("serverKept"):
            continue
        try:
            done = subprocess.run(["bevo-platforms", "remove", str(row["id"])],
                                  capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            done = None
            say("could not retire the %s row: %s" % (row.get("account") or host, exc))
        if done is not None and done.returncode != 0:
            say("could not retire the %s row: %s" % (row.get("account") or host, done.stderr[:200]))


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
    unread = bool(account.get("ordersUnread"))
    shown = shown_resting(site) if unread else None
    subs = [sub for sub in account.get("accounts") or [] if isinstance(sub, dict)]
    if subs:
        rows = subaccount_rows(subs, unread, shown)
        if rows is None:
            say("a %s subaccount has no worth this run; its rows keep their last value" % name)
            return "unpriced", 0, 0, 0
        saved = [bevo.platform_balance(site, name, sub_worth, account=named, positions=positions)
                 for named, sub_worth, positions, _ in rows]
        # Only once every subaccount row is in place, or the venue could vanish for a check.
        if all(saved):
            retire(site, {named for named, _, _, _ in rows})
        held = sum(count for _, _, _, count in rows)
    else:
        positions = listed(account)
        held = len(positions)
        row_account = entry.get("wallet") or wallet
        orders = resting(account, (shown or {}).get(row_account))
        cash = [cash_line(account.get("usdc"), orders)] if entry.get("cashLine") is True else []
        bevo.platform_balance(site, name, value, account=row_account,
                              positions=(cash + positions + orders)[:20])
    try:
        guard(entry, account)
    except Exception as exc:
        # The rows are written; a guard that could not run says so and waits for the next check.
        say("the order guard skipped %s this run: %s" % (name, exc))
    credit = landed(venue, float(account.get("usdc") or 0), holdings(account)) if late else 0.0
    if credit:
        bevo.notify("Your %s deposit landed: $%s USDC credited. The account is worth $%s now."
                    % (name, usd(credit), usd(value)), push="%s deposit credited" % name)
    return "ok", value, held, credit


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
