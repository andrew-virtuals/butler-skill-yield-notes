"""Work one Derive options order for a better price than filling it at once.

Filling at once takes the book: a seller gets the bid, a buyer pays the ask. This
duty starts at Derive's own mark instead and gives ground toward the book slowly,
over WORK_MINUTES, never past WORST_PRICE (the fill-now price the owner agreed to).

It trades hands-free from the duty's own butler wallet (bevo-server's
`DUTY_WALLET_OPTIONS_ENABLED` rail), so the owner approves once, the funding card,
and no card after that. Whatever lands in that wallet it deposits on Derive first.

Every minute, the first of these that applies, and then the next while the minute lasts
(a cancel, the makers and a new resting order fit in one):

    a step is due     ask the makers (`--order rfq`) for the whole rest
    the book reaches  ask the makers to beat it, then take it (immediate-or-cancel)
    nothing rests     rest a post-only order at the target (not a close: Derive refuses
                      a resting reduce-only order)
    the target moved  cancel the resting order and place it again

A maker is taken at once when the quote saves TAKE_SAVING of the gap between the book and
the mark (half of it by default), and never at a price worse than the book's: the makers
do not see the bound, so a looser one costs nothing, and a fill is at the maker's own
price. A refusal names the best quote; the duty remembers it and asks again as soon as
the mark has moved enough for it to fit.

The target starts at the mark and moves toward the bid (selling) or the ask (buying)
on each STEP_MINUTES step, slowly at first and faster toward the deadline. A resting
order is pulled while Derive's prices are stale or the index moves fast against it,
when a resting order is most likely to be picked off. At the deadline it asks the
makers once more and tries the book once, both at WORST_PRICE, then finishes.

What filled is read from the account's position, never added up from answers, so a
part-fill, a resting fill and an answer that never came back all count the same.

Only this duty, while it runs, can cancel an order resting from its wallet: the chat
cannot, and a paused duty cannot. So it never finishes with one resting, it cancels any
order in its account that is not the one it is working, and STOP ends an order early:
it cancels what rests and sends the receipt for what filled.

It finishes with the receipt. What it bought or sold stays in its wallet's account, where
the owner's `options-lifecycle` duty watches it to expiry with every other option.

Settings: INSTRUMENT, ACTION, SIZE, WORST_PRICE, FEE_USD, WORK_MINUTES, STEP_MINUTES,
TAKE_SAVING, SIZE_STEP, MIN_SIZE, TICK_SIZE, FILL_NOW_PRICE, STOP.
"""

import bevo
import datetime
import json
import math
import os
import re
import subprocess
import time

PARAMS = json.loads(os.environ.get("PARAMS", "{}"))
NAME = os.environ.get("BEVO_SERVICE_NAME") or "Your options order"

INSTRUMENT = str(PARAMS.get("INSTRUMENT") or "").strip().upper()
ACTION = str(PARAMS.get("ACTION") or "").strip().lower()
SIZE = float(PARAMS.get("SIZE") or 0)
WORST = float(PARAMS.get("WORST_PRICE") or 0)
FEE_USD = float(PARAMS.get("FEE_USD") or 0)
WORK_SECONDS = float(PARAMS.get("WORK_MINUTES") or 240) * 60
#: Eight steps by default, so one setting, WORK_MINUTES, makes an order quick or patient.
STEP_SECONDS = (float(PARAMS["STEP_MINUTES"]) * 60 if PARAMS.get("STEP_MINUTES")
                else min(max(WORK_SECONDS / 8, 60), 1800))
TAKE_SAVING = float(PARAMS["TAKE_SAVING"]) if PARAMS.get("TAKE_SAVING") is not None else 0.5
SIZE_STEP = float(PARAMS.get("SIZE_STEP") or 0.01)
MIN_SIZE = float(PARAMS.get("MIN_SIZE") or SIZE_STEP)
TICK = float(PARAMS.get("TICK_SIZE") or 0.1)
FILL_NOW = float(PARAMS.get("FILL_NOW_PRICE") or WORST)
STOP = PARAMS.get("STOP") is True or str(PARAMS.get("STOP") or "").strip().lower() == "true"

#: Derive's base fee, charged once per order whatever its size; FEE_USD is the
#: fill-now quote's whole fee, so the rest of it scales with size.
BASE_FEE_USD = 0.5
STALE_SECONDS = 120
#: An index move this far against a resting order inside MOVE_WINDOW pulls it, and nothing
#: rests again for CALM_SECONDS. The window is short on purpose: re-pricing every minute
#: already follows a slow drift, and only a move faster than that picks a resting order off.
MOVE_PCT = 0.003
MOVE_WINDOW = 5 * 60
CALM_SECONDS = 15 * 60
#: A resting order moves only when its target does by more than this and more than 1.5
#: ticks: a mark flickering by one tick would otherwise cancel and re-place the same price.
REPRICE_PCT = 0.01
#: The order finishes this long before expiry, whatever WORK_MINUTES says.
EXPIRY_MARGIN = 3600
MAX_RFQS = 16
#: Between steps the makers are asked again no sooner than this, and a remembered quote
#: is believed no longer than QUOTE_TTL.
RFQ_GAP = 180
QUOTE_TTL = 1800
#: One run sends up to this many commands, and starts none after CHAIN_SECONDS: an RFQ
#: takes about 25 seconds, a cancel or a resting order a few.
MAX_CHAIN = 3
CHAIN_SECONDS = 40
#: Below this the venue takes no deposit, so it stays in the wallet.
MIN_DEPOSIT_USD = 10
DEPOSIT_WAIT = 600
UNFUNDED_AFTER = 1800
#: Refusals that no later minute can fix: the duty stops and says why.
FATAL = {"OPTIONS_DUTY_OFF", "OPTIONS_DUTY_NO_WALLET", "OPTIONS_VENUE_NOT_DUTY",
         "OPTIONS_BAD_COMMAND", "OPTIONS_SIGNER_NOT_READY"}

S = bevo.state
#: State and keys belong to one set of settings: new settings are a new order, and its
#: keys must not meet the ledger's answers for the old one.
def fnv1a(text):
    h = 0x811C9DC5
    for byte in text.encode("utf-8"):
        h = ((h ^ byte) * 0x01000193) & 0xFFFFFFFF
    return "%08x" % h


# STOP ends the order it is set on, so it is no part of which order this is.
ORDER_TAG = fnv1a(json.dumps({k: v for k, v in PARAMS.items() if k != "STOP"}, sort_keys=True))
NAME_RE = re.compile(r"^([A-Z0-9]+)-(\d{8})-([0-9_]+)-([PC])$")
#: The rail's refusal of an RFQ names the best quote, fees included, for the whole size.
QUOTE_RE = re.compile(r"best quote (?:costs|pays) \$([0-9][0-9,]*(?:\.[0-9]+)?)")


def say(text):
    """`bevo.log()` on one line: an echoed error must not forge a log line."""
    bevo.log(" ".join(str(text).split()))


def money(value):
    return "$" + format(round(float(value), 2), ",.2f")


def units(value):
    return ("%.8f" % float(value)).rstrip("0").rstrip(".")


def problem():
    """What is wrong with the settings, or ""."""
    if not NAME_RE.match(INSTRUMENT):
        return "INSTRUMENT must be a Derive option name such as ETH-20261128-3000-P"
    if ACTION not in ("open", "buy", "close"):
        return "ACTION must be open, buy or close"
    if SIZE <= 0 or WORST <= 0:
        return "SIZE and WORST_PRICE must be above 0"
    if FEE_USD < 0 or STEP_SECONDS < 60 or WORK_SECONDS < STEP_SECONDS:
        return "FEE_USD, STEP_MINUTES or WORK_MINUTES is out of range"
    if not 0 <= TAKE_SAVING <= 1:
        return "TAKE_SAVING must be between 0 and 1"
    if expiry() - EXPIRY_MARGIN <= time.time():
        return "%s expires within the hour" % INSTRUMENT
    return ""


def expiry():
    """Derive settles at 08:00 UTC on the day the name gives."""
    day = NAME_RE.match(INSTRUMENT).group(2)
    at = datetime.datetime.strptime(day + "08", "%Y%m%d%H").replace(tzinfo=datetime.timezone.utc)
    return at.timestamp()


def strike():
    return float(NAME_RE.match(INSTRUMENT).group(3).replace("_", "."))


def is_call():
    return NAME_RE.match(INSTRUMENT).group(4) == "C"


def side():
    """`sell` or `buy`. A close is the opposite of what the account held when it started."""
    if ACTION == "open":
        return "sell"
    if ACTION == "buy":
        return "buy"
    return "sell" if float(S.get("start_pos") or 0) > 0 else "buy"


def floor_to(value, step):
    return math.floor(value / step + 1e-9) * step


def fee(size):
    """What Derive and the Virtuals platform fee charge on one order of `size`, estimated
    from the fill-now quote."""
    return BASE_FEE_USD + max(FEE_USD - BASE_FEE_USD, 0.0) * size / SIZE


def acp(key, *args):
    """One `acp options` command: its JSON answer, or {} when it printed none."""
    try:
        run = subprocess.run(["acp", "options", *args, "--idempotency-key", key],
                             capture_output=True, text=True, timeout=170, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        say("acp options %s: %s" % (args[0], exc))
        return {}
    for line in reversed((run.stdout or "").strip().splitlines()):
        try:
            answer = json.loads(line)
        except ValueError:
            continue
        if isinstance(answer, dict):
            return answer
    try:
        answer = json.loads(run.stdout or "{}")
        return answer if isinstance(answer, dict) else {}
    except ValueError:
        return {}


def ledger(key):
    """The ledger row's answer: (outcome, refusal code, what the refusal said)."""
    row = bevo.exec_status(key, route="options") or {}
    body = row.get("response") or {}
    outcome = body.get("outcome") or row.get("approvalOutcome") or {}
    return ((outcome if isinstance(outcome, dict) else {}),
            body.get("code") or row.get("approvalFailureCode"), str(body.get("error") or ""))


def read_market():
    """{mark, bid, ask, index, fresh}, or None when it cannot be read."""
    try:
        body = bevo.read("/options/ticker", {"instrument": INSTRUMENT}) or {}
        mark, index = float(body["mark"]), float(body["index"])
    except (bevo.BevoError, KeyError, TypeError, ValueError) as exc:
        say("could not read %s's prices: %s" % (INSTRUMENT, exc))
        return None
    as_of = float(body.get("asOf") or 0) / 1000.0
    return {"mark": mark, "index": index,
            "bid": float(body["bid"]) if body.get("bid") else None,
            "ask": float(body["ask"]) if body.get("ask") else None,
            "fresh": time.time() - as_of <= STALE_SECONDS}


def read_account():
    """The duty wallet's Derive account, or None when it cannot be read."""
    try:
        account = (bevo.read("/options/account") or {}).get("account")
    except bevo.BevoError as exc:
        say("could not read the options account: %s" % exc)
        return None
    return account if isinstance(account, dict) else None


def held(account):
    return sum(float(row.get("size") or 0) for row in account.get("positions") or []
               if str(row.get("instrument") or "").upper() == INSTRUMENT)


def open_orders(account):
    """Every open order in the duty's account, or None when the read could not see orders."""
    if account.get("ordersUnread"):
        return None
    return [o for o in account.get("openOrders") or []
            if isinstance(o, dict) and o.get("status", "open") == "open"]


def filled(account):
    sign = 1 if side() == "buy" else -1
    moved = sign * (held(account) - float(S["start_pos"]))
    return min(moved, SIZE) if moved > 0 else 0.0


def need_usd():
    """The USDC the whole order needs free on Derive before it starts."""
    if ACTION == "open":
        return strike() * SIZE
    if ACTION == "buy":
        return WORST * SIZE + fee(SIZE)
    return 0.0


def target(market, now):
    """This step's price per contract: the mark, moved toward the book by the share of
    the time spent squared, and never past WORST_PRICE."""
    mark = market["mark"]
    total = max(1, math.ceil((S["deadline"] - S["started"]) / STEP_SECONDS))
    step = min(int((now - S["started"]) // STEP_SECONDS), total)
    share = (step / float(total)) ** 2
    if side() == "sell":
        book = market["bid"] if market["bid"] is not None else WORST
        price = mark - max(mark - book, 0.0) * share
        return max(price, WORST), step
    book = market["ask"] if market["ask"] is not None else WORST
    price = mark + max(book - mark, 0.0) * share
    return min(price, WORST), step


def book_price(market):
    return market["bid"] if side() == "sell" else market["ask"]


def maker_price(market, price):
    """The worst price per contract a maker is taken at now: the target, or the price that
    saves TAKE_SAVING of the gap between the book and the mark when that is easier to meet;
    never past WORST_PRICE, and never worse than the book, which can be had without asking."""
    book, mark = book_price(market), market["mark"]
    if side() == "sell":
        if book is not None and mark > book:
            price = min(price, book + TAKE_SAVING * (mark - book))
        return max(price, WORST, book or 0.0)
    if book is not None and book > mark:
        price = max(price, book - TAKE_SAVING * (book - mark))
    return min(price, WORST, book if book is not None else WORST)


def learn_quote(said, fly):
    """Remember the best quote a refused RFQ named, per contract before fees, with the mark
    it was made at. A refusal that names none means no maker answered."""
    found = QUOTE_RE.search(said)
    size = float(fly.get("size") or 0)
    if not found or size <= 0 or not fly.get("mark"):
        S.pop("quote", None)
        return
    usd = float(found.group(1).replace(",", ""))
    each = (usd - fee(size)) / size if side() == "buy" else (usd + fee(size)) / size
    S["quote"] = {"price": each, "mark": fly["mark"], "at": time.time()}


def quote_fits(market, line, left, now):
    """True when the makers' last quote, moved by as much as the mark has since, is inside
    `line`: asking again should fill."""
    quote = S.get("quote")
    if not quote or now - float(quote["at"]) > QUOTE_TTL:
        return False
    guess = float(quote["price"]) + market["mark"] - float(quote["mark"])
    slack = 0.01 / left  # the refusal rounds the quote to the cent, for the whole size
    return guess <= line - slack if side() == "buy" else guess >= line + slack


def taker_argv(price, size):
    """The immediate-or-cancel command for `size` at `price` per contract, net of fees as
    the rail bounds it; None when the fees eat the whole premium."""
    gross, cost = price * size, fee(size)
    size_arg = ["--instrument", INSTRUMENT, "--size", units(size)]
    if side() == "sell":
        floor = math.ceil((gross - cost) * 100 - 1e-6) / 100.0
        if floor <= 0:
            return None
        if ACTION == "open":
            collateral = math.ceil(strike() * size * 100) / 100.0
            return ["open", *size_arg, "--min-premium", "%.2f" % floor, "--max-collateral", "%.2f" % collateral]
        return ["close", *size_arg, "--min-proceeds", "%.2f" % floor]
    ceiling = math.floor((gross + cost) * 100 + 1e-6) / 100.0
    return ["buy" if ACTION == "buy" else "close", *size_arg, "--max-cost", "%.2f" % ceiling]


def on_tick(price):
    """The price a resting order actually rests at: Derive's tick, rounded up for a sale and
    down for a buy, as the rail rounds it."""
    steps = price / TICK
    steps = math.ceil(steps - 1e-9) if side() == "sell" else math.floor(steps + 1e-9)
    return round(steps * TICK, 8)


def resting_argv(price, size):
    size_arg = ["--instrument", INSTRUMENT, "--size", units(size), "--order", "post-only"]
    if ACTION == "open":
        collateral = math.ceil(strike() * size * 100) / 100.0
        return ["open", *size_arg, "--max-collateral", "%.2f" % collateral, "--min-price", "%.4f" % price]
    return ["buy", *size_arg, "--max-price", "%.4f" % price]


def send(op, argv, price=None, size=None, mark=None):
    """Send one command under the next key and settle it in this run when it can."""
    key = bevo.key("om", bevo.SERVICE_ID, ORDER_TAG, int(S.get("n") or 0), op)
    S["fly"] = {"key": key, "op": op, "argv": argv, "price": price, "size": size, "mark": mark}
    answer = acp(key, *argv)
    code = answer.get("code")
    if code in FATAL:
        stop_fatal(code, answer.get("error") or answer.get("message") or code)
    settle(wait=45)


def settle(wait=0):
    """How the command in flight ended. True while it is still running."""
    fly = S.get("fly")
    if not fly:
        return False
    fate = bevo.settled(fly["key"], route="options", wait=wait)
    if fate in ("waiting", "approval"):
        return True
    outcome, code, said = ledger(fly["key"]) if fate in ("executed", "dropped") else ({}, None, "")
    if fate == "dropped" and code == "OPTIONS_BUSY":
        say("%s: the options rail is busy; the same command goes again next run" % fly["op"])
        S["fly"] = dict(fly, retry=True)
        return True
    if fate == "dropped" and code in FATAL:
        stop_fatal(code, code)
    if fly["op"] == "rest":
        order = outcome.get("order") if isinstance(outcome.get("order"), dict) else {}
        order_id = order.get("orderId") or outcome.get("orderId")
        if fate == "executed" and order_id and outcome.get("resting", True):
            S["rest_id"], S["rest_price"] = str(order_id), fly["price"]
            S["last_rest_price"] = fly["price"]
    elif fly["op"] in ("rfq", "take") and fate == "executed":
        trade = outcome.get("trade") if isinstance(outcome.get("trade"), dict) else {}
        size = trade.get("filledSize", outcome.get("filledSize", trade.get("size")))
        if trade.get("grossUsd") is not None and size:
            S["taken_usd"] = float(S.get("taken_usd") or 0) + float(trade["grossUsd"])
            S["taken_size"] = float(S.get("taken_size") or 0) + float(size)
            if fly["op"] == "rfq":
                S["maker_size"] = float(S.get("maker_size") or 0) + float(size)
        S.pop("quote", None)
    elif fly["op"] == "rfq" and fate == "dropped":
        learn_quote(said, fly)
    elif fly["op"] == "cancel" and (fate == "executed" or code == "OPTIONS_ORDER_NOT_FOUND"):
        S.pop("rest_id", None)
        S.pop("rest_price", None)
    if fate == "unknown":
        say("%s: no answer came back for %s; the account says what happened" % (fly["op"], fly["key"]))
    elif fate == "dropped":
        say("%s: nothing traded (%s)" % (fly["op"], code or "refused"))
    S["n"] = int(S.get("n") or 0) + 1
    S.pop("fly", None)
    return False


def resend():
    """A command the rail was too busy for goes again under its own key."""
    fly = S["fly"]
    acp(fly["key"], *fly["argv"])
    S["fly"] = {k: v for k, v in fly.items() if k != "retry"}
    settle(wait=45)


def stop_fatal(code, why):
    say("options rail refused: %s" % code)
    rest_note = (" An order it placed still rests on Derive, until the option expires or this "
                 "duty runs again and cancels it." if S.get("rest_id") else "")
    bevo.status("stopped")
    bevo.done("%s stopped: Butler's server refused its orders (%s), and that will not change "
              "by itself.%s" % (NAME, why, rest_note))


def track_orders(account):
    """Line the state up with the orders the account shows. True when it cancelled a stray:
    the wallet is this duty's alone, so any order that is not the one it works is one an
    earlier order left behind, on this option or another."""
    orders = open_orders(account)
    if orders is None:
        return False
    ids = [str(o.get("orderId")) for o in orders]
    if S.get("rest_id") and S["rest_id"] not in ids:
        S.pop("rest_id", None)
        S.pop("rest_price", None)
    mine = [o for o in orders if str(o.get("instrument") or "").upper() == INSTRUMENT]
    if not S.get("rest_id") and mine and "started" in S and not STOP:
        S["rest_id"] = str(mine[0].get("orderId"))
        S["rest_price"] = float(mine[0].get("limitPricePerUnitUsd") or 0)
        S["last_rest_price"] = S["rest_price"]
    strays = [i for i in ids if STOP or i != S.get("rest_id")]
    if strays:
        send("cancel", ["cancel", "--order", strays[0]])
        return True
    return False


def cancel_resting():
    send("cancel", ["cancel", "--order", S["rest_id"]])


def calm(market, now):
    """False while the index has just moved fast against the order: it then rests nothing."""
    seen = [p for p in S.get("index") or [] if now - p[0] <= MOVE_WINDOW] + [[now, market["index"]]]
    S["index"] = seen
    against = 1 if is_call() == (side() == "sell") else -1
    ref = min(p[1] for p in seen) if against > 0 else max(p[1] for p in seen)
    if ref > 0 and against * (market["index"] - ref) / ref >= MOVE_PCT:
        S["calm_from"] = now + CALM_SECONDS
        S["index"] = [[now, market["index"]]]
        say("the index moved %.2f%% against the order; pausing" % (100 * abs(market["index"] - ref) / ref))
    return now >= float(S.get("calm_from") or 0)


def set_up(account, now):
    """Its wallet's USDC onto Derive, then the start. True once it is working."""
    if "born" not in S:
        S["born"] = now
    free = float(account.get("freeForNewPutsUsd") or 0) if account.get("exists") else 0.0
    if free + 0.01 >= need_usd():
        start(account, now)
        return True
    if now - float(S.get("deposit_at") or 0) >= DEPOSIT_WAIT:
        try:
            cash = bevo.balance().cash_usd
        except bevo.BevoError:
            cash = None
        if cash is not None and cash >= MIN_DEPOSIT_USD:
            n = int(S.get("deposits") or 0)
            acp(bevo.key("om", bevo.SERVICE_ID, ORDER_TAG, "deposit", n), "deposit", "--amount", str(int(cash)),
                "--from", "8453")
            S["deposits"], S["deposit_at"] = n + 1, now
            bevo.status("moving", amount=int(cash))
            return False
    if not S.get("deposits") and now - S["born"] >= UNFUNDED_AFTER and not S.get("unfunded_told"):
        S["unfunded_told"] = True
        bevo.notify("%s has not started: it needs %s free on Derive and its wallet is empty. "
                    "Approve its funding card, or top it up." % (NAME, money(need_usd())),
                    push="%s is not funded" % NAME)
    bevo.status("setting_up", free=round(free, 2), need=round(need_usd(), 2))
    return False


def start(account, now):
    S["started"] = now
    S["deadline"] = min(now + WORK_SECONDS, expiry() - EXPIRY_MARGIN)
    S["start_pos"] = held(account)
    S["told_filled"] = 0.0
    if ACTION == "close" and not S["start_pos"]:
        finish(account, "there is no %s position to close" % INSTRUMENT)
    verb = {"sell": "sell", "buy": "buy"}[side()]
    limit = "never under" if side() == "sell" else "never over"
    until = datetime.datetime.fromtimestamp(S["deadline"], datetime.timezone.utc).strftime("%H:%M UTC")
    bevo.notify("%s: working your order to %s %s %s, starting at Derive's mark and %s %s each, "
                "until %s." % (NAME, verb, units(SIZE), INSTRUMENT, limit, money(WORST), until))


def remaining(account):
    return floor_to(SIZE - filled(account), SIZE_STEP)


def report_fill(account):
    done = filled(account)
    if done > float(S.get("told_filled") or 0) + 1e-9 and done < SIZE - 1e-9:
        S["told_filled"] = done
        bevo.notify("%s: %s of %s filled so far." % (NAME, units(done), units(SIZE)), quiet=True)


def price_fills(account):
    """Price what filled. A maker's quote or the book reports its own gross; whatever else
    the position shows filled on a resting order, at that order's own limit. Derive's
    entry price is no use here: it has the fee in it."""
    if "start_pos" not in S:
        return
    known = float(S.get("taken_size") or 0) + float(S.get("rested_size") or 0)
    extra = filled(account) - known
    if extra > 1e-9 and S.get("last_rest_price"):
        S["rested_usd"] = float(S.get("rested_usd") or 0) + extra * float(S["last_rest_price"])
        S["rested_size"] = float(S.get("rested_size") or 0) + extra


def average(done):
    """The average price per contract before fees, or None when a fill cannot be priced."""
    size = float(S.get("taken_size") or 0) + float(S.get("rested_size") or 0)
    if done <= 0 or abs(size - done) > 1e-6:
        return None
    return (float(S.get("taken_usd") or 0) + float(S.get("rested_usd") or 0)) / size


def filled_by():
    """Where the fills came from, for the receipt."""
    maker, rested = float(S.get("maker_size") or 0), float(S.get("rested_size") or 0)
    book = float(S.get("taken_size") or 0) - maker
    parts = [text % units(size) for size, text in (
        (maker, "%s by a maker's quote"), (rested, "%s on its resting order"), (book, "%s from the book"))
        if size > 1e-9]
    return " Filled: %s." % ", ".join(parts) if parts else ""


def finish(account, why=""):
    price_fills(account)
    done = filled(account) if "start_pos" in S else 0.0
    verb = "Sold" if side() == "sell" else "Bought"
    if done <= 0:
        line = "%s: nothing filled%s. Nothing was traded." % (NAME, ", " + why if why else "")
    else:
        line = "%s: %s %s of %s %s." % (NAME, verb, units(done), units(SIZE), INSTRUMENT)
        price = average(done)
        if price:
            # The rail reports a fill's gross to the cent, which on a small order is not exact.
            rough = float(S.get("taken_size") or 0) > 0 and 0.005 / done >= 0.01
            line += " Average %s%s each before fees" % ("about " if rough else "", money(price))
            if FILL_NOW:
                better = (price - FILL_NOW) if side() == "sell" else (FILL_NOW - price)
                line += ", %s each %s than filling at once (%s), %s in all" % (
                    money(abs(better)), "better" if better >= 0 else "worse", money(FILL_NOW),
                    money(abs(better) * done))
            line += "." + filled_by()
        if why:
            line += " Stopped: %s." % why
    bevo.status("done", filled=units(done), size=units(SIZE))
    bevo.done(line)


def sweep(account, market):
    """At the deadline: pull what rests, ask the makers at WORST_PRICE, try the book, finish."""
    left = remaining(account)
    if S.get("rest_id"):
        cancel_resting()
        return
    if left < MIN_SIZE:
        finish(account)
    stage = int(S.get("sweep") or 0)
    S["sweep"] = stage + 1
    bevo.status("sweeping", filled=units(filled(account)), size=units(SIZE))
    # A maker has to beat the book; what the book has is taken right after.
    price = maker_price(market, WORST) if stage == 0 else WORST
    argv = taker_argv(price, left)
    if stage >= 2 or not argv:
        finish(account, "no one would %s at %s or better by the deadline" % (
            "buy" if side() == "sell" else "sell", money(WORST)))
    send("rfq" if stage == 0 else "take", argv + (["--order", "rfq"] if stage == 0 else []), price, left,
         market["mark"])


def work(account, market, now):
    price_fills(account)
    left = remaining(account)
    if left < MIN_SIZE:
        if S.get("rest_id"):
            cancel_resting()  # what is left of it is under the venue's minimum
            return
        finish(account)
    report_fill(account)
    if now >= S["deadline"]:
        sweep(account, market)
        return
    resting = bool(S.get("rest_id"))
    if not market["fresh"]:
        if resting:
            cancel_resting()
        bevo.status("paused", filled=units(filled(account)), size=units(SIZE))
        return
    # A fast move only stops resting: a maker's quote and the book are priced at this moment.
    still = calm(market, now)
    if not still and resting:
        cancel_resting()
        bevo.status("paused", filled=units(filled(account)), size=units(SIZE))
        return
    price, step = target(market, now)
    if still:
        bevo.status("working", filled=units(filled(account)), size=units(SIZE), price=round(price, 2))
    else:
        bevo.status("paused", filled=units(filled(account)), size=units(SIZE))
    book = book_price(market)
    crosses = book is not None and (book >= price if side() == "sell" else book <= price)
    line = maker_price(market, price)
    due = step > int(S.get("rfq_step", -1))
    again = now - float(S.get("rfq_at") or 0) >= RFQ_GAP and (crosses or quote_fits(market, line, left, now))
    if (due or again) and int(S.get("rfqs") or 0) < MAX_RFQS:
        if resting:
            cancel_resting()
            return
        S["rfq_step"], S["rfqs"], S["rfq_at"] = step, int(S.get("rfqs") or 0) + 1, now
        argv = taker_argv(line, left)
        if argv:
            send("rfq", argv + ["--order", "rfq"], line, left, market["mark"])
        return
    if crosses:
        if resting:
            cancel_resting()
            return
        argv = taker_argv(price, left)
        if argv:
            send("take", argv, price, left)
        return
    if ACTION == "close" or not still:
        return
    rest_at = on_tick(price)
    if not resting:
        send("rest", resting_argv(rest_at, left), rest_at, left)
    elif abs(float(S.get("rest_price") or 0) - rest_at) > max(REPRICE_PCT * price, 1.5 * TICK):
        cancel_resting()


def run():
    """One minute: act, and act again on what that changed while there is time."""
    began = time.monotonic()
    for _ in range(MAX_CHAIN):
        n = int(S.get("n") or 0)
        act()
        if S.get("fly") or int(S.get("n") or 0) == n or time.monotonic() - began > CHAIN_SECONDS:
            return


def act():
    if S.get("fly"):
        if S["fly"].get("retry"):
            resend()
        elif settle(wait=20):
            bevo.status("busy")
            return
    if S.get("fly"):
        bevo.status("busy")
        return
    account = read_account()
    if account is None:
        bevo.status("unreadable")
        return
    now = time.time()
    # Before anything else: an order nobody is working cannot be left on the book.
    if track_orders(account):
        return
    if STOP:
        if open_orders(account) is None:
            bevo.status("unreadable")
            return
        finish(account, "you stopped it")
    if "started" not in S and not set_up(account, now):
        return
    market = read_market()
    if market is None:
        if S.get("rest_id") and now - float(S.get("market_at") or now) > STALE_SECONDS:
            cancel_resting()
        bevo.status("unreadable")
        return
    S["market_at"] = now
    work(account, market, now)


if S.get("order") != ORDER_TAG:
    for name in list(S):
        S.pop(name)
    S["order"] = ORDER_TAG

PROBLEM = problem()
if PROBLEM and "started" not in S:
    bevo.notify("%s does nothing until its settings are fixed: %s." % (NAME, PROBLEM))
    bevo.status("paused_settings")

for tick in bevo.ticks():
    if PROBLEM and "started" not in S:
        bevo.status("paused_settings")
        bevo.fail("settings: %s" % PROBLEM)
        continue
    try:
        run()
    except Exception as exc:
        say("run skipped: %s" % exc)
