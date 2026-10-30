"""Every underlying a venue has order-book options on, with its expiries."""
import base64, datetime, json, os, socket, ssl, struct, sys, time, urllib.request

UA = "butler-options-trading/2.0"
# Kept in step with KNOWN in scripts/quote.py. Neither venue names its tickers.
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


def fetch(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"User-Agent": UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def paradex(now):
    found = {}
    for m in fetch("https://api.prod.paradex.trade/v1/markets?asset_kind=OPTION").get("results") or []:
        exp = int(m.get("expiry_at") or 0) // 1000
        if m.get("trading_mode") == "STANDARD" and exp > now:
            found.setdefault(m.get("base_currency"), set()).add(exp)
    return found


def derive(now):
    base, found = "https://api.derive.xyz/v3/public/", {}
    for c in fetch(base + "get_all_currencies", {}).get("result") or []:
        if not c.get("option"):
            continue
        page = 1
        while True:
            r = fetch(base + "get_all_instruments", {"currency": c["currency"], "instrument_type": "option",
                                                     "expired": False, "page": page, "page_size": 1000})["result"]
            for i in r.get("instruments") or []:
                exp = int((i.get("option_details") or {}).get("expiry") or 0)
                if i.get("is_active") and exp > now:
                    found.setdefault(c["currency"], set()).add(exp)
            if page >= ((r.get("pagination") or {}).get("num_pages") or 1):
                break
            page += 1
    return found


def rysk(now):
    """Rysk's inventory, over its websocket. Puts only: the skill sells puts there."""
    host = "v12.rysk.finance"
    sock = ssl.create_default_context().wrap_socket(socket.create_connection((host, 443), timeout=25),
                                                    server_hostname=host)
    try:
        sock.send(("GET /taker HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\nOrigin: https://app.rysk.finance\r\n\r\n"
                   % (host, base64.b64encode(os.urandom(16)).decode())).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = sock.recv(4096)
            if not chunk:
                raise RuntimeError("Rysk closed the connection")
            head += chunk
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise RuntimeError("Rysk refused the connection")
        data, mask = json.dumps({"id": "inventory", "jsonrpc": "2.0", "method": "inventory"}).encode(), os.urandom(4)
        sock.send(b"\x81" + bytes([0x80 | len(data)]) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        deadline = time.time() + 25
        while time.time() < deadline:
            first = sock.recv(2)
            if len(first) < 2:
                raise RuntimeError("Rysk sent nothing back")
            size = first[1] & 0x7F
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
            body = json.loads(buf.decode(errors="replace"))
            if body.get("id") == "inventory":
                break
        else:
            raise RuntimeError("Rysk did not answer in 25s")
    finally:
        sock.close()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:200])
    found = {}
    for asset, row in (body.get("result") or {}).items():
        for c in (row.get("combinations") or {}).values():
            exp = int(c.get("expiration_timestamp") or 0)
            if c.get("isPut") and exp > now:
                found.setdefault(asset, set()).add(exp)
    return found


venue = sys.argv[sys.argv.index("--venue") + 1] if "--venue" in sys.argv else "derive"
try:
    found = {"paradex": paradex, "rysk": rysk}.get(venue, derive)(time.time())
except Exception as exc:  # noqa: BLE001 - one line for the skill to read
    print("error: could not list %s's options: %s" % (venue, exc), file=sys.stderr)
    sys.exit(1)
iso = lambda e: datetime.datetime.fromtimestamp(e, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
print(json.dumps([{"underlying": u, "name": KNOWN.get(u, (None, None))[0], "kind": KNOWN.get(u, (None, None))[1],
                   "expiries": [iso(e) for e in sorted(es)]} for u, es in sorted(found.items()) if u], indent=2))
