# The Rysk helper

Write this to `/tmp/rysk.py` and run it with `python3` (`references/rysk.md` says when).
Stdlib only - no key, no account, no signature. Inventory and quotes are public reads.
A listing ("what can I trade on Rysk") is `references/listing.md`, never this helper.

```sh
python3 /tmp/rysk.py screen --collateral 5000 --pay-with <collateral.address>
python3 /tmp/rysk.py quote --asset ETH --collateral 5000 --pay-with <collateral.address>
python3 /tmp/rysk.py quote --asset ETH --collateral 5000 --pay-with <collateral.address> --delta 0.20
python3 /tmp/rysk.py quote --asset ETH --collateral 5000 --pay-with <collateral.address> --expiry 2026-11-13 --strike 2100
python3 /tmp/rysk.py chain --asset ETH --expiry 2026-11-13
python3 /tmp/rysk.py positions --address <smart account>
```

The expiry is the tenor's (`--tenor weekly`, `monthly` by default, `quarterly`: the
listed expiry nearest 7, 30 or 90 days out) unless the owner named a day: `--expiry`
(`YYYY-MM-DD`, UTC), refused with the days Rysk lists when it lists none then. The
strike is the one nearest 10% under spot (`--otm-pct`), or nearest a delta (`--delta`),
unless the owner named one: `--strike`, exactly, refused with the strikes that expiry
lists when it is not among them. `chain` gives one expiry's put strikes on one asset,
each with its `delta` and `pct_otm`, and no price: Rysk has no book, so a price is only
ever a quote.

`--pay-with` is the address of the collateral Butler sells on - **USDC on HyperEVM** -
as `acp options account --venue rysk --json` gives it (`collateral.address`). Rysk names
no stablecoin, so this helper knows a collateral only by that address. `inventory`
lists every collateral per asset (`put_collateral`), and every quote carries
`collateral_options` too. In `positions`, a `received` leg with `collateral: true` is
the stablecoin the put was backed by, coming back.

## The quote, field by field

Named as the Derive helper names them, so `SKILL.md` reads both the same way:

| Field | Means |
| --- | --- |
| `instrument` | Rysk's fields as one name, e.g. `SOL-30OCT26-95-P`; passed to `--instrument` as is |
| `strike`, `expiry`, `days_to_expiry` | the price and the instant the put turns on, as Rysk states it |
| `size` | units of the asset; passed to `--size` as is |
| `collateral.amount` | the USDC the put locks; passed to `--max-collateral` |
| `premium_usd` | `premium_per_unit` times the size, before Rysk's fee |
| `fee_usd` | Rysk's execution fee (`/api/gas`); `null` when it could not be read |
| `net_premium_usd` | what the owner receives: `premium_usd` less `fee_usd` |
| `min_premium_usd` | 95% of `net_premium_usd`, rounded down to the cent; passed to `--min-premium` unless the owner named a floor |
| `apr_pct` | the net premium over the collateral, annualised - "if you kept doing this" |
| `bad_case` | `price`, the asset `fall_pct` (25) below spot, and `loss_usd`, what the put is down at expiry there, premium counted. The owner then **holds** the asset |
| `valid_for_seconds` | how long the maker's quote has left; it is for choosing, never for acting on |

Exit codes: `0` the read succeeded, `1` it did not.

Every quote comes back with `tradeable`, a `reasons` list when that is false, and a
`notes` list of things worth saying either way. **Never offer a quote that is not
`tradeable`**, always read the `notes`, and never soften either - they are written
for an owner already.

It contains a small WebSocket client because Rysk is RFQ over a socket and the
container ships no websocket package. That is the only reason it is here; nothing
else in the file is unusual.

```python
"""Read Rysk V12 and price an option before anyone sells one.

Rysk is an RFQ venue: you ask, real market makers answer, and the answer is a
signed quote that expires in seconds. There is no order book to screen, so what
this helper does instead is turn an intent - "earn on $5,000 of USDC, ETH, a
month out" - into a quote with every number already fixed, and refuse the ones
an owner should not be shown.

Two things make Rysk different from a cash-settled venue, and both matter more
than the yield:

  * It settles **physically**. An assigned put hands the owner the asset, so
    "you now own 2.04 ETH at $2,150" is simply true. On a cash-settled venue it
    is not, and that gap has to be papered over with a separate spot buy.
  * Quotes die in **seconds**, at a `validUntil` each maker sets. Anything
    that needs a human to read and tap will miss that window, so an approval
    card cannot carry a quote.

Everything here is a public read: inventory and quotes need no key, no account
and no signature. Selling does, and that path is not in this file.
"""

import argparse
import base64
import json
import math
import os
import socket
import ssl
import struct
import sys
import time
import urllib.request

HOST = "v12.rysk.finance"
TAKER_PATH = "/taker"
GAS_URL = "https://v12.rysk.finance/api/gas"
#: The price each expiry of an asset settled at, 8dp ("0" until it has one).
#: Like the socket's `positions`, it is what Rysk's own app reads and is not in
#: the integration doc, so its shape is known from use rather than promised.
EXPIRY_PRICES_URL = "https://v12.rysk.finance/api/expiry-prices/%d/%s"

#: Rysk's own units. Strikes are 8dp, everything else is 18dp.
E8 = 10 ** 8
E18 = 10 ** 18

#: The same option can be backed on more than one chain, and the collateral
#: picks which.
CHAIN_NAMES = {1: "Ethereum", 999: "HyperEVM"}

TENOR_DAYS = {"weekly": 7, "monthly": 30, "quarterly": 90}

#: The bad case is said at this fall from spot, as the Derive helper says it.
BAD_CASE_FALL = 0.25

#: The floor suggested for `--min-premium`, as a share of the net premium -
#: the same 95% Butler's server applies when no floor is passed.
MIN_PREMIUM_SHARE = 0.95

# --- the gates -------------------------------------------------------------
# Rysk has no spread to screen, so these are about the promise the owner is
# making, not about execution quality.

#: How likely assignment is, as delta. Past this an owner is being sold an
#: option that will probably be exercised, which is a different conversation
#: from "earn on idle cash".
MAX_ASSIGNMENT_DELTA = 0.35

#: Below this the premium does not pay for the attention it costs.
MIN_APR_PCT = 4.0

#: Rysk takes fixed size steps that differ per asset and are not published in
#: the inventory. Rather than hard-code a table that will drift, the helper
#: walks this ladder and lets the venue say which step it accepts.
SIZE_STEPS = (0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 5, 10, 50, 100, 500, 1000)

#: A quote is signed and dies at `validUntil`. Anything closer than this to
#: expiring cannot survive a round trip, let alone a human.
MIN_QUOTE_SECONDS_LEFT = 20


class RyskError(RuntimeError):
    pass


# --- a websocket, in the standard library ----------------------------------
# Rysk is RFQ over a socket, and the container ships no websocket package, so
# this is the handshake and two frame operations and nothing else.


def _connect(timeout=25):
    raw = socket.create_connection((HOST, 443), timeout=timeout)
    sock = ssl.create_default_context().wrap_socket(raw, server_hostname=HOST)
    key = base64.b64encode(os.urandom(16)).decode()
    sock.send((
        "GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
        "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n"
        "Origin: https://app.rysk.finance\r\n\r\n" % (TAKER_PATH, HOST, key)
    ).encode())
    head = b""
    while b"\r\n\r\n" not in head:
        chunk = sock.recv(4096)
        if not chunk:
            raise RyskError("Rysk closed the connection during the handshake")
        head += chunk
    first = head.split(b"\r\n", 1)[0].decode(errors="replace")
    if "101" not in first:
        raise RyskError("Rysk did not accept the connection: %s" % first)
    return sock


def _send(sock, payload):
    data = json.dumps(payload).encode()
    mask = os.urandom(4)
    size = len(data)
    header = b"\x81"
    if size < 126:
        header += bytes([0x80 | size])
    elif size < 65536:
        header += bytes([0x80 | 126]) + struct.pack(">H", size)
    else:
        header += bytes([0x80 | 127]) + struct.pack(">Q", size)
    sock.send(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))


def _recv(sock, timeout=25):
    sock.settimeout(timeout)
    head = sock.recv(2)
    if len(head) < 2:
        raise RyskError("Rysk sent nothing back")
    size = head[1] & 0x7F
    if size == 126:
        size = struct.unpack(">H", sock.recv(2))[0]
    elif size == 127:
        size = struct.unpack(">Q", sock.recv(8))[0]
    buf = b""
    while len(buf) < size:
        part = sock.recv(min(65536, size - len(buf)))
        if not part:
            break
        buf += part
    return buf.decode(errors="replace")


def _call(payload, want_id, tries=3, timeout=25):
    """One request/response over a fresh socket, retried on a bad minute."""
    last = None
    for attempt in range(tries):
        sock = None
        try:
            sock = _connect()
            _send(sock, payload)
            deadline = time.time() + timeout
            while time.time() < deadline:
                body = json.loads(_recv(sock, timeout=max(2, deadline - time.time())))
                if body.get("id") != want_id:
                    continue
                if body.get("error"):
                    raise RyskError(str(body["error"])[:200])
                return body.get("result")
            raise RyskError("Rysk did not answer in %ds" % timeout)
        except RyskError:
            raise
        except Exception as exc:  # noqa: BLE001 - retried, then surfaced
            last = exc
            if attempt < tries - 1:
                time.sleep(1.5 * (attempt + 1))
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
    raise RyskError("could not reach Rysk: %s" % last)


# --- reads -----------------------------------------------------------------


def inventory():
    """Every asset Rysk offers, with its strikes, expiries and indicative APY."""
    return _call({"id": "inventory", "jsonrpc": "2.0", "method": "inventory"}, "inventory")


_tokens = {}


def _assets():
    """Market token address -> (chain id, symbol, decimals), from Rysk's own asset list.

    Inventory names neither a chain nor a symbol; this is where both come from.
    """
    if not _tokens:
        rows = _call({"id": "assets", "jsonrpc": "2.0", "method": "assets"}, "assets") or {}
        for chain, items in rows.items():
            for a in items:
                _tokens[a["address"].lower()] = (int(chain), a["symbol"], int(a.get("decimals") or 18))
    return _tokens


def _symbol(chain_id, address):
    """Rysk's name for a market token, else the address.

    Rysk names no stablecoin, and a skill may not carry one's address, so a
    collateral is known by the address the caller read (`--pay-with`).
    """
    listed = _assets().get(address.lower())
    if listed and listed[0] == chain_id:
        return listed[1]
    return address


def _options(combos):
    """Every collateral Rysk takes for these options, as it orders them."""
    tokens, seen, out = _assets(), set(), []
    for combo in combos:
        for p in combo.get("products") or []:
            chain_id = (tokens.get(p["asset"].lower()) or (None,))[0]
            key = (chain_id, p["collateralAsset"].lower())
            if chain_id is None or key in seen:
                continue
            seen.add(key)
            out.append({"token": _symbol(chain_id, p["collateralAsset"]),
                        "chain": CHAIN_NAMES.get(chain_id, str(chain_id)),
                        "chain_id": chain_id, "address": p["collateralAsset"], "product": p})
    return out


def _label(option):
    return "%s on %s" % (option["token"], option["chain"])


def _public(option):
    return {k: v for k, v in option.items() if k != "product"}


def _choose(options, asset, pay_with, chain_id):
    """The collateral at address `pay_with`, or Rysk's first when the caller named none."""
    match = [o for o in options
             if (pay_with is None or o["address"].lower() == pay_with.lower())
             and (chain_id is None or o["chain_id"] == chain_id)]
    if pay_with is None and match:
        return match[0]
    takes = ", ".join(_label(o) for o in options)
    if not match:
        raise RyskError("Rysk does not take %s for this %s put. It takes: %s"
                        % (pay_with or "collateral on that chain", asset, takes))
    if len(match) > 1:
        raise RyskError("Rysk takes %s for this %s put on more than one chain - name one "
                        "with --chain. It takes: %s" % (pay_with, asset, takes))
    return match[0]


def _puts(inv, asset):
    out = []
    for combo in (inv.get(asset, {}).get("combinations") or {}).values():
        if combo.get("isPut"):
            out.append(combo)
    return out


def _day(combo):
    return time.strftime("%Y-%m-%d", time.gmtime(combo["expiration_timestamp"]))


def _plain(strike):
    """56.5 -> "56.5", 2100.0 -> "2100": a strike the way Rysk's names write it."""
    return ("%f" % float(strike)).rstrip("0").rstrip(".")


def _at_expiry(combos, asset, tenor, on=None):
    """Every put at one expiry: the one on the day the owner named (`on`, YYYY-MM-DD,
    UTC), never one inside the hour, or else the one nearest the tenor's target,
    never one inside a day."""
    if on:
        live = [c for c in combos if (c.get("timeToExpiryDays") or 0) * 86400 >= 3600]
        hit = [c for c in live if _day(c) == on]
        if hit:
            return hit
        listed = sorted({_day(c) for c in live})
        raise RyskError("Rysk lists no %s put expiring on %s; it lists %s"
                        % (asset, on, ", ".join(listed) or "none"))
    want_days = TENOR_DAYS.get(tenor, TENOR_DAYS["monthly"])
    live = [c for c in combos if (c.get("timeToExpiryDays") or 0) >= 1]
    if not live:
        return []
    best_exp = min({round(c["timeToExpiryDays"]) for c in live},
                   key=lambda d: abs(d - want_days))
    return [c for c in live if round(c["timeToExpiryDays"]) == best_exp]


def _pick(combos, asset, tenor, otm_pct, target_delta, on=None, strike=None):
    """The strike the owner named, exactly, or the listed strike closest to the rule."""
    at_exp = _at_expiry(combos, asset, tenor, on)
    if not at_exp:
        return None
    if strike is not None:
        hit = [c for c in at_exp if float(c["strike"]) == strike]
        if not hit:
            raise RyskError("Rysk lists no %s %s put on %s; it lists %s"
                            % (asset, _plain(strike), at_exp[0]["expiry"],
                               ", ".join(_plain(k) for k in sorted({float(c["strike"]) for c in at_exp}))))
        return hit[0]
    if target_delta is not None:
        return min(at_exp, key=lambda c: abs(abs(c.get("delta") or 0) - abs(target_delta)))
    return min(at_exp, key=lambda c: abs(
        (c["strike"] / (c.get("index") or 1) - 1) * 100 + otm_pct))


def _fee(result, product, chosen, combo, size, strike, valid_until):
    """Rysk's execution fee for this quote, in USD, or None when it cannot be read.

    `/api/gas` prices a confirmation, so it is asked about this one as it would
    be sent. Stablecoins are 6dp, so its answer is in micro-dollars.
    """
    body = {
        "assetAddress": product["asset"], "chainId": chosen["chain_id"],
        "collateralAmount": str(int(round(strike * size * 10 ** 6))),
        "collateralAsset": product["collateralAsset"], "expiry": combo["expiration_timestamp"],
        "fees": "", "isEIP1271": True, "isPut": True, "isTakerBuy": False,
        "maker": result.get("maker"), "nonce": str(int(time.time() * 1000)),
        "price": str(result.get("price") or 0), "quantity": str(result.get("quantity") or 0),
        "quoteNonce": str(result.get("nonce") or ""), "quoteSignature": result.get("signature"),
        "quoteValidUntil": valid_until, "signature": "", "status": "",
        "strike": str(int(round(strike * E8))), "taker": "0x" + "0" * 40, "txHash": "",
        "usd": product["strikeAsset"], "validUntil": valid_until, "gasFee": "0",
    }
    req = urllib.request.Request(GAS_URL, json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "butler-rysk"})
    try:
        with urllib.request.urlopen(req, timeout=15) as f:
            raw = str(json.loads(f.read()).get("gasFee") or "0")
        return int(raw) / 10 ** 6 if raw.isdigit() else None
    except Exception:  # noqa: BLE001 - an unread fee is said, never guessed
        return None


def quote(asset, collateral_usd, tenor="monthly", otm_pct=10.0, target_delta=None,
          pay_with=None, chain_id=None, on=None, strike=None):
    """Ask real makers what they will pay for one cash-secured put.

    The returned price is signed and expires; `valid_for_seconds` is how long
    is actually left, not how long it was issued for. `pay_with` and
    `chain_id` choose the collateral; `collateral_options` lists every one
    Rysk takes for that strike.
    """
    asset = asset.upper()
    inv = inventory()
    if asset not in inv:
        raise RyskError("Rysk does not list %s. It offers: %s"
                        % (asset, ", ".join(sorted(inv))))
    combos = _puts(inv, asset)
    if not combos:
        raise RyskError("Rysk lists %s but is offering no puts on it right now" % asset)

    combo = _pick(combos, asset, tenor, otm_pct, target_delta, on, strike)
    if combo is None:
        raise RyskError("no %s put with an expiry more than a day out" % asset)
    options = _options([combo])
    if not options:
        raise RyskError("no tradeable product for that %s strike" % asset)
    chosen = _choose(options, asset, pay_with, chain_id)
    product = chosen["product"]

    strike = float(combo["strike"])
    index = float(combo.get("index") or 0)
    # A cash-secured put is collateralised at the strike, so the size the
    # owner can afford falls straight out of what they are willing to commit.
    wanted = collateral_usd / strike if strike else 0

    def ask(size):
        return _call({
            "id": "request", "jsonrpc": "2.0", "method": "request",
            "params": {
                "asset": product["asset"], "assetName": asset, "chainId": chosen["chain_id"],
                "expiry": combo["expiration_timestamp"], "isPut": True,
                "quantity": str(int(round(size * E18))),
                "strike": str(int(round(strike * E8))),
                "taker": "0x" + "0" * 40,
                "usd": product["strikeAsset"],
                "collateralAsset": product["collateralAsset"],
            },
        }, "request", tries=1, timeout=15)

    # Largest step that still divides what the owner can afford, walking up
    # until the venue stops complaining about the increment or the minimum.
    result, used, last = None, 0.0, None
    for step in [s for s in SIZE_STEPS if s <= max(wanted, SIZE_STEPS[0])][::-1]:
        size = int(wanted / step) * step
        if size <= 0:
            continue
        try:
            result, used = ask(round(size, 8)), size
            break
        except RyskError as exc:
            last = exc
            continue
    if result is None:
        raise RyskError(
            "Rysk would not price $%s of %s: %s. Its sizes step per asset, so a small "
            "amount may be under the minimum." % (format(collateral_usd, ",.0f"), asset,
                          str(last) if last else "no maker answered"))

    # `price` is PER UNIT, not the total - the same figure comes back for 0.5,
    # 1 and 1.5 of the same option. Multiplying is the whole premium.
    unit_price = float(result.get("price") or 0) / E18
    filled = float(result.get("quantity") or 0) / E18 or used
    premium = unit_price * filled
    collateral = strike * filled
    days = float(combo.get("timeToExpiryDays") or 0)
    valid_until = int(result.get("validUntil") or 0)
    left = valid_until - int(time.time())

    fee = _fee(result, product, chosen, combo, filled, strike, valid_until)
    net = premium - (fee or 0.0)
    net_r = round(net, 2)
    apr = (net / collateral * 365 / days * 100) if collateral and days else 0.0
    low = index * (1 - BAD_CASE_FALL)

    q = {
        "venue": "rysk",
        "product": "cash_secured_put",
        "settlement": "physical",
        # The name `acp options open --venue rysk` takes, in Rysk's own words.
        "instrument": "%s-%s-%s-P" % (asset, combo["expiry"], _plain(strike)),
        "asset": asset,
        "chain": chosen["chain"],
        "chain_id": chosen["chain_id"],
        "strike": strike,
        "index_price": round(index, 4),
        "pct_otm": round((strike / index - 1) * 100, 2) if index else None,
        "expiry": combo.get("expiry"),
        "expiry_ts": combo["expiration_timestamp"],
        "days_to_expiry": round(days, 2),
        "size": round(filled, 8),
        "delta": combo.get("delta"),
        "premium_usd": round(premium, 2),
        "fee_usd": None if fee is None else round(fee, 2),
        "net_premium_usd": net_r,
        "min_premium_usd": math.floor(net_r * MIN_PREMIUM_SHARE * 100 + 1e-6) / 100,
        "premium_per_unit": round(unit_price, 4),
        "collateral": {**_public(chosen), "amount": round(collateral, 2)},
        "collateral_options": [_public(o) for o in options],
        "apr_pct": round(apr, 2),
        "breakeven": round(strike - unit_price, 2),
        "bad_case": {"fall_pct": int(BAD_CASE_FALL * 100), "price": round(low, 6),
                     "loss_usd": round(max(strike - low, 0.0) * filled - net, 2)} if index else None,
        "maker": result.get("maker"),
        "valid_until": valid_until,
        "valid_for_seconds": left,
        "quote_nonce": result.get("nonce"),
        "quote_signature": result.get("signature"),
        "tradeable": False,
        "reasons": [],
        "notes": [],
    }

    if fee is None:
        q["notes"].append("Rysk's fee could not be read; the sale counts it against the floor")
    if filled <= 0:
        q["reasons"].append("the maker quoted no size - nobody will write that option now")
        return q
    # A short fit is worth saying, never worth hiding the note over: Rysk's
    # strikes and size steps are fixed, so a round dollar amount rarely lands
    # exactly. Refusing here would bury whichever asset pays best.
    if collateral_usd and collateral < collateral_usd * 0.95:
        q["notes"].append(
            "this puts $%s of the $%s to work - Rysk's strikes and sizes step, so a "
            "round amount rarely lands exactly"
            % (format(collateral, ",.0f"), format(collateral_usd, ",.0f")))
    if abs(combo.get("delta") or 0) > MAX_ASSIGNMENT_DELTA:
        q["reasons"].append(
            "this is close enough to the money that it will probably be exercised "
            "(delta %.2f) - a likely purchase, not idle cash earning"
            % abs(combo["delta"]))
    if apr < MIN_APR_PCT:
        q["reasons"].append(
            "%.1f%% a year does not pay for locking the money up until %s"
            % (apr, combo.get("expiry")))
    if left < MIN_QUOTE_SECONDS_LEFT:
        q["reasons"].append(
            "this quote has %ds left and dies at %d - re-quote rather than act on it"
            % (max(left, 0), valid_until))

    q["tradeable"] = not q["reasons"]
    return q


def screen(collateral_usd, tenor="monthly", otm_pct=10.0, pay_with=None, chain_id=None):
    """What Rysk will actually pay across everything it lists, right now."""
    inv = inventory()
    rows = []
    for asset in sorted(inv):
        try:
            rows.append(quote(asset, collateral_usd, tenor, otm_pct,
                              pay_with=pay_with, chain_id=chain_id))
        except RyskError as exc:
            rows.append({"asset": asset, "venue": "rysk", "tradeable": False,
                         "reasons": [str(exc)]})
    rows.sort(key=lambda r: (not r.get("tradeable"), -(r.get("apr_pct") or 0)))
    return rows


def chain(asset, tenor="monthly", on=None):
    """One expiry's puts on one asset, each row naming it: the strikes to choose from.

    No prices: Rysk has no book, so a price is only ever a quote."""
    asset = asset.upper()
    inv = inventory()
    if asset not in inv:
        raise RyskError("Rysk does not list %s. It offers: %s"
                        % (asset, ", ".join(sorted(inv))))
    combos = _puts(inv, asset)
    if not combos:
        raise RyskError("Rysk lists %s but is offering no puts on it right now" % asset)
    at_exp = _at_expiry(combos, asset, tenor, on)
    if not at_exp:
        raise RyskError("no %s put with an expiry more than a day out" % asset)
    rows = []
    for c in sorted(at_exp, key=lambda c: float(c["strike"])):
        strike, index = float(c["strike"]), float(c.get("index") or 0)
        rows.append({
            "instrument": "%s-%s-%s-P" % (asset, c["expiry"], _plain(strike)),
            "expiry": c["expiry"],
            "expiry_ts": c["expiration_timestamp"],
            "strike": strike,
            "index_price": round(index, 4),
            "pct_otm": round((strike / index - 1) * 100, 2) if index else None,
            "delta": c.get("delta"),
        })
    return rows


def _amount(raw, chain_id, address):
    """A settlement amount in the token's own units, and the token's name."""
    listed = _assets().get(address.lower())
    decimals = listed[2] if listed and listed[0] == chain_id else 6  # stablecoins are 6dp
    return {"amount": int(raw) / 10 ** decimals, "token": _symbol(chain_id, address),
            "address": address, "collateral": not (listed and listed[0] == chain_id)}


def _settled_at(cache, chain_id, asset, expiry):
    key = (chain_id, asset.lower())
    if key not in cache:
        req = urllib.request.Request(EXPIRY_PRICES_URL % key, headers={"User-Agent": "butler-rysk"})
        try:
            with urllib.request.urlopen(req, timeout=20) as f:
                cache[key] = json.loads(f.read())
        except Exception:  # noqa: BLE001 - a missing price is not a failed read of the positions
            cache[key] = {}
    raw = cache[key].get(str(expiry))
    raw = raw.get("price") if isinstance(raw, dict) else raw
    return int(raw) / E8 if raw and int(raw) else None


def positions(address):
    """Every option `address` has sold on Rysk, open first, then the latest settled.

    `received` is what settlement paid back: the collateral when an option
    expired worthless, or what assignment delivered instead - cash for a call,
    the asset for a put. `assigned` is anything back that is not the collateral,
    so it does not depend on how Rysk labels the payout. `settlement_price` is
    the price an expired one settled at, None until Rysk has it.
    """
    if not (address.startswith("0x") and len(address) == 42):
        raise RyskError("not an address: %s" % address)
    rows = _call({"id": "positions", "jsonrpc": "2.0", "method": "positions",
                  "params": {"address": address}}, "positions")
    if not isinstance(rows, list):
        raise RyskError("Rysk's positions were not a list")
    now, out, prices = time.time(), [], {}
    for r in rows:
        chain_id = int(r["chainId"])
        received = []
        if int(r.get("payout") or 0):
            received.append(_amount(r["payout"], chain_id, r["payoutAsset"]))
        if int(r.get("settlementCollateralPayout") or 0):
            received.append(_amount(r["settlementCollateralPayout"], chain_id, r["collateral"]))
        expiry = int(r["expiry"])
        if r.get("status") == "SETTLED":
            status = "settled"
        else:
            status = "open" if expiry > now else "settling"
        out.append({
            "asset": _symbol(chain_id, r["address"]),
            "asset_address": r["address"],
            "chain": CHAIN_NAMES.get(chain_id, str(chain_id)),
            "chain_id": chain_id,
            "type": "put" if r["isPut"] else "call",
            "strike": int(r["strike"]) / E18,
            "size": int(r["quantity"]) / E18,
            "expiry": time.strftime("%d%b%y", time.gmtime(expiry)).upper().lstrip("0"),
            "expiry_ts": expiry,
            "premium_usd": round(int(r.get("premium") or 0) / E18, 2),
            "status": status,
            "settlement_price": None if status == "open" else _settled_at(prices, chain_id, r["address"], expiry),
            "received": received,
            "assigned": None if status != "settled" else any(
                x["address"].lower() != r["collateral"].lower() for x in received),
            "tx": r.get("txHash"),
        })
    out.sort(key=lambda p: (p["status"] != "open",
                            p["expiry_ts"] if p["status"] == "open" else -p["expiry_ts"]))
    return out


def _utc_day(text):
    try:
        return time.strftime("%Y-%m-%d", time.strptime(text.strip(), "%Y-%m-%d"))
    except ValueError:
        raise argparse.ArgumentTypeError("%r is not a date like 2026-10-30" % text)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inventory", help="assets, strikes and expiries Rysk offers")
    s = sub.add_parser("screen", help="what every listed asset pays right now")
    s.add_argument("--collateral", type=float, required=True)
    s.add_argument("--tenor", default="monthly", choices=sorted(TENOR_DAYS))
    s.add_argument("--otm-pct", type=float, default=10.0)
    q = sub.add_parser("quote", help="one signed quote for a cash-secured put")
    q.add_argument("--asset", required=True)
    q.add_argument("--collateral", type=float, required=True)
    q.add_argument("--tenor", default="monthly", choices=sorted(TENOR_DAYS))
    rule = q.add_mutually_exclusive_group()
    rule.add_argument("--otm-pct", type=float, default=10.0)
    rule.add_argument("--delta", type=float, default=None)
    rule.add_argument("--strike", type=float, default=None,
                      help="the strike the owner named, exactly; refused if the expiry does not list it")
    c = sub.add_parser("chain", help="one expiry's put strikes on one asset")
    c.add_argument("--asset", required=True)
    c.add_argument("--tenor", default="monthly", choices=sorted(TENOR_DAYS))
    for cmd in (q, c):
        cmd.add_argument("--expiry", type=_utc_day, default=None,
                         help="YYYY-MM-DD (UTC): that day's expiry instead of the tenor's")
    for cmd in (s, q):
        cmd.add_argument("--pay-with", required=True,
                         help="the collateral's address: `collateral.address` of the account read")
        cmd.add_argument("--chain", type=int, default=None, choices=sorted(CHAIN_NAMES),
                         help="the chain the collateral is on")
    pos = sub.add_parser("positions", help="every option an address has sold, and how it settled")
    pos.add_argument("--address", required=True, help="the taker: the owner's smart account on HyperEVM")
    a = p.parse_args()

    if a.cmd == "inventory":
        inv = inventory()
        out = {}
        for asset, body in inv.items():
            combos = list((body.get("combinations") or {}).values())
            # By settlement time, not by label: "13NOV26" sorts before "30OCT26" as text.
            settles = {c["expiry"]: c.get("expiration_timestamp") or 0
                       for c in combos if c.get("expiry")}
            out[asset] = {
                "strikes": len(combos),
                "puts": sum(1 for c in combos if c.get("isPut")),
                "calls": sum(1 for c in combos if not c.get("isPut")),
                "expiries": sorted(settles, key=settles.get),
                "put_collateral": [_label(o) for o in _options(c for c in combos if c.get("isPut"))],
                "call_collateral": [_label(o) for o in _options(c for c in combos if not c.get("isPut"))],
            }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    elif a.cmd == "positions":
        print(json.dumps(positions(a.address), indent=2, ensure_ascii=False))
    elif a.cmd == "chain":
        print(json.dumps(chain(a.asset, a.tenor, a.expiry), indent=2, ensure_ascii=False))
    elif a.cmd == "screen":
        rows = screen(a.collateral, a.tenor, a.otm_pct, a.pay_with, a.chain)
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(quote(a.asset, a.collateral, a.tenor, a.otm_pct, a.delta,
                               a.pay_with, a.chain, a.expiry, a.strike), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except RyskError as exc:
        print("error: %s" % exc, file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 - one line for the skill to read
        print("error: %s" % exc, file=sys.stderr)
        sys.exit(1)
```
