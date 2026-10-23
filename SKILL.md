---
name: options-trading
description: Trade options on Derive or Paradex - earn on idle USDC by selling cash-secured puts, buy a call or a put, close before expiry, and check or withdraw USDC and positions.
version: 2.6.3
metadata: {"butler":{"moneyMoving":true,"keywords":["yield","earn on my usdc","make my money work","idle cash","options income","cash secured put","sell options","sell a put","premium","get paid to wait","buy the dip","yield note","options","buy a call","buy a put","call option","put option","hedge","protect my eth","upside","bet on eth","close my option","sell my option back","buy back my put","close my note","exit my put","get my collateral back","withdraw","withdraw my usdc","derive","my options","options account","options positions","free usdc","derive positions","my option positions","withdraw from derive","withdraw my free usdc","paradex","paradex options","paradex positions"],"requires":{"bins":["python3","bevo-read","acp"]}}}
---

## When to use

Your owner wants one of four things on Derive's or Paradex's options market:

- **Earn** - "earn on my USDC", "get paid to buy the dip": **sell** one cash-secured
  put, fully collateralised in USDC. They keep the premium and may end up buying the
  asset at the strike (`references/selling.md`).
- **Buy** - "buy an ETH call", "hedge my ETH with a put": **buy** one call or put.
  Not yield: they pay up front and can lose all of it (`references/buying.md`).
- **Close** - before expiry: "sell my call back" **sells back** an option they
  **bought**; "get out of my put", "free my collateral" **buys back** a note they
  **sold**.
- **Look or withdraw** - "my free USDC in Derive" (`freeForNewPutsUsd`, not wallet
  cash), "my positions": step 1, then stop. "Withdraw my free USDC": step 8, never an
  `acp trade` (`references/account.md`).

Not this skill: covered calls, spreads, leverage, or a trade the helper refuses.

## Before you start

1. **Which of the four.** Earning and buying are different promises; never blur them.
   Selling fits only USDC whose owner would happily buy the asset lower; a no to that
   ends selling, every put on it.
2. **Sizes are in the asset.** 1 contract is 1 ETH: 0.16 is 0.16 ETH, and Derive's 0.1
   is only its minimum. Say "0.16 ETH", never "contracts", and never convert.
3. **The bad case first, in their words, before any upside number.** Selling, from
   `bad_case`: *"If ETH falls 25% to $1,844, you pay $2,200: down $44."* Buying: *"If ETH is not
   above $2,664 on 30 October, the $190 is gone."*
4. **First time for that kind of trade:** the plain yes answers in
   `references/selling.md` or `references/buying.md`. A no or a vague answer stops it.
5. **Derive figures come only from this turn's reads:** sizes, prices and positions
   from `acp options account` and quotes, never memory; a note that disagrees is wrong,
   so fix it. `bevo-read assets` has none.
6. **Venue.** Derive, unless they name Paradex or hold it there: then `--venue paradex`
   everywhere (`references/paradex.md`, also for withdrawing).

### Never file without all four

Before any `acp options` deposit, open, buy or close, from the owner's own words in
this chat. One missing: ask, and file nothing this turn.

1. **They chose it.** Asset and amount to open; option and size to close. Never fill
   one in. "You pick", "whatever looks good": Butler does not choose; ask asset,
   amount, expiry.
2. **They hold it.** A close is at most `positions`' size. Asked for more ("sell 5",
   0.16 held): say what they hold and ask. Never shrink it quietly.
3. **They said yes to the number.** The loss, the ownership, or the floor or ceiling,
   with its dollar figure, after the quote. Never your default.
4. **The helper's quote is fresh:** run after their last answer (step 5).

## Procedure

1. [ADAPT] Read the Derive account before answering or filing anything, and the
   wallet only to fund (step 4):

   ```sh
   acp options account
   bevo-read assets
   ```

   `signerReady: false` - stop: the owner must enable Butler's signer first. Fields:
   `references/account.md`. An unreadable account is not an empty one. On
   `exists: true` on either venue, step 9.

2. [FIXED] Write the script in `references/helper.md` to `/tmp/derive_helper.py`.
   Quote with the line for the intent; the strike is a rule, never your number:

   ```sh
   python3 /tmp/derive_helper.py screen --collateral <USD>
   python3 /tmp/derive_helper.py quote --product cash_secured_put --underlying <ASSET> --collateral <USD>
   python3 /tmp/derive_helper.py quote --side buy --product <PRODUCT> --underlying <ASSET> --budget <USD>
   python3 /tmp/derive_helper.py quote --side close --instrument <INSTRUMENT> --size <SIZE>
   python3 /tmp/derive_helper.py quote --side buyback --instrument <INSTRUMENT> --size <SIZE> --premium-received <USD>
   ```

   Selling: the asset they named, or screen (never an APR menu) and ask. Buying:
   `<PRODUCT>` is `call` or `put`, `--budget` the most they will spend. Closing:
   instrument and size from `positions`; positive is `--side close`, negative is `--side buyback` with the size positive and `--premium-received`
   the note's `netPremiumUsd` (or its duty's PREMIUM_USD) scaled to it. **Offer only
   `tradeable: true`**; give the `reasons` as written. Listing: `chain`
   alone; names as given, no company name.

3. [ADAPT] Offer it using **only** quote fields; never compute a number:
   - **Sell:** `bad_case` first, then `net_premium_usd`, `fee_usd`, the lock to
     `expiry`; `apr_pct` last. Then, on its own: *"Happy to own 0.13 ETH at $2,200 on
     30 October?"* A no or a vague answer ends it: no other strike, tenor or asset.
     Butler buys the asset afterwards only if they ask now.
   - **Buy:** not yield; `max_cost_usd` is the most they pay and can lose, all of it;
     `breakeven` is where it pays at expiry. Get an explicit yes to *"you can lose the whole $199.54"*.
   - **Close (sell back):** `net_proceeds_usd` now, against what they paid (the duty's
     PREMIUM_USD); `warnings` as written. Ask the floor; `min_proceeds_usd` is the
     suggestion.
   - **Close (buy back):** `total_cost_usd` now, then `result_usd`: what the note made
     or lost once bought back; `warnings` as written; it frees `frees`. Ask the
     ceiling; `max_cost_usd` is the suggestion. Waiting for expiry costs nothing;
     say so when `result_usd` is negative.

4. [FIXED] With all four met, fund a sell or a buy only when `freeForNewPutsUsd` is below
   `collateral.amount` (sell) or `max_cost_usd` (buy). Deposit the shortfall plus 2% for
   the bridge fee and its 1% slippage bound, rounded up, and **never under $6**. Say
   the bridge fee comes out of the amount:

   ```sh
   acp options deposit --amount <DEPOSIT_USDC> --idempotency-key <KEY>:deposit
   ```

   The bot gathers USDC from **every chain**, not one (`references/venue.md`).
   `--from 1` only when `ethereum.usdc` covers it alone. Never ask about gas or an
   address. Re-read `acp options account` until free USDC covers the trade, and do step
   9; if it ends short, re-quote smaller and re-offer. Free USDC spans their Derive
   accounts: the server moves it (`account.md`).

5. [FIXED] Run the quote again now, after their last answer. With all four met, file
   the one command, with that quote's fields and the bound they agreed:

   ```sh
   acp options open --instrument <instrument> --size <size> --min-premium <min_premium_usd> --max-collateral <collateral.amount> --idempotency-key <KEY>:open
   acp options buy --instrument <instrument> --size <size> --max-cost <max_cost_usd> --idempotency-key <KEY>:buy
   acp options close --instrument <instrument> --size <size> --min-proceeds <AGREED_FLOOR> --idempotency-key <KEY>:close
   acp options close --instrument <instrument> --size <size> --max-cost <AGREED_CEILING> --idempotency-key <KEY>:close
   ```

   One bound per close. The reply is an approval card, not a fill: tell the owner to
   approve it in the app.

6. [FIXED] Wait for the outcome; never re-run the command to find it. The server nudges
   you here when the card lands. Then:

   ```sh
   bevo-read request <KEY>:<OP> --route options
   ```

   `approvalStatus: confirmed` - `approvalOutcome` holds the fill, maybe partial:
   `filledSize`, plus open `netPremiumUsd`, `collateral`; buy `totalCostUsd`; close
   `direction`, `netProceedsUsd` or `totalCostUsd`; `funding`: USDC moved first, say so.
   `failed` or `rejected` - nothing traded;
   give `approvalFailureReason` as written. `pending` or `signed` - still waiting.

7. [FIXED] Only on `confirmed`, keep the lifecycle duty in step, numbers from
   `approvalOutcome`, never the quote. After an open or a buy, `duty_create`:

   ```json
   {"recipe": "options-lifecycle@8", "title": "Watch {INSTRUMENT} to expiry",
    "triggers": [{"kind": "timer", "intervalSeconds": 900}],
    "params": {"VENUE": "<venue>", "INSTRUMENT": "<instrument>", "PRODUCT": "<product>", "UNDERLYING": "<prefix>",
    "STRIKE": <strike>, "SIZE": <filledSize>, "PREMIUM_USD": <usd>, "COLLATERAL_USD": <usd>}}
   ```

   Sold put: PRODUCT `cash_secured_put`, PREMIUM_USD `netPremiumUsd`, COLLATERAL_USD
   `collateral`. Bought: PRODUCT `long_call` or `long_put`, PREMIUM_USD `totalCostUsd`,
   COLLATERAL_USD 0. Always SIZE `filledSize`, STRIKE `strike`, UNDERLYING the
   instrument's prefix. `DELIVER_ASSET` and its TOKEN_ID only if they asked in step 3
   (`references/selling.md`). After a close, `duty_delete` that instrument's duty; if
   part is still open, file it again with SIZE from `positions` (positive) and
   PREMIUM_USD and COLLATERAL_USD scaled to it. Never file for an unknown or failed
   trade. A second `options-lifecycle` duty in
   one chat needs `"alongside": [<this chat's earlier ones' names>]`; step 9's needs
   none.

8. [FIXED] Withdraw only when asked, only free USDC: at most this turn's
   `freeForNewPutsUsd`, rounded down to the cent. It lands on Ethereum in about 20
   minutes, less up to $1 (say so first); `:home` brings it to Base once it shows in
   `ethereum.usdc`:

   ```sh
   acp options withdraw --amount <USDC> --idempotency-key <KEY>:withdraw
   acp trade --token-in usdc --chain-in 1 --amount-in <USDC_ARRIVED> --token-out usdc --chain-out 8453 --idempotency-key <KEY>:home
   ```

9. [FIXED] As long as an account exists on any venue and `duty_list` has no
   `options-account` duty, file it, unasked, then delete any `derive-account` duty:

   ```json
   {"recipe": "options-account@1", "title": "Options accounts", "triggers": [{"kind": "timer", "intervalSeconds": 600}]}
   ```

   It alone writes every venue's Platforms row: no watcher or `bevo-platforms set` of yours.

## Idempotency and retries

Derive one key per trade, such as `ot:eth:20261030:2600c:1`, with `:deposit`,
`:open`, `:buy`, `:close`, `:withdraw`, `:home`. On an error, a timeout or an unclear
answer, **do not re-run** the command - a retried buy can buy twice, a retried
deposit can bridge twice. Look it up as in step 6: `not_found` means nothing was filed
under that key. A deposit still crediting is not a failed one: re-read `acp options
account` and wait. The `:home` leg is `acp trade`: look it up with `--route trade`.

## Failure handling

| Outcome | What to do |
| --- | --- |
| Nothing `tradeable` | Say nothing is worth doing today and why. Never loosen a gate. |
| `no live bid` / `no live ask` | Opening: another strike, expiry or asset, or stop. Closing: nobody bids for theirs now; holding costs nothing. |
| `vol points wide`, `paying N% over fair value` | A poor price; say so, never trade it. |
| `fees are N% of the premium` | Too small or too short. Offer monthly or bigger. |
| `collateral too small`, `budget too small` | Under Derive's minimum. Give the figure from the reason. |
| An `OPTIONS_*` refusal | Nothing filed: follow its hint; never raise a bound the owner agreed. |
| No fill (open, buy or close) | Nobody took it at the agreed bound; never call it no liquidity. Nothing moved. Re-quote, re-ask, never re-file the same bound. |
| Buy failed over `--max-cost` | Give the reason as written, then read `positions`: anything shown there was bought. Never buy again. |
| Deposit refused, failed or partial | Give the reason as written; re-read the account before any new deposit. Never move funds between chains to fix it. |
| Withdraw or `:home` failed | Give the reason as written, and stop (`only $N is free`: the rest backs sold puts). |
| Card swept after 30 minutes | Unsigned; re-quote before offering again. |

## Limits

- Selling locks collateral until expiry or a buy-back; buying is paid in full, nothing
  borrowed. No rolling without a fresh yes.
- **Monthly by default**; weeklies lose too much to fees and the spread.
- **Cash settled** in USDC, never the asset; it stays on the venue until withdrawn.
- Not advice: never rank or recommend.

## Say to the owner

Worked sentences end each file in `references/`.
