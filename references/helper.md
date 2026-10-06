# The Derive helper

Write this to a file and run it with `python3`. Stdlib only, no API key, no secret.
It prints one JSON object on stdout and a one-line reason on stderr when it fails.

```sh
python3 /tmp/derive_helper.py screen --tenor monthly --collateral 5000
python3 /tmp/derive_helper.py quote --product cash_secured_put --underlying ETH \
    --collateral 5000 --tenor monthly --otm-pct 10
python3 /tmp/derive_helper.py chain --underlying ETH --tenor monthly
```

Exit codes: `0` the read succeeded, `1` it did not.

Every quote comes back with `tradeable` and, when that is false, a `reasons` list in
plain English. **Never offer a note whose quote is not `tradeable`**, and never
rewrite a reason into something softer - they are already written for an owner.

The money paths (`open`, `close`, `positions`, `withdraw`) refuse with an explanation
until spikes A1 and A4 pass. That refusal is deliberate: there is no session key to
sign with, and a helper that pretended otherwise would be worse than one that stops.

```python
"""Quote and price yield notes on Derive, from its public API.

A yield note is one option sold short, fully collateralised:

  cash_secured_put   sell a put, hold strike x size in USDC
  covered_call       sell a call, hold size of the underlying

Everything here that reads the venue works with no credentials. The parts
that move money (`open`, `close`, `withdraw`) need a registered session key
and are not reachable until spikes A1 and A4 pass; they refuse rather than
pretend.

The point of this file is that the model never picks an instrument, a strike
or a premium. It passes an intent - product, underlying, collateral, tenor,
strike rule - and gets back a quote object with every number already fixed.

Usage:
    derive_helper.py screen [--tenor monthly]
    derive_helper.py chain --underlying ETH [--tenor monthly] [--type P]
    derive_helper.py quote --product cash_secured_put --underlying ETH \
        --collateral 5000 [--tenor monthly] [--otm-pct 10 | --delta 0.20]
"""

import argparse
import datetime
import json
import math
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.lyra.finance"
UA = "butler-yield-notes/0.1"

# Derive's taker fee: $0.50 a trade, plus 0.03% of the underlying notional,
# with the percentage part capped at 12.5% of the option's value.
BASE_FEE_USD = 0.50
TAKER_RATE = 0.0003
FEE_CAP_RATE = 0.125

# --- the gates -------------------------------------------------------------
# Measured against the live book on 6 Oct 2026; see references/venue.md for
# where each number comes from. These are what keep a note off an asset whose
# option is quoted but not sellable.

#: Most the bid may sit below Derive's own mark, in vol points. At 5 points a
#: seller crossing the spread gives up roughly a quarter of fair value, which
#: is the worst we will show an owner. ETH sits near 4, BTC near 3.5, and
#: every other listed asset is 10 to 60 and fails this outright.
MAX_VOL_GAP_PTS = 5.0

#: Fees may not eat more than this share of the gross premium. The $0.50 base
#: fee alone is 80%+ of a minimum-size weekly, so this is what rules out small
#: tickets and most weeklies.
MAX_FEE_DRAG = 0.15

#: Below this there is no point quoting: the premium rounds to nothing.
MIN_PREMIUM_USD = 1.00

CURRENCIES = ["ETH", "BTC", "SOL", "XRP", "ADA", "HYPE",
              "ZEC", "XAUT", "LIT", "VVV", "PUMP", "CC"]

TENOR_DAYS = {"weekly": 9, "monthly": 24, "quarterly": 80}


# --- transport -------------------------------------------------------------

def post(path, body, tries=3):
    """One JSON-RPC-ish POST to Derive's public API.

    The User-Agent matters: Derive's edge 403s the default urllib one.
    """
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                BASE + path,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "User-Agent": UA},
            )
            out = json.load(urllib.request.urlopen(req, timeout=40))
            if "error" in out:
                raise RuntimeError(out["error"].get("data") or out["error"].get("message"))
            return out["result"]
        except Exception as exc:  # noqa: BLE001 - retried, then surfaced
            last = exc
            if attempt < tries - 1:
                time.sleep(1.2 * (attempt + 1))
    raise RuntimeError("derive %s failed: %s" % (path, last))


def num(x):
    """Derive sends numbers as strings, and nulls for an empty side."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


# --- venue reads -----------------------------------------------------------

def instruments(currency, option_type=None):
    """Every active option on one currency, paged out in full."""
    out, page = [], 1
    while True:
        r = post("/public/get_all_instruments", {
            "expired": False, "instrument_type": "option",
            "currency": currency, "page": page, "page_size": 500,
        })
        out += r["instruments"]
        if page >= r["pagination"]["num_pages"]:
            break
        page += 1
    act = [i for i in out if i["is_active"]]
    if option_type:
        act = [i for i in act if i["option_details"]["option_type"] == option_type]
    return act


def ticker(name):
    return post("/public/get_ticker", {"instrument_name": name})


def pick_expiry(insts, tenor):
    """The listed expiry closest to the tenor's target, ignoring today's."""
    now = time.time()
    want = TENOR_DAYS.get(tenor, TENOR_DAYS["monthly"])
    exps = sorted({i["option_details"]["expiry"] for i in insts})
    exps = [e for e in exps if (e - now) / 86400 >= 1.0]
    if not exps:
        raise RuntimeError("no expiry more than a day out")
    return min(exps, key=lambda e: abs((e - now) / 86400 - want))


def fee_for(index_price, size, mark):
    """Derive taker fee: $0.50 + min(0.03% x notional, 12.5% x premium)."""
    return BASE_FEE_USD + min(TAKER_RATE * index_price * size,
                              FEE_CAP_RATE * mark * size)


# --- quoting ---------------------------------------------------------------

def build_quote(product, underlying, collateral_usd, tenor="monthly",
                otm_pct=10.0, target_delta=None):
    """Price one note. Returns the quote object the skill shows the owner.

    Nothing here is advisory: every field is read off the book or computed
    from it, so the model has no room to invent a number.
    """
    if product not in ("cash_secured_put", "covered_call"):
        raise RuntimeError("unknown product %r" % product)
    opt_type = "P" if product == "cash_secured_put" else "C"

    insts = instruments(underlying, opt_type)
    if not insts:
        raise RuntimeError("%s has no active %s options on Derive"
                           % (underlying, "put" if opt_type == "P" else "call"))

    expiry = pick_expiry(insts, tenor)
    chain = [i for i in insts if i["option_details"]["expiry"] == expiry]
    spot = num(ticker(chain[0]["instrument_name"])["index_price"])

    # Strike by rule. Delta needs a ticker each, so it is the slower path.
    if target_delta is not None:
        best, best_d = None, 1e9
        for i in chain:
            t = ticker(i["instrument_name"])
            d = abs(num((t.get("option_pricing") or {}).get("delta")))
            if abs(d - target_delta) < best_d:
                best, best_d = i, abs(d - target_delta)
            time.sleep(0.05)
        inst = best
    else:
        sign = -1 if opt_type == "P" else 1
        want = spot * (1 + sign * otm_pct / 100.0)
        inst = min(chain, key=lambda i: abs(float(i["option_details"]["strike"]) - want))

    strike = float(inst["option_details"]["strike"])
    step = num(inst["amount_step"])
    min_amt = num(inst["minimum_amount"])

    # Size is whatever the collateral fully covers - never more. For a put
    # the collateral is cash at the strike; for a call it is the asset itself.
    per_unit = strike if opt_type == "P" else spot
    raw = collateral_usd / per_unit
    size = math.floor(raw / step) * step
    size = round(size, 8)

    t = ticker(inst["instrument_name"])
    op = t.get("option_pricing") or {}
    bid, mark = num(t["best_bid_price"]), num(t["mark_price"])
    bid_sz = num(t["best_bid_amount"])
    bid_iv, mark_iv = num(op.get("bid_iv")), num(op.get("iv"))
    dte = (expiry - time.time()) / 86400.0

    q = {
        "product": product,
        "venue": "derive",
        "underlying": underlying,
        "instrument": inst["instrument_name"],
        "spot": round(spot, 6),
        "strike": strike,
        "pct_otm": round((strike / spot - 1) * 100, 2),
        "expiry": datetime.datetime.utcfromtimestamp(expiry).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "days_to_expiry": round(dte, 2),
        "size": size,
        "min_size": min_amt,
        "size_step": step,
        "delta": round(num(op.get("delta")), 4),
        "collateral": {
            "asset": "USDC" if opt_type == "P" else underlying,
            "amount": round(size * per_unit, 2),
        },
        "tradeable": False,
        "reasons": [],
    }

    # --- the gates, in the order that matters -----------------------------
    if size < min_amt or size <= 0:
        q["reasons"].append(
            "collateral too small: Derive's minimum is %g contracts, which needs "
            "about $%s" % (min_amt, "{:,.0f}".format(min_amt * per_unit)))
        return q

    if bid <= 0 or bid_iv <= 0:
        q["reasons"].append("no live bid on %s - nobody is buying this option right now"
                            % inst["instrument_name"])
        return q

    gross = bid * size
    fee = fee_for(spot, size, mark)
    net = gross - fee
    gap = (mark_iv - bid_iv) * 100 if mark_iv > 0 else 0.0

    q.update({
        "premium_usd": round(gross, 2),
        "fee_usd": round(fee, 2),
        "net_premium_usd": round(net, 2),
        "fair_value_usd": round(mark * size, 2),
        "edge_vs_fair_vol_pts": round(-gap, 2),
        "fee_drag_pct": round(fee / gross * 100, 1) if gross > 0 else None,
        "bid_iv_pct": round(bid_iv * 100, 2),
        "mark_iv_pct": round(mark_iv * 100, 2),
        "bid_depth": bid_sz,
        "apr_pct": round(net / q["collateral"]["amount"] * 365 / dte * 100, 2) if dte > 0 else None,
        "breakeven": round(strike - bid, 2) if opt_type == "P" else round(strike + bid, 2),
        "valid_until": datetime.datetime.utcfromtimestamp(
            time.time() + 60).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    if bid_sz < size:
        q["reasons"].append(
            "the bid is only %g contracts and this note needs %g - it would fill "
            "part-way or walk the book" % (bid_sz, size))
    if gap > MAX_VOL_GAP_PTS:
        q["reasons"].append(
            "the market is %.1f vol points wide against the seller (limit %.1f): "
            "selling here hands over %.0f%% of the option's value"
            % (gap, MAX_VOL_GAP_PTS, (1 - bid / mark) * 100 if mark else 0))
    if gross < MIN_PREMIUM_USD:
        q["reasons"].append("premium is $%.2f - too small to be worth a trade" % gross)
    elif fee / gross > MAX_FEE_DRAG:
        q["reasons"].append(
            "fees are %.0f%% of the premium (limit %.0f%%): too small a ticket, or "
            "too short a tenor" % (fee / gross * 100, MAX_FEE_DRAG * 100))

    q["tradeable"] = not q["reasons"]
    return q


def screen(tenor="monthly", collateral_usd=5000.0, otm_pct=10.0):
    """Which underlyings can actually carry a note right now."""
    out = []
    for cur in CURRENCIES:
        try:
            q = build_quote("cash_secured_put", cur, collateral_usd,
                            tenor=tenor, otm_pct=otm_pct)
        except Exception as exc:  # noqa: BLE001 - one bad asset must not stop the screen
            out.append({"underlying": cur, "tradeable": False,
                        "reasons": [str(exc)]})
            continue
        out.append(q)
    return out


# --- money paths (blocked until A1/A4 pass) --------------------------------

def _blocked(action):
    raise SystemExit(
        "%s needs a registered Derive session key and a funded subaccount.\n"
        "Spikes A1 (can a Butler wallet register a session key?) and A4 (does the\n"
        "Base deposit path work?) have not passed, so there is nothing to sign with.\n"
        "Quoting and screening work today; opening does not." % action)


# --- cli -------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("screen", help="which underlyings can carry a note now")
    s.add_argument("--tenor", default="monthly", choices=sorted(TENOR_DAYS))
    s.add_argument("--collateral", type=float, default=5000.0)
    s.add_argument("--otm-pct", type=float, default=10.0)

    c = sub.add_parser("chain", help="one expiry's strikes, with the book")
    c.add_argument("--underlying", required=True)
    c.add_argument("--tenor", default="monthly", choices=sorted(TENOR_DAYS))
    c.add_argument("--type", default="P", choices=["P", "C"])

    q = sub.add_parser("quote", help="price one note")
    q.add_argument("--product", required=True,
                   choices=["cash_secured_put", "covered_call"])
    q.add_argument("--underlying", required=True)
    q.add_argument("--collateral", type=float, required=True)
    q.add_argument("--tenor", default="monthly", choices=sorted(TENOR_DAYS))
    q.add_argument("--otm-pct", type=float, default=10.0)
    q.add_argument("--delta", type=float, default=None)

    for name in ("open", "close", "positions", "withdraw"):
        sub.add_parser(name, help="needs a session key (blocked: see A1/A4)")

    a = p.parse_args()

    if a.cmd == "screen":
        rows = screen(a.tenor, a.collateral, a.otm_pct)
        print(json.dumps(rows, indent=2))
    elif a.cmd == "quote":
        print(json.dumps(build_quote(a.product, a.underlying, a.collateral,
                                     a.tenor, a.otm_pct, a.delta), indent=2))
    elif a.cmd == "chain":
        insts = instruments(a.underlying, a.type)
        exp = pick_expiry(insts, a.tenor)
        rows = []
        for i in sorted([x for x in insts if x["option_details"]["expiry"] == exp],
                        key=lambda x: float(x["option_details"]["strike"])):
            t = ticker(i["instrument_name"])
            op = t.get("option_pricing") or {}
            rows.append({
                "instrument": i["instrument_name"],
                "strike": float(i["option_details"]["strike"]),
                "bid": num(t["best_bid_price"]), "bid_size": num(t["best_bid_amount"]),
                "ask": num(t["best_ask_price"]), "mark": num(t["mark_price"]),
                "bid_iv_pct": round(num(op.get("bid_iv")) * 100, 2),
                "mark_iv_pct": round(num(op.get("iv")) * 100, 2),
                "delta": round(num(op.get("delta")), 4),
            })
            time.sleep(0.05)
        print(json.dumps(rows, indent=2))
    else:
        _blocked(a.cmd)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - one-line failure for the skill to read
        print("error: %s" % exc, file=sys.stderr)
        sys.exit(1)
```
