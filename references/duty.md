# A duty that trades options

The `options-lifecycle`, `options-put-delivery` and `options-account` duties only watch
and report (SKILL.md steps 7 and 9). This file is for any trade the owner wants to happen
later, without them in the chat: set off by a condition (a price, a move, any signal), at
a set time, or on a schedule, once or again and again. That is a duty whose own code
trades, never a trade filed from chat now.

When it is asked, check the condition (the price, the day). A price is the helper's
`spot` (`quote.py minimum --underlying <ASSET>`), never a token search; unread, say so and
ask whether it is already true, never assume it is not. Not met: a duty. Already met:
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
and any quote. A reply with only the rule's questions is not this reply, and neither is
one that only asks what they meant (sell or buy, now or on that date): the three come
first, that question after them, in the same reply. Per-venue minimums never stand in
for the set-aside question. When their
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

Never type the duty's program or its `duty_create` fields yourself: `scripts/make_duty.py`
builds both from `scripts/duty_program.py`, the one program every such duty runs. You
write only the rule, then run it.

1. **The rule.** Save one file, `~/duties/<name>/rule.py`, with two functions (below).
2. **Its own wallet only:** `bevo-wallet create --chain ethereum --label <name>`: an
   empty wallet.
3. **Build it:**

   ```sh
   python3 ~/skills/options-trading/scripts/make_duty.py --name '<TITLE>' --spec '<THEIR ASK>' \
     --wallet own --wallet-label <name> --set-aside <USD> --need <USD> --times <N> \
     --venue derive --every 300 --rule ~/duties/<name>/rule.py --param STRIKE=1500
   ```

   - `--name`: its title, what it does and when, at most 38 characters, no chain, size or
     count: "ETH calls every 30 min", "Sell ETH puts below $1,500". It and `--spec` go in
     single quotes: in double quotes the shell eats `$1,500`.
   - `--set-aside`: **the amount they set aside**, never one trade's need. `--need`: what
     one trade needs, as in the first reply. `--times`: how many trades, then it stops.
   - `--every`: 60 for a set time, 300 for a price or a schedule. It runs from the moment
     it is filed; the time, day or price is in `trigger()`, and the runs before it are
     when its money reaches the venue.
   - `--param KEY=VALUE`: each of the rule's figures, read from `P` in the rule, never
     written into it.
   - When they gave one: `--end-at YYYY-MM-DD` (no new trade from that day). Its own
     wallet only: `--max-loss <USD>` (no new trade once that much of what it deposited is
     gone, counted with nothing open and still gone six hours later, trading nothing while
     it checks) and `--withdraw-on-finish`, so at the end it sends everything back to the
     main wallet itself.
   - **The main wallet:** `--wallet main --free <freeForNewPutsUsd>` from this turn's
     `acp options account`, and no `--wallet-label`; `--card-each-trade` only when they
     asked for a card on every trade.
4. **Do what it prints:**
   - `duty_create`: pass that object to the `duty_create` tool exactly as printed. It
     names the saved program by `codePath`; never send `code`, never change a field.
     Then say its `say` line: one funding card (its own wallet: the amount set aside plus
     2%, moved to the duty's wallet on Base, then deposited by the duty), or one Start
     card proposing the amount set aside as its limit (the main wallet). Never ask them
     for a limit in chat: they named it.
   - `deposit_first` (the main wallet, short on the venue): deposit that amount as
     SKILL.md step 4 does (`--venue` for Paradex), ask the owner to approve its card, and
     file nothing more in that turn. Once `acp options account` shows it free, build
     again with the new `--free`.
   - `error: …`: nothing was built; fix what it names. Under $10 set aside, its own
     wallet cannot deposit: recommend the main wallet.

Nothing is filed to watch what it trades: SKILL.md step 9's `options-lifecycle` duty
watches every option held, in a duty's own wallet too.

## The rule

`rule.py` is plain Python, put into the program as written. It may read `P` (the
`--param` settings), `S` (state kept between runs), `time`, `bevo.read`, and `quote()`,
which runs the helper (`helper.md`) with the same arguments and returns its JSON, or
`{"error": why}`. It never sends a note, writes a status, runs `acp`, or adds a key: the
program does all four.

- `trigger()` returns `(True, "ETH at $1,480")` to trade now, else
  `(False, "ETH at $1,790")`: what it saw, said as the owner would read it. A price is
  `quote("minimum", "--underlying", "ETH").get("spot")`; unread, return
  `(False, "ETH unread")`.
- `order()` prices the trade now with `quote("quote", ...)` and returns
  `(argv, "a line saying it")`, the argv being what follows `acp options`, without a key:
  `["open", "--instrument", i, "--size", s, "--min-premium", p, "--max-collateral", c]`
  for a sold put, `["buy", "--instrument", i, "--size", s, "--max-cost", m]` for a buy.
  `(None, why)` when the quote failed, is not `tradeable`, or raises a safeguard.

```python
STRIKE = float(P["STRIKE"])
SIZE = float(P["SIZE"])


def trigger():
    spot = quote("minimum", "--underlying", "ETH").get("spot")
    if spot is None:
        return False, "ETH unread"
    return spot < STRIKE, f"ETH at ${spot:,.0f}"


def order():
    q = quote("quote", "--product", "cash_secured_put", "--underlying", "ETH",
              "--collateral", f"{STRIKE * SIZE:g}", "--strike", f"{STRIKE:g}")
    if q.get("error"):
        return None, f"the quote failed ({q['error']})"
    if not q.get("tradeable") or q.get("waivable"):
        return None, "the quote is not tradeable now"
    return (["open", "--instrument", q["instrument"], "--size", f"{q['size']:g}",
             "--min-premium", f"{q['min_premium_usd']:g}",
             "--max-collateral", f"{q['collateral']['amount']:g}"],
            f"sell a {q['size']:g} ETH ${STRIKE:,.0f} put for at least ${q['min_premium_usd']}")
```

A time or a schedule compares timestamps, never the clock's hour or weekday (the agent
refuses that under this timer), and reads `S.get("traded_at", 0)`, when the program last
traded: it is set on a fill, never on a miss, so a run a minute later does not trade
again while a missed order is still retried. A set time is one epoch in a `--param`
(`time.time() >= AT`, and `S.get("traded_at", 0) < AT`). A schedule counts from an anchor:

```python
WEEK = 7 * 86400
ANCHOR = 4 * 86400 + 9 * 3600  # a Monday 09:00 UTC (5 January 1970)


def trigger():
    due = ANCHOR + (time.time() - ANCHOR) // WEEK * WEEK  # this week's Monday 09:00 UTC
    if S.get("traded_at", 0) >= due or time.time() - due > 6 * 3600:
        return False, "next sale Monday 09:00 UTC"
    return True, "Monday 09:00 UTC"
```

`make_duty.py` refuses a rule whose `order()` leaves out the quote's bound
(`--min-premium` and `--max-collateral` on a sale, `--max-cost` on a buy), or whose
`trigger()` answers anything but `(True or False, "a line")`.

## What the program does

The same for every duty, and why none of it is yours to write:

- **Set up** (its own wallet): whatever USDC lands in its wallet (the funding card, a
  top-up) it deposits on the venue, and trades nothing in that run. Once it is there it
  says it is ready, and only then reads the trigger. A wallet still empty after 30
  minutes (a funding card declined or left waiting) is said once, with a push. A
  main-wallet duty's money was deposited in chat.
- **Short** is checked on every run once it is ready, before the trigger matters: the
  owner hears it while there is still time to top up, and again if it fires while short.
  It never deposits on its own past setting up.
- **One key per order**, from the trade's count, never a timestamp: a re-fire reuses it
  and the server never runs it twice. An order whose end is unclear is counted and never
  sent again.
- **One note per trouble.** While its trigger holds it tries again every five minutes,
  and says each kind of trouble once: an order nobody took, a trade the server held back
  (a Start card or an earlier card still waiting, a limit used up, each named as such),
  a quote that failed three times running. Repeats go to its log and its status line; a
  fill, or the trigger passing, clears them.
- **Its limit:** `--times` trades, then it stops itself.

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

A duty built with `--withdraw-on-finish` (auto-roll always is) stops itself cleanly:
`duty_update` its params with `"STOP": true` added, every other setting unchanged. It
makes no new trade and waits until nothing ties money to the venue (no position, no
locked collateral, no fill or deposit still landing). Then it withdraws everything free
(a cent under the figure read, less again only after "only $N is free"), waits for that
to reach its wallet (24 hours at most), sends everything back to the main wallet
(`bevo-wallet withdraw`) and finishes, saying what went home. Money that lands on the
venue before then is withdrawn too. Never turn it off or delete it to stop it: its money
would stay in its wallet.

Without it, deleting a duty is refused (409 `duty_venue_not_empty`) while its own
wallet's venue account holds money or a position. Have the duty cancel its resting
orders, close or let settle what it holds, and withdraw (`duty_update` its code with that
step if it has none), then delete. A withdrawal lands in the duty's wallet on Ethereum
(Derive) or Arbitrum (Paradex), less the venue's fee.

## Auto-roll

A put sold every week from its own wallet, the next one as soon as the last settles, until
an end date, a loss limit or the owner says stop: "auto-roll", "sell a put every week",
"keep rolling my puts". Cash only: below the strike they pay the difference in cash, and it
never buys the asset. Its rule is built in (`--preset auto-roll`); write no `rule.py`.

1. **First reply**, as above, with two answers fixed: **its own wallet** (auto-roll runs
   from its own wallet only, so the main wallet is not offered) and **Derive**. Ask how
   much to set aside; one put needs at least `min_collateral_usd` from
   `quote.py minimum --underlying <ASSET> --tenor weekly`.
2. **Second reply, once the wallet and amount are confirmed:** quote the first put with
   the duty's own rule, then make the offer, each line its own paragraph:

   ```sh
   python3 ~/skills/options-trading/scripts/quote.py quote --product cash_secured_put --underlying <ASSET> --collateral <SET_ASIDE> --tenor weekly --otm-pct 8 --max-delta 0.15
   ```

   > Best first trade for your $5,000: sell the ETH $1,500 put, expiring 4 Dec. Estimated yield: 33% a year.
   >
   > If ETH ends below $1,500, you pay the difference in cash. At $1,400, that's about $333, less the $51 premium you keep.
   >
   > After that, I'll roll it weekly with what's left, targeting about 30% a year, until 23 Feb or if losses pass $500.
   >
   > You can stop me anytime.
   >
   > Start?

   Strike, expiry and yield are the quote's (`apr_pct`); the premium kept is
   `net_premium_usd`; the cash example is (strike minus a price about 7% under it) x
   `size`. The target is `apr_pct` rounded down to a 5: an estimate the rule never
   chases by selling nearer the price. End date and loss limit are theirs; unnamed,
   offer 13 weeks and 10% of the amount set aside. Say the bad case if they ask what a
   crash costs: `bad_case`.
3. **On yes:** `bevo-wallet create --chain ethereum --label <name>`, then build it and do
   what it prints (Filing it, step 4: one funding card, the amount set aside plus 2%):

   ```sh
   python3 ~/skills/options-trading/scripts/make_duty.py --name 'Weekly ETH puts' --spec '<THEIR ASK>' \
     --preset auto-roll --wallet own --wallet-label <name> --set-aside <USD> --need <min_collateral_usd> \
     --end-at <YYYY-MM-DD> --max-loss <USD> --param UNDERLYING=ETH
   ```

   `--end-at` and `--max-loss` are required; it sells a put a week to the end date (and
   one more), so no `--times`. Derive only, every 300 seconds: no `--venue` or `--every`.

What it does every five minutes: once nothing is open and the last put has settled (no
collateral locked, 20 minutes past its 08:00 UTC expiry), or none was sold yet, it quotes
this week's put by the same rule (the strike nearest spot at least 8% under it with a delta
of 0.15 or less and a bid; the expiry nearest 9 days out, a Friday), sized to all its free
USDC, and sells it at the quote's bound. While a put is open its locked collateral is not
short. `options-lifecycle` gives each put's heads-up and outcome. At the end date, the loss
limit or `STOP` it finishes as Stopping it says. Change `MIN_BELOW_PCT` or `MAX_DELTA`
only when the owner asks.

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
