"""Screen and quote options on Derive v3 or Paradex, from their public APIs.

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
    quote.py screen [--tenor monthly] [--collateral 5000]
    quote.py quote --product cash_secured_put --underlying ETH \
        --collateral 5000 [--tenor monthly] [--otm-pct 10 | --delta 0.20]
    quote.py quote --side buy --product call --underlying ETH \
        --budget 200 [--tenor monthly] [--otm-pct 5 | --delta 0.30]
    quote.py quote --side buy --product put --underlying ETH --size 1
    quote.py quote --side close --instrument ETH-20261030-2750-C --size 0.5
    quote.py quote --side buyback --instrument ETH-20261030-2300-P --size 2 \
        [--premium-received 61.40]
    quote.py chain --underlying ETH [--tenor monthly | --expiry 2026-10-30] [--type P]
    quote.py chain

Every command takes --venue derive (the default) or --venue paradex. A buy or
sell quote and chain take --expiry YYYY-MM-DD for the day the owner named, and a
buy or sell quote --strike for the strike they named.
"""

import argparse
import datetime
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.derive.xyz/v3"
PARADEX = "https://api.prod.paradex.trade/v1"
UA = "butler-options-trading/2.0"

# The venue this run reads: set once from --venue, then read by every function
# whose answer depends on it. The quote logic itself is the same on both.
V = {"id": "derive", "name": "Derive"}
VENUES = {"derive": {"id": "derive", "name": "Derive"},
          "paradex": {"id": "paradex", "name": "Paradex"}}

# Calibrated against measured spreads and fees; see README.md, Measurements.
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
# A sold put's bad case is said as a dollar loss at this fall from spot, so the
# model never has to compute one; 25% sits well past the default 10% OTM strike.
BAD_CASE_FALL = 0.25


# What each ticker is, since neither venue's API says (Paradex tags its stocks,
# indices and commodities alike as "RWA"). Every underlying Derive or Paradex
# listed on 2026-10-26, from Paradex's instrument docs and the Pyth feed each
# one prices from. Never fill a gap by searching the ticker: Pyth's CL is
# Colgate-Palmolive, where Paradex's CL is crude oil. Unknown: name and kind null.
KNOWN = {
    "AAVE": ("Aave", "crypto"), "ADA": ("Cardano", "crypto"),
    "AERO": ("Aerodrome", "crypto"), "AVAX": ("Avalanche", "crypto"),
    "BNB": ("BNB", "crypto"), "BTC": ("Bitcoin", "crypto"),
    "CC": ("Canton", "crypto"), "DIME": ("DIME, Paradex's token", "crypto"),
    "DOGE": ("Dogecoin", "crypto"), "ENA": ("Ethena", "crypto"),
    "ETH": ("Ethereum", "crypto"), "ETHFI": ("ether.fi", "crypto"),
    "GRAM": ("Gram (formerly Toncoin)", "crypto"), "HYPE": ("Hyperliquid", "crypto"),
    "JTO": ("Jito", "crypto"), "JUP": ("Jupiter", "crypto"),
    "KAITO": ("Kaito", "crypto"), "LDO": ("Lido DAO", "crypto"),
    "LINK": ("Chainlink", "crypto"), "LIT": ("Lighter", "crypto"),
    "LTC": ("Litecoin", "crypto"), "MON": ("Monad", "crypto"),
    "MORPHO": ("Morpho", "crypto"), "NEAR": ("NEAR Protocol", "crypto"),
    "ONDO": ("Ondo", "crypto"), "PAXG": ("PAX Gold, a gold-backed token", "crypto"),
    "PENDLE": ("Pendle", "crypto"), "PUMP": ("Pump.fun", "crypto"),
    "PYTH": ("Pyth Network", "crypto"), "SOL": ("Solana", "crypto"),
    "STRK": ("Starknet", "crypto"), "SUI": ("Sui", "crypto"),
    "TAO": ("Bittensor", "crypto"), "TRUMP": ("Official Trump", "crypto"),
    "TRX": ("TRON", "crypto"), "UNI": ("Uniswap", "crypto"),
    "VVV": ("Venice", "crypto"), "WLFI": ("World Liberty Financial", "crypto"),
    "XAUT": ("Tether Gold, a gold-backed token", "crypto"), "XMR": ("Monero", "crypto"),
    "XPL": ("Plasma", "crypto"), "XRP": ("XRP", "crypto"), "ZEC": ("Zcash", "crypto"),
    "kPEPE": ("Pepe, per 1,000 PEPE", "crypto"), "kSHIB": ("Shiba Inu, per 1,000 SHIB", "crypto"),
    "CRCL": ("Circle Internet Group", "stock"), "GOOGL": ("Alphabet, class A", "stock"),
    "INTC": ("Intel", "stock"), "META": ("Meta Platforms", "stock"),
    "MRVL": ("Marvell Technology", "stock"), "MSFT": ("Microsoft", "stock"),
    "MSTR": ("Strategy (MicroStrategy)", "stock"), "MU": ("Micron Technology", "stock"),
    "NVDA": ("NVIDIA", "stock"), "SNDK": ("Sandisk", "stock"),
    "SPCX": ("SpaceX", "stock"), "TSLA": ("Tesla", "stock"),
    "DRAM": ("Roundhill Memory ETF", "etf"), "EWY": ("iShares MSCI South Korea ETF", "etf"),
    "US500": ("US 500, the S&P 500", "index"), "US100": ("US 100, the Nasdaq-100", "index"),
    "CL": ("WTI crude oil", "commodity"), "BZ": ("Brent crude oil", "commodity"),
    "NG": ("Henry Hub natural gas", "commodity"), "XAU": ("Gold", "commodity"),
    "XAG": ("Silver", "commodity"), "XPT": ("Platinum", "commodity"),
    "XCU": ("Copper", "commodity"),
}

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


def get(path, query, tries=3):
    """GET one public Paradex path. A 4xx is Paradex's answer: asking again changes nothing."""
    last = None
    url = "%s%s?%s" % (PARADEX, path, urllib.parse.urlencode(query))
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            last = "HTTP %s" % exc.code
            if 400 <= exc.code < 500 and exc.code != 429:
                raise TransportError(last)
        except Exception as exc:  # noqa: BLE001 - retried, then surfaced
            last = exc
        if attempt < tries - 1:
            time.sleep(1.2 * (attempt + 1))
    raise TransportError("%s failed: %s" % (path, last))


# Paradex answers are reshaped into Derive's, so one set of quote functions
# serves both: an instrument as `get_all_instruments` names its fields, a
# ticker as `get_tickers` does (b/B bid, a/A ask, M mark, I index, and
# option_pricing bi/ai/i IVs and d delta).
_PDX_SUMMARIES = None


def pdx_summaries():
    """Every Paradex market's summary in one read (about 5 MB), once per run."""
    global _PDX_SUMMARIES
    if _PDX_SUMMARIES is None:
        rows = get("/markets/summary", {"market": "ALL"}).get("results") or []
        _PDX_SUMMARIES = {r.get("symbol"): r for r in rows}
    return _PDX_SUMMARIES


def pdx_inst(m):
    fees = m.get("fee_config") or {}
    # Butler's orders go out as Retail (Paradex's interactive flow), so the retail schedule applies.
    fee = ((fees.get("interactive_fee") or fees.get("api_fee") or {}).get("taker_fee")) or {}
    return {
        "instrument_name": m["symbol"],
        "is_active": True,
        "option_details": {
            "strike": m.get("strike_price"),
            "expiry": int(m["expiry_at"]) // 1000,
            "option_type": "C" if m.get("option_type") == "CALL" else "P",
        },
        "amount_step": m.get("order_size_increment"),
        # Raised to Paradex's minimum notional once the index is known (pdx_minimum).
        "minimum_amount": m.get("order_size_increment"),
        "min_notional": m.get("min_notional"),
        # Paradex charges no base fee; its taker fee is a rate on the underlying's
        # notional, capped at a share of the premium.
        "base_fee": "0",
        "taker_fee_rate": fee.get("fee"),
        "mark_price_fee_rate_cap": fee.get("fee_cap"),
        "price_band": m.get("price_bands_width"),
    }


def pdx_ticker(s, inst):
    """A side priced outside the market's price band cannot be taken (an order may
    pay at most mark x (1 + band), and sell at no less than mark x (1 - band)),
    so it is dropped, as if the book had none."""
    greeks = s.get("greeks") or {}
    bid, ask, mark, band = num(s.get("bid")), num(s.get("ask")), num(s.get("mark_price")), num(inst.get("price_band"))
    bid_ok = not (band > 0 and mark > 0 and bid < mark * (1 - band))
    ask_ok = not (band > 0 and mark > 0 and ask > mark * (1 + band))
    return {
        "b": s.get("bid") if bid_ok else None, "B": s.get("bid_size") if bid_ok else None,
        "a": s.get("ask") if ask_ok else None, "A": s.get("ask_size") if ask_ok else None,
        "M": s.get("mark_price"), "I": s.get("underlying_price"),
        "option_pricing": {"bi": s.get("bid_iv"), "ai": s.get("ask_iv"),
                           "i": s.get("mark_iv"), "d": greeks.get("delta", s.get("delta"))},
    }


def pdx_minimum(inst, index):
    """Paradex takes an order of at least `min_notional` dollars of the underlying."""
    step, floor = num(inst.get("amount_step")), num(inst.get("min_notional"))
    if step > 0 and index > 0:
        inst["minimum_amount"] = round(max(step, math.ceil(floor / index / step - 1e-9) * step), 8)


def pdx_active_options(currency, opt_type):
    """Order-book options only: an RFQ-only market cannot be filed through acp options."""
    rows = get("/markets", {"asset_kind": "OPTION", "base_asset": currency}).get("results") or []
    now = time.time()
    return [pdx_inst(m) for m in rows
            if m.get("trading_mode") == "STANDARD" and m.get("expiry_at")
            and int(m["expiry_at"]) / 1000.0 > now
            and ("C" if m.get("option_type") == "CALL" else "P") == opt_type]


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


def derive_options(currency):
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
    return [i for i in out if i.get("is_active")]


def active_options(currency, opt_type):
    if V["id"] == "paradex":
        return pdx_active_options(currency, opt_type)
    return [i for i in derive_options(currency)
            if (i.get("option_details") or {}).get("option_type") == opt_type]


def listed():
    """Every underlying the venue has order-book options on, and its expiries, by
    the venue's own ticker, with what KNOWN says it is."""
    now = time.time()
    found = {}
    try:
        if V["id"] == "paradex":
            for m in get("/markets", {"asset_kind": "OPTION"}).get("results") or []:
                exp = int(m.get("expiry_at") or 0) // 1000
                if m.get("trading_mode") == "STANDARD" and exp > now:
                    found.setdefault(m.get("base_currency"), set()).add(exp)
        else:
            for c in post("public/get_all_currencies", {}) or []:
                if not c.get("option"):
                    continue
                for i in derive_options(c["currency"]):
                    exp = int((i.get("option_details") or {}).get("expiry") or 0)
                    if exp > now:
                        found.setdefault(c["currency"], set()).add(exp)
    except Exception as exc:  # noqa: BLE001 - transport or a malformed answer
        raise VenueError("could not list %s's options: %s" % (V["name"], exc))
    return [{"underlying": u, "name": KNOWN.get(u, (None, None))[0],
             "kind": KNOWN.get(u, (None, None))[1],
             "expiries": [iso(e) for e in sorted(es)]}
            for u, es in sorted(found.items()) if u]


def pick_expiry(insts, tenor, now, on=None):
    """The listed expiry nearest the tenor's target, never one inside 24 hours, or
    the one on the day the owner named (`on`, YYYY-MM-DD, UTC), never one inside the hour."""
    exps = sorted({i["option_details"]["expiry"] for i in insts})
    if on:
        day = lambda e: datetime.datetime.fromtimestamp(int(e), datetime.timezone.utc).strftime("%Y-%m-%d")
        hit = [e for e in exps if day(e) == on and e - now >= 3600]
        if hit:
            return hit[0]
        listed = sorted({day(e) for e in exps if e - now >= 3600})
        raise VenueError("%s lists no expiry on %s; it lists %s"
                         % (V["name"], on, ", ".join(listed) or "none"))
    want = TENOR_DAYS.get(tenor, TENOR_DAYS["monthly"])
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


def load_chain(underlying, opt_type, tenor, now, on=None):
    try:
        insts = active_options(underlying, opt_type)
        if not insts:
            raise VenueError("%s has no active %s options on %s"
                             % (underlying, "put" if opt_type == "P" else "call", V["name"]))
        expiry = pick_expiry(insts, tenor, now, on)
        if V["id"] == "paradex":
            sums = pdx_summaries()
            tickers = {i["instrument_name"]: pdx_ticker(sums[i["instrument_name"]], i) for i in insts
                       if i["option_details"]["expiry"] == expiry and i["instrument_name"] in sums}
        else:
            tickers = tickers_for(underlying, expiry)
    except VenueError:
        raise
    except Exception as exc:  # noqa: BLE001 - transport or a malformed answer
        raise VenueError("could not read %s's %s options: %s" % (V["name"], underlying, exc))
    chain = [i for i in insts
             if i["option_details"]["expiry"] == expiry and i["instrument_name"] in tickers]
    if not chain:
        raise VenueError("no %s prices published for that expiry" % underlying)
    if V["id"] == "paradex":
        for i in chain:
            pdx_minimum(i, num(tickers[i["instrument_name"]].get("I")))
    return expiry, chain, tickers


def build_quote(product, underlying, collateral_usd, tenor="monthly",
                otm_pct=10.0, target_delta=None, on=None, strike=None):
    if product not in ("cash_secured_put", "covered_call"):
        raise VenueError("unknown product %r" % product)
    opt_type = "P" if product == "cash_secured_put" else "C"
    underlying = underlying.strip().upper()
    now = time.time()

    expiry, chain, tickers = load_chain(underlying, opt_type, tenor, now, on)
    spot = num(tickers[chain[0]["instrument_name"]].get("I"))

    inst = strike_for(chain, tickers, opt_type, spot, otm_pct, target_delta, strike)

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
        "venue": V["id"],
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
            "collateral too small: %s's minimum is %s contracts, which needs about $%s"
            % (V["name"], plain(min_amt), "{:,}".format(int(math.floor(min_amt * per_unit + 0.5)))))
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
    if opt_type == "P":
        low = spot * (1 - BAD_CASE_FALL)
        q["bad_case"] = {
            "fall_pct": int(BAD_CASE_FALL * 100),
            "price": rnd(low, 6),
            "loss_usd": rnd(max(strike - low, 0.0) * size - net, 2),
        }

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


def strike_for(chain, tickers, opt_type, spot, otm_pct, target_delta, strike=None):
    """The strike the owner named, exactly, or the strike rule, applied: nearest
    the target delta, or nearest spot moved otm_pct out of the money (down for a
    put, up for a call)."""
    if strike is not None:
        hit = [i for i in chain if num(i["option_details"]["strike"]) == strike]
        if not hit:
            listed = sorted({num(i["option_details"]["strike"]) for i in chain})
            raise VenueError("%s lists no %s strike for that expiry; it lists %s"
                             % (V["name"], plain(strike), ", ".join(plain(k) for k in listed)))
        return hit[0]
    if target_delta is not None:
        want = abs(target_delta)
        return min(chain, key=lambda i: abs(abs(num(
            (tickers[i["instrument_name"]].get("option_pricing") or {}).get("d"))) - want))
    sign = -1 if opt_type == "P" else 1
    want = spot * (1 + sign * otm_pct / 100.0)
    return min(chain, key=lambda i: abs(num(i["option_details"]["strike"]) - want))


def build_buy_quote(product, underlying, budget_usd=None, tenor="monthly",
                    otm_pct=5.0, target_delta=None, want_size=None, on=None, strike=None):
    """Price buying one call or put. Sized from the budget (premium + fee, with
    room for the price to move), or exactly want_size contracts for a hedge."""
    if product not in ("call", "put"):
        raise VenueError("a buy is a call or a put, not %r" % product)
    opt_type = "C" if product == "call" else "P"
    underlying = underlying.strip().upper()
    now = time.time()

    expiry, chain, tickers = load_chain(underlying, opt_type, tenor, now, on)
    spot = num(tickers[chain[0]["instrument_name"]].get("I"))
    inst = strike_for(chain, tickers, opt_type, spot, otm_pct, target_delta, strike)

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
        "venue": V["id"],
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
            "%s too small: %s's minimum is %s contracts, which costs about $%.2f "
            "with fees and room for the price to move"
            % ("size" if want_size is not None else "budget", V["name"], plain(min_amt),
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
    if V["id"] == "paradex":
        return pdx_held_option(instrument)
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


def pdx_held_option(instrument):
    name = instrument.strip().upper()
    parts = name.split("-")
    if len(parts) != 5 or parts[1] != "USD" or parts[4] not in ("C", "P"):
        raise VenueError("%r is not a Paradex option name like ETH-USD-27NOV26-2750-C" % instrument)
    try:
        m = next((x for x in get("/markets", {"market": name}).get("results") or []
                  if x.get("symbol") == name), None)
        if m is None or m.get("trading_mode") != "STANDARD":
            raise VenueError("%s is not an option Paradex's order book trades" % name)
        s = next((x for x in get("/markets/summary", {"market": name}).get("results") or []
                  if x.get("symbol") == name), None)
    except VenueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise VenueError("could not read Paradex's %s options: %s" % (parts[0], exc))
    if not s:
        raise VenueError("no price published for %s" % name)
    inst = pdx_inst(m)
    t = pdx_ticker(s, inst)
    pdx_minimum(inst, num(t.get("I")))
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
        "venue": V["id"],
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
            "%s's fee ($%.2f) is more than the bid pays ($%.2f): closing gets nothing back"
            % (V["name"], fee, gross))
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
        "venue": V["id"],
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
    output of the gates, not an allowlist; one bad asset never stops the screen.
    The underlyings are what the venue lists now; on Paradex only its crypto,
    since a note on idle USDC does not screen its stock, index or commodity options."""
    out = []
    for row in listed():
        if V["id"] == "paradex" and row["kind"] != "crypto":
            continue
        cur = row["underlying"]
        try:
            out.append(build_quote("cash_secured_put", cur, collateral_usd,
                                   tenor=tenor, otm_pct=otm_pct))
        except Exception as exc:  # noqa: BLE001
            out.append({"underlying": cur, "tradeable": False, "reasons": [str(exc)]})
    return out


def chain_rows(underlying, tenor, opt_type, on=None):
    """One expiry's strikes, each row naming it: never the venue's whole list of expiries."""
    expiry, chain, tickers = load_chain(underlying.strip().upper(), opt_type, tenor, time.time(), on)
    rows = []
    for i in sorted(chain, key=lambda x: num(x["option_details"]["strike"])):
        t = tickers[i["instrument_name"]]
        op = t.get("option_pricing") or {}
        rows.append({
            "instrument": i["instrument_name"],
            "expiry": iso(expiry),
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


def utc_day(text):
    try:
        return datetime.datetime.strptime(text.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError("%r is not a date like 2026-10-30" % text)


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
        return build_buy_quote(a.product, a.underlying, a.budget, a.tenor, otm, a.delta, a.size, a.expiry, a.strike)
    need("collateral")
    if a.product not in ("cash_secured_put", "covered_call"):
        p.error("quote --side sell takes --product cash_secured_put or covered_call")
    otm = 10.0 if a.otm_pct is None else a.otm_pct
    return build_quote(a.product, a.underlying, a.collateral, a.tenor, otm, a.delta, a.expiry, a.strike)


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
    rule.add_argument("--strike", type=float, default=None,
                      help="the strike the owner named, exactly; refused if the expiry does not list it")

    c = sub.add_parser("chain", help="one expiry's strikes, with the book; "
                                     "without --underlying, every underlying listed")
    c.add_argument("--underlying")
    c.add_argument("--tenor", default="monthly", choices=sorted(TENOR_DAYS))
    c.add_argument("--type", default="P", choices=["P", "C"])
    for sp in (q, c):
        sp.add_argument("--expiry", type=utc_day, default=None,
                        help="YYYY-MM-DD (UTC): that day's expiry instead of the tenor's")

    for sp in (s, q, c):
        sp.add_argument("--venue", default="derive", choices=sorted(VENUES))
    a = p.parse_args()
    V.update(VENUES[a.venue])

    if a.cmd == "screen":
        out = screen(a.tenor, a.collateral, a.otm_pct)
    elif a.cmd == "quote":
        out = run_quote(p, a)
    elif a.underlying:
        out = chain_rows(a.underlying, a.tenor, a.type, a.expiry)
    else:
        out = listed()
    print(json.dumps(tidy(out), indent=2))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - one line for the skill to read
        print("error: %s" % exc, file=sys.stderr)
        sys.exit(1)
