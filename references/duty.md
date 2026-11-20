# A duty that trades options

The `options-lifecycle`, `options-put-delivery` and `options-account` duties only watch
and report (SKILL.md steps 7 and 9). This file is for any trade the owner wants to happen
later, without them in the chat: set off by a condition (a price, a move, any signal), at
a set time, or on a schedule, once or again and again. That is a duty whose own code
trades, never a trade filed from chat now.

When it is asked, check the condition (the price, the day). Not met: a duty. Already met:
say so, and ask whether they want the trade now (SKILL.md's steps) or the duty for the
next time; file nothing until they answer. Unsure whether they mean now or later (a date
that may be the expiry or the day to trade): ask which, in the reply below.

The rule is the owner's: the asset, what sets it off, the strike and expiry rule, the size
of each trade, its floor or ceiling, and how many times it may trade. Never fill one in;
ask. Say the bad case as for one trade (`selling.md`, `buying.md`), and how it will ask
before trading, or that it won't.

A new ask is a new duty, filed as this file says. In that turn, never open, check, edit or
fix the owner's other duties, orders or cards, even a failing one or a card still waiting,
and never copy how an earlier duty was filed. When one bears on the money (a waiting card
holds part of the free USDC), say so in one line; touch it only when they ask.

## Your first reply

Never file a duty in the turn it is asked, even when the ask names the time, the venue
and the money, and free USDC already covers it: the wallet is the owner's to pick, so
this reply recommends one and waits for their answer.

When they named the money (a budget, the collateral, a size), this reply comes before any
tool call after reading this file, but the one read a condition needs (its price now):
that figure is one trade's need, and the quote waits for filing. Without one, read only
what the floor needs (one quote) and reply.

A duty's money is on the venue before it can trade: a Derive or Paradex deposit takes
minutes, and the price that set it off may be gone by then. So the first reply settles
the money. It opens with these three, numbered, in this order, before any quote, table
or question about the rule, every time, even when the reply also has to clear up the
rule:

1. **The wallet, as your recommendation:** "I recommend **its own wallet**, because …"
   (or **your main wallet**), with one reason from this chat (the table below). Then the
   other in one line, and that they can pick it instead: "Or your main wallet, to use
   the USDC already in your options account, with one approval for its limit."
2. **How much to set aside for it, in total,** asked in these words: "How much do you
   want to set aside for this duty in total?" One dollar figure the duty works with for
   every trade it makes; never "per put" or "per trade" in its place (each trade's size
   is one of the rule's questions), and never "it depends": they answer it with a
   dollar figure. Give the floor after it: "one trade needs about $X"
   (a sold put's `strike x size`, a buy's most it costs), and "N at once need about
   $N·X" when it repeats.
3. **Which venue:** Derive, unless they name Paradex or already hold it there. Rysk
   trades only from chat (`OPTIONS_VENUE_NOT_DUTY`).

Then the rule's own questions (strike, size, how many times, now or later), the bad case,
and any quote. A reply with only the rule's questions is not this reply. When their
answer already gives a figure or a wallet, confirm it in place of asking.

### Which wallet to recommend

| | Its own wallet | The main wallet |
| --- | --- | --- |
| Trades | Hands-free, no card | Hands-free up to the limit on its Start card, once held |
| Deposits | The duty makes them, hands-free | A card now, in chat; each top-up a card |
| Its money | Its own account and Platforms row, apart from the owner's | The owner's main account |
| Copyable | Yes | No: its trades are never copied |

Recommend **its own wallet** for anything that runs unattended, repeats, waits for a
price, or may be published or copied: the reason is that it trades the moment it fires,
with no card to miss. Recommend **the main wallet** to trade free USDC already in their
main options account (`acp options account`), or when they want a card for every trade.
Either is a recommendation, asked in the first reply. Their pick stands; never argue it
twice.

## Filing it

### Its own wallet

1. `bevo-wallet create --chain ethereum --label <duty name>`: an empty wallet.
2. `duty_create` with `"walletId": "<that label>"`, `"fundUsdc"`: **the amount they set
   aside** (never one trade's collateral in its place), plus 2% for the bridge fee and its
   slippage bound, rounded up to the dollar: $10 is 11, $15 is 16, $100 is 102. Add
   nothing else, no headroom of your own: whatever is left stays idle in that wallet.
   `ALLOCATION_USD` is the amount they set aside. Its own wallet needs at least $10 set
   aside, the venue's minimum deposit; under that, recommend the main wallet. No
   `fundUsdc` is refused (`fund_amount_required`). One funding card moves it from the
   main wallet to the duty's wallet on Base; nothing moves until the owner approves it.
   Say so.
3. The duty sets itself up (below) and tells the owner once its money is on the venue.

### The main wallet

1. When free USDC there (`acp options account`) is short of the amount set aside,
   deposit the gap now, as SKILL.md step 4 does (`--venue` for Paradex): ask the owner to
   approve the deposit card, and file nothing more in that turn. When it already covers
   it, go on to 2 in this turn.
2. Once it shows free, `duty_create` with no `walletId` and `"pocketUsdc"`: **the amount
   they set aside**. That files one Start card proposing that limit; the owner's hold is
   the approval. Never ask them for a limit in chat: they named it. Say that once they
   hold it, each trade it covers runs with no card; until then a trade it covers is
   skipped, and a bigger one asks with its own card. Only when they asked for a card on
   every trade: `"pocketUsdc": 0`.

### What `duty_create` gets, either way

Besides `walletId` and `fundUsdc`, or `pocketUsdc`, these fields, as written, so it files
the first time:

```json
{
  "name": "<a slug>",
  "spec": "<the owner's ask, in their words>",
  "title": "{NAME}",
  "movesFunds": true,
  "triggers": [{"kind": "timer", "intervalSeconds": 60, "untilDone": true}],
  "spendBasis": {"perTrade": "NEED_USD", "times": "TIMES"},
  "statusTemplate": {
    "moving": "Moving ${amount} to {venue}",
    "setting_up": "Setting up: ${free} of ${allocation} on {venue}",
    "unfunded": "Waiting for its funding card",
    "watching": "{seen} · ${free} free on {venue}",
    "short": "${gap} short on {venue} · top it up to trade",
    "placed": "Placed: {order} · waiting on {venue}",
    "retrying": "{seen} · not placed yet, trying again",
    "unreadable": "Couldn't read the options account · retrying"
  },
  "params": {"NAME": "...", "VENUE": "derive", "OWN_WALLET": true, "ALLOCATION_USD": 0,
             "NEED_USD": 0, "TIMES": 1, "QUOTE_PY": "...", "...": "the rule's figures"},
  "code": "<the program below, filled in>"
}
```

- `NAME`: what it does and when, at most 38 characters, no chain, size or count: "ETH
  calls every 30 min", "Sell ETH puts below $1,500". The title is `{NAME}` alone.
- `intervalSeconds`: 60 for a set time, 300 for a price or a schedule. It runs from the
  moment it is filed, never a `startsAt` or an `at`, even for a set time: the time, day
  or price is in `trigger()`, and the runs before it are when its money reaches the venue.
- `OWN_WALLET`: true for its own wallet, false for the main one. `ALLOCATION_USD`: the
  amount set aside. `NEED_USD`: one trade's need, as in the first reply. `TIMES`: how
  many trades.
- `QUOTE_PY`: the helper's full path, read in chat with
  `realpath ~/skills/options-trading/scripts/quote.py`: a duty runs in its own folder,
  where `~/skills` is not this skill and `python3` is not on its path.
- The rule's own figures go in `params` too, each read from `P` in `trigger()` or
  `order()`, never written into the code.

It gets no `options-lifecycle` duty: it follows its own trades.

## Its code

Start from this program, for either wallet. Write only `trigger()` and `order()`; keep
every other line as written, its notes' words and pushes too, since each is a promise to
the owner: its money is on the venue before it watches, it never deposits when it fires,
it warns (with a push) when it is short of the next trade, and it says when it fired and
how that ended. Never write a duty that trades options any other way.

```python
import json, math, os, subprocess, sys, time
import bevo

P = json.loads(os.environ.get("PARAMS") or "{}")
NAME = P["NAME"]
VENUE = str(P.get("VENUE") or "derive").lower()
OWN = bool(P.get("OWN_WALLET"))
ALLOCATION = float(P["ALLOCATION_USD"])
NEED = float(P["NEED_USD"])
TIMES = int(P.get("TIMES", 1))
QUOTE_PY = P["QUOTE_PY"]
Q = {} if VENUE == "derive" else {"venue": VENUE}
FROM = ["--from", "8453"] if VENUE == "derive" else ["--venue", VENUE]
WHERE = VENUE.title()
S = bevo.state


HELD = {"pocket_pending": "is waiting for you to hold its Start card",
        "pocket_empty": "has used up its limit; raise it and it carries on",
        "OPTIONS_DUTY_CARD_PENDING": "is waiting for you to answer its last card"}


def acp(key, *args):
    """Runs it; returns which of HELD refused it, or ""."""
    run = subprocess.run(["acp", "options", *args, "--idempotency-key", key],
                         capture_output=True, text=True, timeout=170, check=False)
    return next((code for code in HELD if code in run.stdout + run.stderr), "")


def say(kind, text, push):
    """One note per kind of trouble until it clears; a repeat goes to the log only."""
    if kind in S.get("said", []):
        bevo.log(text)
        return
    S["said"] = S.get("said", []) + [kind]
    bevo.notify(text, push=push)


def quote(*args):
    """The helper (helper.md), e.g. quote("quote", "--side", "buy", ...): its JSON, or
    {"error": why} when it failed."""
    try:
        run = subprocess.run([sys.executable, QUOTE_PY, *args], capture_output=True,
                             text=True, timeout=120, check=False)
        if run.returncode == 0:
            return json.loads(run.stdout)
        return {"error": (run.stderr or "no answer").strip()[-200:]}
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)[:200]}


def free_on_venue():
    """Its free USDC there: 0 before its first deposit, None when unread."""
    try:
        account = (bevo.read("/options/account", Q) or {}).get("account")
    except bevo.BevoError:
        return None
    if not isinstance(account, dict):
        return None
    return float(account.get("freeForNewPutsUsd") or 0) if account.get("exists") else 0.0


def trigger():
    """The owner's rule. (True, "ETH at $1,480") to trade now, else (False, "ETH at $1,790").
    A repeat keeps in S when it last traded, so one trigger trades once."""


def order():
    """The trade, quoted now with quote(), never another path to the helper: (argv after
    `acp options`, a line saying it), e.g. (["open", "--instrument", i, "--size", s,
    "--min-premium", p, "--max-collateral", c], "sell a 0.5 ETH $1,500 put for at least
    $41"); a buy is ["buy", ..., "--max-cost", m]. (None, why) when the quote failed or
    is not tradeable. By RFQ, only when the owner asked for it: the same argv and bound
    with "--order", "rfq" added."""


def move_in(free):
    """Its own wallet's USDC onto the venue. True when it deposited: that run trades nothing."""
    if not OWN or time.time() - S.get("deposit_at", 0) < 600:
        return False
    cash = bevo.balance().cash_usd
    if cash is None or cash < 10:
        return False
    n = S.get("deposits", 0)
    acp(bevo.key("deposit", bevo.SERVICE_ID, n), "deposit", "--amount", str(int(cash)), *FROM)
    S["deposits"], S["deposit_at"], S["free_before"] = n + 1, time.time(), free
    bevo.status("moving", amount=int(cash), venue=WHERE)
    return True


def short(free, met, seen):
    """Short of the next trade: tell the owner once per balance, and once per missed fire."""
    gap = math.ceil(NEED - free)
    ask = max(gap, 10) if OWN else gap  # its wallet moves nothing to the venue under $10
    if S.get("low_at") != round(free):
        S["low_at"] = round(free)
        bevo.notify(f"{NAME}: ${free:,.0f} free on {WHERE}; its next trade needs ${NEED:,.0f}. "
                    f"Top it up by ${ask:,} and it carries on.", push=f"{NAME} is ${gap:,} short")
    if met and not S.get("missed"):
        S["missed"] = True
        bevo.notify(f"{NAME}: {seen}, but it is ${gap:,} short on {WHERE}, so nothing traded. "
                    f"Top it up and it trades the next time.", push=f"{NAME} fired, short ${gap:,}")
    bevo.status("short", gap=gap, venue=WHERE)


def follow_up():
    """How a placed order ended, told once. True while it is still running."""
    key = S.get("key")
    if not key:
        return False
    fate = bevo.settled(key, route="options", wait=60)
    if fate in ("waiting", "approval"):
        bevo.status("placed", order=S.get("placing") or "the order", venue=WHERE)
        return True
    line = S.pop("placing", "the order")
    del S["key"]
    held = HELD.get(S.pop("refused", ""))
    if fate == "dropped" or held:  # a held-back trade never ran, whatever the ledger says
        S["tries"], S["retry_at"] = S.get("tries", 0) + 1, time.time() + 300
        if held:
            say("held", f"{NAME}: {line} was not placed: it {held}. Nothing traded.",
                f"{NAME} needs you")
        else:
            say("missed", f"{NAME}: {line} did not fill at its bound; nothing traded. It "
                f"keeps trying while its trigger holds.", f"{NAME}: not filled")
        return False
    S.pop("said", None)
    S["done"] = S.get("done", 0) + 1
    if fate == "executed":
        bevo.notify(f"{NAME}: done, {line}. Trade {S['done']} of {TIMES}.", push=f"{NAME}: filled")
    else:
        bevo.notify(f"{NAME}: {line} may have gone through; your options account on {WHERE} "
                    f"says for sure. It is counted, never sent again.", push=f"{NAME}: unclear")
    return False


for tick in bevo.ticks():
    if follow_up():
        continue
    if S.get("done", 0) >= TIMES:
        bevo.done(f"{NAME}: all {TIMES} trade(s) made.")
    free = free_on_venue()
    if free is None:
        bevo.status("unreadable")
        continue
    if move_in(free):
        continue
    arriving = OWN and (not S.get("deposits") or (free <= S["free_before"] + 1
                                                   and time.time() - S["deposit_at"] < 1800))
    if free < NEED and arriving:
        if S.get("deposits") or time.time() - S.setdefault("born", time.time()) < 1800:
            bevo.status("setting_up", free=round(free), allocation=round(ALLOCATION), venue=WHERE)
            continue
        if not S.get("unfunded"):  # funding card declined or never answered
            S["unfunded"] = True
            bevo.notify(f"{NAME}: its wallet is still empty, so it has not started. Approve "
                        f"its funding card, or ask Butler to fund it.",
                        push=f"{NAME} is not funded")
        bevo.status("unfunded")
        continue
    if not S.get("ready") and free >= NEED:
        S["ready"] = True
        bevo.notify(f"{NAME}: ${free:,.0f} ready on {WHERE}. Watching now.",
                    push=f"{NAME} is ready")
    met, seen = trigger()
    if free < NEED:
        short(free, met, seen)
        continue
    S.pop("low_at", None)
    S.pop("missed", None)
    if not met:
        S.pop("said", None)
        S.pop("noquote", None)
        bevo.status("watching", seen=seen, free=round(free), venue=WHERE)
        continue
    if time.time() < S.get("retry_at", 0):  # five minutes between tries
        bevo.status("retrying", seen=seen)
        continue
    argv, line = order()
    if not argv:
        S["noquote"], S["retry_at"] = S.get("noquote", 0) + 1, time.time() + 300
        if S["noquote"] >= 3:  # a blip is logged; a quote still failing is told once
            say("noquote", f"{NAME}: {seen}, but {line}; nothing traded. It keeps trying.",
                f"{NAME} cannot quote")
        else:
            bevo.log(f"{seen}, but {line}")
        bevo.status("retrying", seen=seen)
        continue
    S.pop("noquote", None)
    key = bevo.key("trade", bevo.SERVICE_ID, S.get("done", 0), S.get("tries", 0))
    say("fired", f"{NAME}: {seen}. Placing: {line}.", f"{NAME} fired")
    S["refused"] = acp(key, *argv)
    S["key"], S["placing"] = key, line
    follow_up()
```

What each part keeps:

- **Set up** (its own wallet): whatever USDC lands in its wallet (the funding card, a
  top-up) it deposits on the venue, and trades nothing in that run. Once it is there it
  says `ready`, and only then reads the trigger. A wallet still empty after 30 minutes
  (a funding card declined or left waiting) is said once, with a push. A main-wallet
  duty's money was deposited in chat.
- **Short** is checked on every run once it is ready, before the trigger matters: the
  owner hears it while there is still time to top up, and again if it fires while short.
  It never deposits on its own past setting up.
- **One key per order**, from `bevo.key` with the trade's count, never a timestamp: a
  re-fire reuses it and the server never runs it twice. `bevo.settled` reads how it
  ended; never send it again under a new key.
- **One note per trouble.** While its trigger holds it tries again every five minutes,
  and says each kind of trouble once: an order nobody took, a trade the server held back
  (a Start card or an earlier card still waiting, a limit used up, each named as such),
  a quote that failed three times running. Repeats go to its log and its status line; a
  fill, or the trigger passing, clears them.
- **Its limit:** `TIMES` trades, then `bevo.done`.

## By RFQ

Only when the owner asked for it (`rfq.md`), on Derive or Paradex, from either wallet:
`order()` adds `"--order", "rfq"` to the same argv, with the same bound. Makers have 20
seconds; when none quotes inside the bound nothing trades (`OPTIONS_NOT_FILLED`), and the
duty tries again on its next trigger. Say first that makers may not quote a small size
(`rfq.md`), and offer the order book for it.

## Topping it up

On a short note, in chat: say what it is short and ask if they want to top it up, and by
how much. Nothing moves without their yes.

- **Its own wallet:** `bevo-wallet fund --wallet "<label>" --amount <usd>`, at least $10
  (the venue's minimum deposit: less stays in the wallet and never reaches the venue), one
  card from the main wallet; the duty moves it to the venue on its next run.
- **The main wallet:** deposit as SKILL.md step 4; raise the pocket only if they ask.

## What comes back

| Answer | What to do |
| --- | --- |
| `executed` | It ran; the fields are under `outcome`. A resting order is placed, not filled; read `acp options account`. |
| `refused` | Nothing moved. `OPTIONS_NOT_FILLED`: nobody took it at the bound. `OPTIONS_BUSY`: send the same command, same key, on a later run. |
| `unknown` | It may have moved. Read `acp options account` before anything else; never retry blind. |
| 403 `OPTIONS_DUTY_OFF` | Options from duties are off on this server. Tell the owner and stop. |
| 403 `OPTIONS_DUTY_NO_WALLET` | It holds wallets, none on EVM. Bind an empty EVM one as in filing, step 1 and 2. |
| 409 `OPTIONS_DUTY_PAUSED` | Paused, or its funding card still waits. Wait for the owner. |
| 409 `OPTIONS_DUTY_CARD_PENDING` | A main-wallet duty's last card still waits; one at a time. |
| 402 `pocket_empty`, `pocket_pending` | A main-wallet duty's pocket cannot cover it, or its card waits. |

## Stopping it

Deleting a duty is refused (409 `duty_venue_not_empty`) while its own wallet's venue
account holds money or a position. Have the duty cancel its resting orders, close or let
settle what it holds, and withdraw (`duty_update` its code with that step if it has
none), then delete. A withdrawal lands in the duty's wallet on Ethereum (Derive) or
Arbitrum (Paradex), less the venue's fee.

## Say to the owner

First reply: "I can set that up as a duty that trades by itself when ETH drops below
$1,500. Three things first:
1. **Wallet:** I recommend its own wallet, because it then sells the moment ETH crosses,
   with no card for you to approve in time. Or your main wallet, to use the USDC already
   in your options account, with one approval for its limit.
2. **How much do you want to set aside for this duty in total?** One 0.5 ETH put at
   $1,500 needs about $750.
3. **Venue:** Derive, unless you'd like Paradex.
And for the put itself: which strike, what size, and once or each time it drops?"

Short: "Your ETH put duty has $400 free on Derive; its next put needs $750. Want to top
it up by $350?"
