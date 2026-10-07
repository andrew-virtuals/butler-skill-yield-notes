# The Derive helper

Write the script below to `/tmp/derive_helper.py` and run it with `python3`. Stdlib
only, no API key, no secret, read-only: it screens and quotes against Derive v3's
public API and nothing else. Opening, funding and withdrawing are `acp options`
commands in `SKILL.md`, never this file.

```sh
python3 /tmp/derive_helper.py screen --tenor monthly --collateral 5000
python3 /tmp/derive_helper.py quote --product cash_secured_put --underlying ETH --collateral 5000 --tenor monthly --otm-pct 10
python3 /tmp/derive_helper.py quote --product cash_secured_put --underlying ETH --collateral 5000 --tenor monthly --delta 0.20
python3 /tmp/derive_helper.py chain --underlying ETH --tenor monthly
```

It prints one JSON object (a list for `screen` and `chain`) on stdout. Exit `0`: the
read succeeded. Exit `1`: it did not, with a one-line `error: …` on stderr - Derive is
unreachable or does not list that asset. `--testnet` before the command reads Derive's
testnet instead.

Every quote carries `tradeable` and, when false, `reasons` in plain English. **Never
offer a note whose quote is not `tradeable`**, and never rewrite a reason into
something softer - they are already written for an owner.

## The quote, field by field

| Field | Means |
| --- | --- |
| `instrument` | Derive's name, e.g. `ETH-20261030-2300-P`; passed to `--instrument` as is |
| `strike`, `expiry`, `days_to_expiry` | the price and the date (08:00 UTC) the note turns on |
| `size` | contracts, which are units of the asset; passed to `--size` as is |
| `collateral.amount` | what the note locks: USDC for a put, units of the asset for a call; passed to `--max-collateral` |
| `collateral.usd` | the same in dollars |
| `premium_usd` | the bid times the size, before fees |
| `fee_usd` | Derive's taker fee for the whole note |
| `net_premium_usd` | what the owner receives: `premium_usd` less `fee_usd` |
| `min_premium_usd` | 95% of `net_premium_usd`, rounded down to the cent; passed to `--min-premium` |
| `apr_pct` | the net premium over the collateral, annualised - "if you kept doing this" |
| `breakeven` | strike less the bid for a put, plus it for a call |
| `edge_vs_fair_vol_pts` | how far the bid sits under Derive's own mark; negative for a seller |
| `bid_depth` | contracts on the best bid; a note bigger than this is refused |
| `valid_until` | 60 seconds after the read; quote again past it |

The gates, all in the script and all calibrated (see `venue.md`): the bid within
5 vol points of mark, fees at most 15% of the premium, a premium of at least $1, and
the best bid covering the whole note. Size is always what the collateral **fully**
covers, rounded down to Derive's step.

```python
"""Screen and quote yield notes on Derive v3, from its public API.

A yield note is one option sold short, fully collateralised:

  cash_secured_put   sell a put, hold strike x size in USDC
  covered_call       sell a call, hold size of the underlying

Read-only and keyless. Opening a note is `acp options open`, never this file.

The model never picks an instrument, a strike or a premium. It passes an
intent - product, underlying, collateral, tenor, strike rule - and gets back a
quote object with every number already fixed, including the bounds the open
command takes.

Usage:
    derive_helper.py screen [--tenor monthly] [--collateral 5000]
    derive_helper.py quote --product cash_secured_put --underlying ETH \
        --collateral 5000 [--tenor monthly] [--otm-pct 10 | --delta 0.20]
    derive_helper.py chain --underlying ETH [--tenor monthly] [--type P]

Add --testnet before the command to read Derive's testnet instead.
"""

import argparse
import datetime
import json
import math
import sys
import time
import urllib.error
import urllib.request

MAINNET = "https://api.derive.xyz/v3"
TESTNET = "https://testnet.api.derive.xyz/v3"
UA = "butler-yield-notes/1.0"

# Calibrated against measured spreads and fees; see references/venue.md.
# ETH and BTC bids sit a few vol points under mark, every other listed asset
# 10 to 60. Do not lower this to 2: that rejects every fill, good ones too.
MAX_VOL_GAP_PTS = 5.0
MAX_FEE_DRAG = 0.15
MIN_PREMIUM_USD = 1.00
QUOTE_TTL_SEC = 60
# --min-premium is set this far under the quoted net, so ordinary movement
# between quote and approval does not fail the fill.
MIN_PREMIUM_SHARE = 0.95

CURRENCIES = ["ETH", "BTC", "SOL", "XRP", "ADA", "HYPE",
              "ZEC", "XAUT", "LIT", "VVV", "PUMP", "CC"]

TENOR_DAYS = {"weekly": 9, "monthly": 24, "quarterly": 80}

BASE = MAINNET


class VenueError(Exception):
    pass


class TransportError(Exception):
    pass


def post(method, params, tries=3):
    """POST one public method. Derive's edge rejects a request with no User-Agent."""
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                "%s/%s" % (BASE, method),
                data=json.dumps(params).encode(),
                headers={"Content-Type": "application/json", "User-Agent": UA},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                out = json.load(resp)
            if out.get("error"):
                err = out["error"]
                raise TransportError(str(err.get("data") or err.get("message") or err))
            return out["result"]
        except TransportError:
            raise  # the venue answered with an error: asking again changes nothing
        except urllib.error.HTTPError as exc:
            last = "HTTP %s" % exc.code
            if 400 <= exc.code < 500 and exc.code != 429:
                raise TransportError(last)
        except Exception as exc:  # noqa: BLE001 - retried, then surfaced
            last = exc
        if attempt < tries - 1:
            time.sleep(1.2 * (attempt + 1))
    raise TransportError("%s failed: %s" % (method, last))


def num(x):
    """Derive sends numbers as strings, and nulls for an empty side."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) else 0.0


def rnd(v, places):
    # Half-up, so the numbers match bevo-server's quote engine to the cent.
    f = 10 ** places
    return math.floor(v * f + 0.5) / f


def plain(v):
    """A number the way a person writes it: 0.1, 2.17, 82.8, 3."""
    return str(int(v)) if float(v).is_integer() else repr(float(v))


def iso(sec):
    return datetime.datetime.fromtimestamp(int(sec), datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def active_options(currency, opt_type):
    out, page = [], 1
    while True:
        r = post("public/get_all_instruments", {
            "currency": currency, "instrument_type": "option",
            "expired": False, "page": page, "page_size": 1000,
        })
        out += r.get("instruments") or []
        if page >= ((r.get("pagination") or {}).get("num_pages") or 1):
            break
        page += 1
    return [i for i in out if i.get("is_active")
            and (i.get("option_details") or {}).get("option_type") == opt_type]


def pick_expiry(insts, tenor, now):
    """The listed expiry nearest the tenor's target, never one inside 24 hours."""
    want = TENOR_DAYS.get(tenor, TENOR_DAYS["monthly"])
    exps = sorted({i["option_details"]["expiry"] for i in insts})
    exps = [e for e in exps if (e - now) / 86400.0 >= 1.0]
    if not exps:
        raise VenueError("no expiry more than a day out")
    return min(exps, key=lambda e: abs((e - now) / 86400.0 - want))


def tickers_for(currency, expiry):
    day = int(datetime.datetime.fromtimestamp(int(expiry), datetime.timezone.utc).strftime("%Y%m%d"))
    r = post("public/get_tickers", {
        "currency": currency, "instrument_type": "option", "expiry_date": day,
    })
    return r.get("tickers") or {}


def taker_fee(inst, index, size, mark):
    """base + min(taker rate x index notional, cap x premium). Matched a testnet fill to the cent."""
    return num(inst.get("base_fee")) + min(
        num(inst.get("taker_fee_rate")) * index * size,
        num(inst.get("mark_price_fee_rate_cap")) * mark * size)


def load_chain(underlying, opt_type, tenor, now):
    try:
        insts = active_options(underlying, opt_type)
        if not insts:
            raise VenueError("%s has no active %s options on Derive"
                             % (underlying, "put" if opt_type == "P" else "call"))
        expiry = pick_expiry(insts, tenor, now)
        tickers = tickers_for(underlying, expiry)
    except VenueError:
        raise
    except Exception as exc:  # noqa: BLE001 - transport or a malformed answer
        raise VenueError("could not read Derive's %s options: %s" % (underlying, exc))
    chain = [i for i in insts
             if i["option_details"]["expiry"] == expiry and i["instrument_name"] in tickers]
    if not chain:
        raise VenueError("no %s prices published for that expiry" % underlying)
    return expiry, chain, tickers


def build_quote(product, underlying, collateral_usd, tenor="monthly",
                otm_pct=10.0, target_delta=None):
    if product not in ("cash_secured_put", "covered_call"):
        raise VenueError("unknown product %r" % product)
    opt_type = "P" if product == "cash_secured_put" else "C"
    underlying = underlying.strip().upper()
    now = time.time()

    expiry, chain, tickers = load_chain(underlying, opt_type, tenor, now)
    spot = num(tickers[chain[0]["instrument_name"]].get("I"))

    def delta_of(i):
        return abs(num((tickers[i["instrument_name"]].get("option_pricing") or {}).get("d")))

    if target_delta is not None:
        want = abs(target_delta)
        inst = min(chain, key=lambda i: abs(delta_of(i) - want))
    else:
        sign = -1 if opt_type == "P" else 1
        want = spot * (1 + sign * otm_pct / 100.0)
        inst = min(chain, key=lambda i: abs(num(i["option_details"]["strike"]) - want))

    t = tickers[inst["instrument_name"]]
    op = t.get("option_pricing") or {}
    strike = num(inst["option_details"]["strike"])
    step = num(inst.get("amount_step"))
    min_amt = num(inst.get("minimum_amount"))

    # Size is whatever the collateral FULLY covers, never more. Derive is a
    # margin venue and will happily carry an uncollateralised short.
    per_unit = strike if opt_type == "P" else spot
    size = round(math.floor(collateral_usd / per_unit / step + 1e-9) * step, 8) if step > 0 else 0.0
    bid, bid_sz, mark = num(t.get("b")), num(t.get("B")), num(t.get("M"))
    bid_iv, mark_iv = num(op.get("bi")), num(op.get("i"))
    dte = (expiry - now) / 86400.0
    locked_usd = rnd(size * per_unit, 2)

    q = {
        "product": product,
        "venue": "derive",
        "underlying": underlying,
        "instrument": inst["instrument_name"],
        "spot": rnd(spot, 6),
        "strike": strike,
        "pct_otm": rnd((strike / spot - 1) * 100, 2) if spot else 0.0,
        "expiry": iso(expiry),
        "expiry_sec": expiry,
        "days_to_expiry": rnd(dte, 2),
        "size": size,
        "min_size": min_amt,
        "size_step": step,
        "delta": rnd(num(op.get("d")), 4),
        # amount is what `acp options open --max-collateral` takes: USDC for a
        # put, units of the asset for a call. usd is its dollar value.
        "collateral": {
            "asset": "USDC" if opt_type == "P" else underlying,
            "amount": locked_usd if opt_type == "P" else size,
            "usd": locked_usd,
        },
        "tradeable": False,
        "reasons": [],
    }

    if size < min_amt or size <= 0:
        q["reasons"].append(
            "collateral too small: Derive's minimum is %s contracts, which needs about $%s"
            % (plain(min_amt), "{:,}".format(int(math.floor(min_amt * per_unit + 0.5)))))
        return q
    if bid <= 0 or bid_iv <= 0:
        q["reasons"].append("no live bid on %s - nobody is buying this option right now"
                            % inst["instrument_name"])
        return q

    gross = bid * size
    fee = taker_fee(inst, spot, size, mark)
    net = gross - fee
    gap = (mark_iv - bid_iv) * 100 if mark_iv > 0 else 0.0
    net_r = rnd(net, 2)

    q.update({
        "premium_usd": rnd(gross, 2),
        "fee_usd": rnd(fee, 2),
        "net_premium_usd": net_r,
        "min_premium_usd": math.floor(net_r * MIN_PREMIUM_SHARE * 100 + 1e-6) / 100,
        "fair_value_usd": rnd(mark * size, 2),
        "edge_vs_fair_vol_pts": rnd(-gap, 2),
        "fee_drag_pct": rnd(fee / gross * 100, 1),
        "bid_iv_pct": rnd(bid_iv * 100, 2),
        "mark_iv_pct": rnd(mark_iv * 100, 2),
        "bid_price": bid,
        "bid_depth": bid_sz,
        "breakeven": rnd(strike - bid if opt_type == "P" else strike + bid, 2),
        "valid_until": iso(now + QUOTE_TTL_SEC),
    })
    if dte > 0 and locked_usd > 0:
        q["apr_pct"] = rnd(net / locked_usd * (365 / dte) * 100, 2)

    if bid_sz < size:
        q["reasons"].append(
            "the bid is only %s contracts and this note needs %s - it would fill "
            "part-way or walk the book" % (plain(bid_sz), plain(size)))
    if gap > MAX_VOL_GAP_PTS:
        q["reasons"].append(
            "the market is %.1f vol points wide against the seller (limit %.1f): "
            "selling here hands over %d%% of the option's value"
            % (gap, MAX_VOL_GAP_PTS, int(math.floor((1 - bid / mark) * 100 + 0.5)) if mark else 0))
    if gross < MIN_PREMIUM_USD:
        q["reasons"].append("premium is $%.2f - too small to be worth a trade" % gross)
    elif fee / gross > MAX_FEE_DRAG:
        q["reasons"].append(
            "fees are %d%% of the premium (limit %d%%): too small a ticket, or "
            "too short a tenor" % (int(math.floor(fee / gross * 100 + 0.5)),
                                   int(math.floor(MAX_FEE_DRAG * 100 + 0.5))))

    q["tradeable"] = not q["reasons"]
    return q


def screen(tenor="monthly", collateral_usd=5000.0, otm_pct=10.0):
    """Which underlyings can carry a note right now. The offerable set is an
    output of the gates, not an allowlist; one bad asset never stops the screen."""
    out = []
    for cur in CURRENCIES:
        try:
            out.append(build_quote("cash_secured_put", cur, collateral_usd,
                                   tenor=tenor, otm_pct=otm_pct))
        except Exception as exc:  # noqa: BLE001
            out.append({"underlying": cur, "tradeable": False, "reasons": [str(exc)]})
    return out


def chain_rows(underlying, tenor, opt_type):
    expiry, chain, tickers = load_chain(underlying.strip().upper(), opt_type, tenor, time.time())
    rows = []
    for i in sorted(chain, key=lambda x: num(x["option_details"]["strike"])):
        t = tickers[i["instrument_name"]]
        op = t.get("option_pricing") or {}
        rows.append({
            "instrument": i["instrument_name"],
            "strike": num(i["option_details"]["strike"]),
            "bid": num(t.get("b")), "bid_size": num(t.get("B")),
            "ask": num(t.get("a")), "mark": num(t.get("M")),
            "bid_iv_pct": rnd(num(op.get("bi")) * 100, 2),
            "mark_iv_pct": rnd(num(op.get("i")) * 100, 2),
            "delta": rnd(num(op.get("d")), 4),
        })
    return rows


def tidy(v):
    """2300.0 -> 2300, so a number reads back the way a person writes it."""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, dict):
        return {k: tidy(x) for k, x in v.items()}
    if isinstance(v, list):
        return [tidy(x) for x in v]
    return v


def main():
    global BASE
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--testnet", action="store_true", help="read Derive's testnet")
    sub = p.add_subparsers(dest="cmd")
    sub.required = True

    s = sub.add_parser("screen", help="which underlyings can carry a note now")
    s.add_argument("--tenor", default="monthly", choices=sorted(TENOR_DAYS))
    s.add_argument("--collateral", type=float, default=5000.0)
    s.add_argument("--otm-pct", type=float, default=10.0)

    q = sub.add_parser("quote", help="price one note")
    q.add_argument("--product", required=True, choices=["cash_secured_put", "covered_call"])
    q.add_argument("--underlying", required=True)
    q.add_argument("--collateral", type=float, required=True)
    q.add_argument("--tenor", default="monthly", choices=sorted(TENOR_DAYS))
    rule = q.add_mutually_exclusive_group()
    rule.add_argument("--otm-pct", type=float, default=10.0)
    rule.add_argument("--delta", type=float, default=None)

    c = sub.add_parser("chain", help="one expiry's strikes, with the book")
    c.add_argument("--underlying", required=True)
    c.add_argument("--tenor", default="monthly", choices=sorted(TENOR_DAYS))
    c.add_argument("--type", default="P", choices=["P", "C"])

    a = p.parse_args()
    if a.testnet:
        BASE = TESTNET

    if a.cmd == "screen":
        out = screen(a.tenor, a.collateral, a.otm_pct)
    elif a.cmd == "quote":
        out = build_quote(a.product, a.underlying, a.collateral, a.tenor, a.otm_pct, a.delta)
    else:
        out = chain_rows(a.underlying, a.tenor, a.type)
    print(json.dumps(tidy(out), indent=2))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - one line for the skill to read
        print("error: %s" % exc, file=sys.stderr)
        sys.exit(1)
```
