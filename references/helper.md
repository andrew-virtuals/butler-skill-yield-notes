# The Derive helper

Write the script below to `/tmp/derive_helper.py` and run it with `python3`. Stdlib
only, no API key, no secret, read-only: it screens and quotes against Derive v3's
public API and nothing else. Selling, buying, closing, funding and withdrawing are
`acp options` commands in `SKILL.md`, never this file.

```sh
python3 /tmp/derive_helper.py screen --tenor monthly --collateral 5000
python3 /tmp/derive_helper.py quote --product cash_secured_put --underlying ETH --collateral 5000 --tenor monthly --otm-pct 10
python3 /tmp/derive_helper.py quote --product cash_secured_put --underlying ETH --collateral 5000 --tenor monthly --delta 0.20
python3 /tmp/derive_helper.py quote --side buy --product call --underlying ETH --budget 200 --tenor monthly --otm-pct 5
python3 /tmp/derive_helper.py quote --side buy --product put --underlying ETH --size 1 --tenor monthly --delta 0.30
python3 /tmp/derive_helper.py quote --side close --instrument ETH-20261030-2600-C --size 2.95
python3 /tmp/derive_helper.py quote --side buyback --instrument ETH-20261030-2300-P --size 2 --premium-received 61.40
python3 /tmp/derive_helper.py chain --underlying ETH --tenor monthly --type C
```

It prints one JSON object (a list for `screen` and `chain`) on stdout. Exit `0`: the
read succeeded. Exit `1`: it did not, with a one-line `error: …` on stderr - Derive is
unreachable, does not list that asset, or the option named is not active. Exit `2`: the
command line was wrong (usage on stderr).

`quote` is the sell side unless `--side buy`, `--side close` or `--side buyback` says
otherwise. Every
quote carries `tradeable` and, when false, `reasons` in plain English. **Never offer a
trade whose quote is not `tradeable`**, and never rewrite a reason into something
softer - they are already written for an owner.

## The sell quote, field by field

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

Gates: the bid within 5 vol points of mark, fees at most 15% of the premium, a
premium of at least $1, and the best bid covering the whole note. Size is always what
the collateral **fully** covers, rounded down to Derive's step.

## The buy quote, field by field

`--product call` or `put`. `--budget` is the most the owner will spend, fees
included; `--size` asks for an exact number of contracts instead (a hedge sized to
what they hold). `--otm-pct` defaults to 5 for a buy: the strike nearest spot moved 5%
up for a call, down for a put. `--delta 0.30` picks by delta instead.

| Field | Means |
| --- | --- |
| `instrument`, `strike`, `expiry`, `days_to_expiry` | as for a sell; `instrument` is passed to `--instrument` |
| `size` | contracts; passed to `--size`. From a budget: the most the budget buys at the ask plus fee **with 5% room**, floored to Derive's step |
| `ask_price`, `ask_depth` | the best offer per contract, and how many contracts sit on it |
| `premium_usd` | the ask times the size |
| `fee_usd` | Derive's taker fee for the whole buy |
| `total_cost_usd` | `premium_usd` plus `fee_usd`: what the owner pays at today's ask |
| `max_loss_usd` | the same number: a bought option can lose all of what it cost, and no more |
| `max_cost_usd` | about 5% over `total_cost_usd`, rounded up to the cent, never over the budget; passed to `--max-cost`. It is what the owner agrees they can lose |
| `breakeven` | at expiry: strike plus total cost per contract for a call, minus it for a put |
| `overpay_vs_fair_vol_pts` | how far the ask sits over Derive's own mark; positive for a buyer |
| `fair_value_usd` | Derive's mark times the size |
| `fee_drag_pct` | the fee as a share of the premium |
| `budget_usd` | the budget asked for (absent with `--size`) |
| `valid_until` | 60 seconds after the read |

Buyer gates, each a reason in `reasons`: no live ask; the ask thinner than the size;
the ask more than 5 vol points over mark ("you would be paying N% over fair value");
fees over 15% of the premium; a budget (or size) under Derive's minimum, with what the
minimum costs.

## The close quote, field by field

Prices selling back `--size` contracts of `--instrument`, an option the owner holds
(a positive `size` in `acp options account`), on the bid now.

| Field | Means |
| --- | --- |
| `bid_price`, `bid_depth` | the best bid per contract, and its size |
| `proceeds_usd` | the bid times the size, before fees |
| `fee_usd` | Derive's fee for the sale |
| `net_proceeds_usd` | what the owner receives: `proceeds_usd` less `fee_usd` |
| `min_proceeds_usd` | 95% of `net_proceeds_usd`, rounded down; the suggested `--min-proceeds` |
| `fair_value_usd` | Derive's mark times the size |
| `edge_vs_fair_vol_pts` | how far the bid sits under mark; negative is the spread |
| `warnings` | the market is wide, or fees take a big share: say so, it does not stop a close |

A close is refused (`tradeable: false`) only when there is no bid, the bid is thinner
than the size, or the fee is more than the bid pays. An owner cutting a loss may accept
a wide market; tell them it is wide.

## The buy-back quote, field by field

Prices buying back `--size` contracts of `--instrument`, a note the owner **sold** (a
negative `size` in `acp options account`), on the ask now. `--premium-received` is
what they got for it: `netPremiumUsd` from the open's outcome, or the lifecycle duty's
`PREMIUM_USD`, scaled to the size being bought back.

| Field | Means |
| --- | --- |
| `ask_price`, `ask_depth` | the best offer per contract, and its size |
| `cost_usd` | the ask times the size, before fees |
| `fee_usd` | Derive's fee for the buy-back |
| `total_cost_usd` | `cost_usd` plus `fee_usd`: what ending the note costs at today's ask |
| `max_cost_usd` | about 5% over `total_cost_usd`, rounded up to the cent; the suggested `--max-cost` |
| `premium_received_usd` | as given (absent without `--premium-received`) |
| `result_usd` | `premium_received_usd` less `total_cost_usd`: what the note made, or lost if negative, once bought back |
| `frees` | the collateral it releases: USDC for a put, units of the asset for a call |
| `fair_value_usd` | Derive's mark times the size |
| `overpay_vs_fair_vol_pts` | how far the ask sits over mark; positive is the spread |
| `warnings` | the market is wide, or the buy-back costs more than the note brought in |

A buy-back is refused only when there is no ask or the ask is thinner than the size. An
owner getting out of a falling put may accept a wide market; tell them it is wide.

```python
"""Screen and quote options on Derive v3, from its public API.

Four sides:

  sell    one option sold short, fully collateralised, for income:
            cash_secured_put   sell a put, hold strike x size in USDC
            covered_call       sell a call, hold size of the underlying
  buy     one call or put bought outright: the most it can lose is what it costs
  close   sell back an option the owner bought, before expiry
  buyback buy back a note the owner sold, before expiry

Read-only and keyless. Trading is `acp options`, never this file.

The model never picks an instrument, a strike or a price. It passes an
intent - side, product, underlying, money, tenor, strike rule - and gets back
a quote object with every number already fixed, including the bounds the
`acp options` command takes.

Usage:
    derive_helper.py screen [--tenor monthly] [--collateral 5000]
    derive_helper.py quote --product cash_secured_put --underlying ETH \
        --collateral 5000 [--tenor monthly] [--otm-pct 10 | --delta 0.20]
    derive_helper.py quote --side buy --product call --underlying ETH \
        --budget 200 [--tenor monthly] [--otm-pct 5 | --delta 0.30]
    derive_helper.py quote --side buy --product put --underlying ETH --size 1
    derive_helper.py quote --side close --instrument ETH-20261030-2750-C --size 0.5
    derive_helper.py quote --side buyback --instrument ETH-20261030-2300-P --size 2 \
        [--premium-received 61.40]
    derive_helper.py chain --underlying ETH [--tenor monthly] [--type P]
"""

import argparse
import datetime
import json
import math
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.derive.xyz/v3"
UA = "butler-options-trading/2.0"

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
# --max-cost is set this far over the quoted total for a buy or a buy-back, and a buy is
# sized so that ceiling still fits the owner's budget.
MAX_COST_HEADROOM = 1.05

CURRENCIES = ["ETH", "BTC", "SOL", "XRP", "ADA", "HYPE",
              "ZEC", "XAUT", "LIT", "VVV", "PUMP", "CC"]

TENOR_DAYS = {"weekly": 9, "monthly": 24, "quarterly": 80}


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
    """base + min(taker rate x index notional, cap x premium). Matched a live fill to the cent."""
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

    inst = strike_for(chain, tickers, opt_type, spot, otm_pct, target_delta)

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


def strike_for(chain, tickers, opt_type, spot, otm_pct, target_delta):
    """The strike rule, applied: nearest the target delta, or nearest spot
    moved otm_pct out of the money (down for a put, up for a call)."""
    if target_delta is not None:
        want = abs(target_delta)
        return min(chain, key=lambda i: abs(abs(num(
            (tickers[i["instrument_name"]].get("option_pricing") or {}).get("d"))) - want))
    sign = -1 if opt_type == "P" else 1
    want = spot * (1 + sign * otm_pct / 100.0)
    return min(chain, key=lambda i: abs(num(i["option_details"]["strike"]) - want))


def build_buy_quote(product, underlying, budget_usd=None, tenor="monthly",
                    otm_pct=5.0, target_delta=None, want_size=None):
    """Price buying one call or put. Sized from the budget (premium + fee, with
    room for the price to move), or exactly want_size contracts for a hedge."""
    if product not in ("call", "put"):
        raise VenueError("a buy is a call or a put, not %r" % product)
    opt_type = "C" if product == "call" else "P"
    underlying = underlying.strip().upper()
    now = time.time()

    expiry, chain, tickers = load_chain(underlying, opt_type, tenor, now)
    spot = num(tickers[chain[0]["instrument_name"]].get("I"))
    inst = strike_for(chain, tickers, opt_type, spot, otm_pct, target_delta)

    t = tickers[inst["instrument_name"]]
    op = t.get("option_pricing") or {}
    strike = num(inst["option_details"]["strike"])
    step = num(inst.get("amount_step"))
    min_amt = num(inst.get("minimum_amount"))
    ask, ask_sz, mark = num(t.get("a")), num(t.get("A")), num(t.get("M"))
    ask_iv, mark_iv = num(op.get("ai")), num(op.get("i"))
    dte = (expiry - now) / 86400.0

    q = {
        "side": "buy",
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
        "size": 0.0,
        "min_size": min_amt,
        "size_step": step,
        "delta": rnd(num(op.get("d")), 4),
        "tradeable": False,
        "reasons": [],
    }
    if budget_usd is not None:
        q["budget_usd"] = rnd(budget_usd, 2)

    if ask <= 0 or ask_iv <= 0:
        q["reasons"].append("no live ask on %s - nobody is selling this option right now"
                            % inst["instrument_name"])
        return q

    # The fee is base + size x min(rate x index, cap x mark): linear in size
    # once the base is paid, so the largest affordable size has a closed form.
    base = num(inst.get("base_fee"))
    per_contract = ask + min(num(inst.get("taker_fee_rate")) * spot,
                             num(inst.get("mark_price_fee_rate_cap")) * mark)
    size = 0.0
    if want_size is not None:
        if step > 0:
            size = round(math.floor(want_size / step + 1e-9) * step, 8)
    else:
        spendable = budget_usd / MAX_COST_HEADROOM - base
        if step > 0 and spendable > 0:
            size = round(math.floor(spendable / per_contract / step + 1e-9) * step, 8)
    q["size"] = size

    if size < min_amt or size <= 0:
        need = (min_amt * per_contract + base) * MAX_COST_HEADROOM
        q["reasons"].append(
            "%s too small: Derive's minimum is %s contracts, which costs about $%.2f "
            "with fees and room for the price to move"
            % ("size" if want_size is not None else "budget", plain(min_amt),
               math.ceil(need * 100) / 100))
        return q

    gross = ask * size
    fee = taker_fee(inst, spot, size, mark)
    # The total is the sum of the two lines the owner is shown, to the cent.
    total_r = rnd(rnd(gross, 2) + rnd(fee, 2), 2)
    per = total_r / size
    max_cost = math.ceil(total_r * MAX_COST_HEADROOM * 100 - 1e-6) / 100
    if budget_usd is not None:
        max_cost = min(max_cost, rnd(budget_usd, 2))
    gap = (ask_iv - mark_iv) * 100 if mark_iv > 0 else 0.0

    q.update({
        "ask_price": ask,
        "ask_depth": ask_sz,
        "premium_usd": rnd(gross, 2),
        "fee_usd": rnd(fee, 2),
        "total_cost_usd": total_r,
        "max_loss_usd": total_r,
        "max_cost_usd": max_cost,
        "breakeven": rnd(strike + per if opt_type == "C" else strike - per, 2),
        "fair_value_usd": rnd(mark * size, 2),
        "overpay_vs_fair_vol_pts": rnd(gap, 2),
        "fee_drag_pct": rnd(fee / gross * 100, 1),
        "ask_iv_pct": rnd(ask_iv * 100, 2),
        "mark_iv_pct": rnd(mark_iv * 100, 2),
        "valid_until": iso(now + QUOTE_TTL_SEC),
    })

    if ask_sz < size:
        q["reasons"].append(
            "the ask is only %s contracts and this buy needs %s - it would fill "
            "part-way or walk the book" % (plain(ask_sz), plain(size)))
    if gap > MAX_VOL_GAP_PTS:
        q["reasons"].append(
            "the market is %.1f vol points wide against the buyer (limit %.1f): "
            "you would be paying %d%% over fair value"
            % (gap, MAX_VOL_GAP_PTS, int(math.floor((ask / mark - 1) * 100 + 0.5)) if mark else 0))
    if fee / gross > MAX_FEE_DRAG:
        q["reasons"].append(
            "fees are %d%% of the premium (limit %d%%): too small a ticket, or "
            "too short a tenor" % (int(math.floor(fee / gross * 100 + 0.5)),
                                   int(math.floor(MAX_FEE_DRAG * 100 + 0.5))))

    q["tradeable"] = not q["reasons"]
    return q


def held_option(instrument):
    """One named option and its ticker, for pricing a position already held."""
    name = instrument.strip().upper()
    parts = name.split("-")
    if len(parts) != 4 or parts[3] not in ("C", "P"):
        raise VenueError("%r is not a Derive option name like ETH-20261030-2750-C" % instrument)
    try:
        inst = next((i for i in active_options(parts[0], parts[3])
                     if i["instrument_name"] == name), None)
        if inst is None:
            raise VenueError("%s is not an active option on Derive" % name)
        t = tickers_for(parts[0], inst["option_details"]["expiry"]).get(name)
    except VenueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise VenueError("could not read Derive's %s options: %s" % (parts[0], exc))
    if not t:
        raise VenueError("no price published for %s" % name)
    return name, inst, t


def build_close_quote(instrument, size):
    """What selling back `size` of a bought option fetches on the book now.
    Only a missing or thin bid, or nothing left after fees, stops a close: an
    owner cutting a loss may accept a wide market, so width is a warning."""
    name, inst, t = held_option(instrument)
    now = time.time()
    op = t.get("option_pricing") or {}
    bid, bid_sz, mark = num(t.get("b")), num(t.get("B")), num(t.get("M"))
    bid_iv, mark_iv = num(op.get("bi")), num(op.get("i"))
    spot = num(t.get("I"))
    expiry = inst["option_details"]["expiry"]
    q = {
        "side": "close",
        "venue": "derive",
        "instrument": name,
        "strike": num(inst["option_details"]["strike"]),
        "expiry": iso(expiry),
        "expiry_sec": expiry,
        "days_to_expiry": rnd((expiry - now) / 86400.0, 2),
        "size": size,
        "spot": rnd(spot, 6),
        "fair_value_usd": rnd(mark * size, 2),
        "tradeable": False,
        "reasons": [],
        "warnings": [],
    }
    if bid <= 0:
        q["reasons"].append("no live bid on %s - nobody is buying this option right now" % name)
        return q

    gross = bid * size
    fee = taker_fee(inst, spot, size, mark)
    net = gross - fee
    net_r = rnd(net, 2)
    gap = (mark_iv - bid_iv) * 100 if mark_iv > 0 and bid_iv > 0 else 0.0
    q.update({
        "bid_price": bid,
        "bid_depth": bid_sz,
        "proceeds_usd": rnd(gross, 2),
        "fee_usd": rnd(fee, 2),
        "net_proceeds_usd": net_r,
        "min_proceeds_usd": max(0.0, math.floor(net_r * MIN_PREMIUM_SHARE * 100 + 1e-6) / 100),
        "edge_vs_fair_vol_pts": rnd(-gap, 2),
        "valid_until": iso(now + QUOTE_TTL_SEC),
    })
    if bid_sz < size:
        q["reasons"].append(
            "the bid is only %s contracts and this close is %s - close %s or less"
            % (plain(bid_sz), plain(size), plain(bid_sz)))
    if net <= 0:
        q["reasons"].append(
            "Derive's fee ($%.2f) is more than the bid pays ($%.2f): closing gets nothing back"
            % (fee, gross))
    if gap > MAX_VOL_GAP_PTS:
        q["warnings"].append(
            "the market is %.1f vol points wide: selling back here gets %d%% under fair value"
            % (gap, int(math.floor((1 - bid / mark) * 100 + 0.5)) if mark else 0))
    if gross > 0 and fee / gross > MAX_FEE_DRAG:
        q["warnings"].append("fees take %d%% of what the bid pays" % int(math.floor(fee / gross * 100 + 0.5)))
    q["tradeable"] = not q["reasons"]
    return q


def build_buyback_quote(instrument, size, premium_received=None):
    """What buying back `size` of a sold note costs on the book now. Only a
    missing or thin ask stops it: an owner getting out of a falling put may
    accept a wide market, so width - and a loss on the note - are warnings."""
    name, inst, t = held_option(instrument)
    now = time.time()
    op = t.get("option_pricing") or {}
    ask, ask_sz, mark = num(t.get("a")), num(t.get("A")), num(t.get("M"))
    ask_iv, mark_iv = num(op.get("ai")), num(op.get("i"))
    spot = num(t.get("I"))
    strike = num(inst["option_details"]["strike"])
    put = inst["option_details"]["option_type"] == "P"
    expiry = inst["option_details"]["expiry"]
    q = {
        "side": "buyback",
        "venue": "derive",
        "instrument": name,
        "strike": strike,
        "expiry": iso(expiry),
        "expiry_sec": expiry,
        "days_to_expiry": rnd((expiry - now) / 86400.0, 2),
        "size": size,
        "spot": rnd(spot, 6),
        "frees": {"asset": "USDC", "amount": rnd(strike * size, 2)} if put
                 else {"asset": name.split("-")[0], "amount": size},
        "fair_value_usd": rnd(mark * size, 2),
        "tradeable": False,
        "reasons": [],
        "warnings": [],
    }
    if ask <= 0:
        q["reasons"].append("no live ask on %s - nobody is selling this option right now" % name)
        return q

    gross = ask * size
    fee = taker_fee(inst, spot, size, mark)
    total = rnd(gross + fee, 2)
    gap = (ask_iv - mark_iv) * 100 if mark_iv > 0 and ask_iv > 0 else 0.0
    q.update({
        "ask_price": ask,
        "ask_depth": ask_sz,
        "cost_usd": rnd(gross, 2),
        "fee_usd": rnd(fee, 2),
        "total_cost_usd": total,
        "max_cost_usd": math.ceil(total * MAX_COST_HEADROOM * 100 - 1e-6) / 100,
        "overpay_vs_fair_vol_pts": rnd(gap, 2),
        "valid_until": iso(now + QUOTE_TTL_SEC),
    })
    if premium_received is not None:
        q["premium_received_usd"] = rnd(premium_received, 2)
        q["result_usd"] = rnd(premium_received - total, 2)
        if total > premium_received:
            q["warnings"].append(
                "buying back costs $%.2f, more than the $%.2f the note brought in: a $%.2f loss taken now"
                % (total, premium_received, total - premium_received))
    if ask_sz < size:
        q["reasons"].append(
            "the ask is only %s contracts and this buy-back is %s - buy back %s or less"
            % (plain(ask_sz), plain(size), plain(ask_sz)))
    if gap > MAX_VOL_GAP_PTS:
        q["warnings"].append(
            "the market is %.1f vol points wide: buying back here pays %d%% over fair value"
            % (gap, int(math.floor((ask / mark - 1) * 100 + 0.5)) if mark else 0))
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
            "ask": num(t.get("a")), "ask_size": num(t.get("A")), "mark": num(t.get("M")),
            "bid_iv_pct": rnd(num(op.get("bi")) * 100, 2),
            "ask_iv_pct": rnd(num(op.get("ai")) * 100, 2),
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


def run_quote(p, a):
    def need(*flags):
        missing = [f for f in flags if getattr(a, f) is None]
        if missing:
            p.error("quote --side %s needs %s" % (a.side, ", ".join(
                "--" + f.replace("_", "-") for f in missing)))

    if a.side == "close":
        need("instrument", "size")
        return build_close_quote(a.instrument, a.size)
    if a.side == "buyback":
        need("instrument", "size")
        return build_buyback_quote(a.instrument, a.size, a.premium_received)
    need("product", "underlying")
    if a.side == "buy":
        if (a.budget is None) == (a.size is None):
            p.error("quote --side buy takes one of --budget or --size")
        if a.product not in ("call", "put"):
            p.error("quote --side buy takes --product call or put")
        otm = 5.0 if a.otm_pct is None else a.otm_pct
        return build_buy_quote(a.product, a.underlying, a.budget, a.tenor, otm, a.delta, a.size)
    need("collateral")
    if a.product not in ("cash_secured_put", "covered_call"):
        p.error("quote --side sell takes --product cash_secured_put or covered_call")
    otm = 10.0 if a.otm_pct is None else a.otm_pct
    return build_quote(a.product, a.underlying, a.collateral, a.tenor, otm, a.delta)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    sub.required = True

    s = sub.add_parser("screen", help="which underlyings can carry a note now")
    s.add_argument("--tenor", default="monthly", choices=sorted(TENOR_DAYS))
    s.add_argument("--collateral", type=float, default=5000.0)
    s.add_argument("--otm-pct", type=float, default=10.0)

    q = sub.add_parser("quote", help="price one sell, buy, close or buy-back")
    q.add_argument("--side", default="sell", choices=["sell", "buy", "close", "buyback"])
    q.add_argument("--product", choices=["cash_secured_put", "covered_call", "call", "put"])
    q.add_argument("--underlying")
    q.add_argument("--collateral", type=float, help="sell: USD to lock")
    q.add_argument("--budget", type=float, help="buy: the most to spend, fees included")
    q.add_argument("--instrument", help="close, buyback: the option held")
    q.add_argument("--size", type=float,
                   help="close, buyback: contracts; buy: exact contracts instead of --budget")
    q.add_argument("--premium-received", type=float,
                   help="buyback: what the note brought in, for the result")
    q.add_argument("--tenor", default="monthly", choices=sorted(TENOR_DAYS))
    rule = q.add_mutually_exclusive_group()
    rule.add_argument("--otm-pct", type=float, default=None,
                      help="strike this far out of the money (sell 10, buy 5 by default)")
    rule.add_argument("--delta", type=float, default=None)

    c = sub.add_parser("chain", help="one expiry's strikes, with the book")
    c.add_argument("--underlying", required=True)
    c.add_argument("--tenor", default="monthly", choices=sorted(TENOR_DAYS))
    c.add_argument("--type", default="P", choices=["P", "C"])

    a = p.parse_args()

    if a.cmd == "screen":
        out = screen(a.tenor, a.collateral, a.otm_pct)
    elif a.cmd == "quote":
        out = run_quote(p, a)
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
