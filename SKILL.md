---
name: options-trading
description: Trade options on Derive - earn on idle USDC by selling cash-secured puts, or buy a call or a put for upside or a hedge, and close either before expiry.
version: 2.1.1
metadata: {"butler":{"moneyMoving":true,"keywords":["yield","earn on my usdc","make my money work","idle cash","options income","cash secured put","sell options","sell a put","premium","get paid to wait","buy the dip","yield note","options","buy a call","buy a put","call option","put option","hedge","protect my eth","upside","bet on eth","close my option","sell my option back","buy back my put","close my note","exit my put","get my collateral back"],"requires":{"bins":["python3","bevo-read","acp"]}}}
---

## When to use

Your owner wants one of three things on Derive's options market:

- **Earn** - "earn on my USDC", "get paid to buy the dip": **sell** one cash-secured
  put, fully collateralised in USDC. They keep the premium and may end up buying the
  asset at the strike (`references/selling.md`).
- **Buy** - "buy an ETH call", "hedge my ETH with a put": **buy** one call or put.
  Not yield: they pay up front and can lose all of it (`references/buying.md`).
- **Close** - before expiry: "sell my call back" **sells back** an option they
  **bought**; "get out of my put", "free my collateral" **buys back** a note they
  **sold**. Buying back can cost more than the note brought in.

Not this skill: covered calls, spreads, leverage, or any trade the helper refuses. It
never picks a trade *for* them.

## Before you start

1. **Which of the three.** Earning and buying are different promises; never blur them.
   Selling fits only USDC whose owner would happily buy the asset lower; if not, there
   is no note here.
2. **One asset, one amount.** Selling locks collateral to expiry; buying spends the
   cost outright.
3. **The bad case first, in their words, before any upside number.** Selling: *"ETH
   drops to $2,000 and you have bought it at $2,300 anyway."* Buying: *"If ETH is not
   above $2,664 on 30 October, the $190 is gone."*
4. **First time for that kind of trade:** the plain yes answers in
   `references/selling.md` or `references/buying.md`. A no or a vague answer stops it.

Money commands need Butler's server signer and run from chat only, never from a duty.

## Procedure

1. [ADAPT] Read what they hold and their Derive account:

   ```sh
   bevo-read assets
   acp options account
   ```

   `signerReady: false` - stop: the owner must enable Butler's signer first. Note
   `account.freeForNewPutsUsd` (`exists: false` is no account yet),
   `account.positions` (positive `size` = bought, negative = sold) and `ethereum.usdc`.
   An unreadable account is not an empty one.

2. [FIXED] Write the script in `references/helper.md` to `/tmp/derive_helper.py`.
   Quote with the line for the intent; the strike is a rule, never your number:

   ```sh
   python3 /tmp/derive_helper.py screen --tenor monthly --collateral <USD>
   python3 /tmp/derive_helper.py quote --product cash_secured_put --underlying <ASSET> --collateral <USD> --tenor monthly --otm-pct 10
   python3 /tmp/derive_helper.py quote --side buy --product <PRODUCT> --underlying <ASSET> --budget <USD> --tenor monthly --otm-pct 5
   python3 /tmp/derive_helper.py quote --side close --instrument <INSTRUMENT> --size <SIZE>
   python3 /tmp/derive_helper.py quote --side buyback --instrument <INSTRUMENT> --size <SIZE> --premium-received <USD>
   ```

   Selling: screen first, then quote. Buying: `<PRODUCT>` is `call` or `put`,
   `--budget` the most they will spend; `--delta 0.3` instead of `--otm-pct` holds the
   odds steady. Closing: instrument and size from `positions`; positive is `--side
   close`, negative is `--side buyback` with the size positive and `--premium-received`
   the note's `netPremiumUsd` (or its duty's PREMIUM_USD) scaled to it. **Offer only
   `tradeable: true`**; give the `reasons` as written.

3. [ADAPT] Offer it using **only** quote fields (the references map each to a
   sentence; never compute a premium, a breakeven or an APR):
   - **Sell:** bad case first, then `net_premium_usd`, `fee_usd`, the lock to
     `expiry`. Then a **separate** yes: *"Happy to own 2.17 ETH at $2,300 on 30
     October?"* A yes to the yield is not a yes to this. Derive settles in cash;
     Butler buys the asset after settlement only if they ask for that now.
   - **Buy:** not yield; `max_cost_usd` is the most they pay and can lose, all of it;
     `breakeven` is where it pays at expiry, and it loses value while the price stands
     still. Get an explicit yes to *"you can lose the whole $199.54"*.
   - **Close (sell back):** `net_proceeds_usd` now, against what they paid (the duty's
     PREMIUM_USD); they agree the floor (`min_proceeds_usd` unless they name one).
   - **Close (buy back):** `total_cost_usd` now, then `result_usd`: what the note made
     or lost once bought back; `warnings` as written; it frees `frees`. They agree the
     ceiling (`max_cost_usd` unless they name one). Waiting for expiry costs nothing
     to do; say so when `result_usd` is negative.

4. [FIXED] Fund a sell or a buy only when `freeForNewPutsUsd` is below
   `collateral.amount` (sell) or `max_cost_usd` (buy). Deposit the shortfall plus 2% for
   the bridge fee and its 1% slippage bound, rounded up, and **never under $6** (the
   server refuses a bridge that could land under $5.05). Say the bridge fee comes out
   of the amount:

   ```sh
   acp options deposit --amount <DEPOSIT_USDC> --idempotency-key <KEY>:deposit
   ```

   The trade bot takes USDC from the owner's wallet on **whichever chains hold it**,
   gathering from several when none covers alone (`references/venue.md`): never judge a
   deposit by one chain's balance, and if asked, USDC on any supported chain counts. A
   wallet that cannot cover it is refused with the per-chain balances. Add `--from 1` only
   when `ethereum.usdc` already covers it: the bot does not gather from Ethereum ($5
   minimum). Never ask about gas or an address. Re-read
   `acp options account` until free USDC covers the trade; if it ends short, re-quote
   smaller and re-offer.

5. [FIXED] Quote again if `valid_until` has passed, then file the one command for the
   intent, with the quote's own fields:

   ```sh
   acp options open --instrument <instrument> --size <size> --min-premium <min_premium_usd> --max-collateral <collateral.amount> --idempotency-key <KEY>:open
   acp options buy --instrument <instrument> --size <size> --max-cost <max_cost_usd> --idempotency-key <KEY>:buy
   acp options close --instrument <instrument> --size <size> --min-proceeds <AGREED_FLOOR> --idempotency-key <KEY>:close
   acp options close --instrument <instrument> --size <size> --max-cost <AGREED_CEILING> --idempotency-key <KEY>:close
   ```

   A close takes one bound: `--min-proceeds` sells back, `--max-cost` buys back. The
   reply is an approval card, not a fill: tell the owner to approve it in the app.

6. [FIXED] Wait for the outcome; never re-run the command to find it. Butler's server
   posts a note in this chat when the card lands and nudges you. Then:

   ```sh
   bevo-read request <KEY>:<OP> --route options
   ```

   `approvalStatus: confirmed` - `approvalOutcome` holds the fill: open
   `filledSize`, `netPremiumUsd`, `collateral`; buy `filledSize`, `totalCostUsd`;
   close `direction` (`sell_back` / `buy_back`), `filledSize`, `netProceedsUsd` or
   `totalCostUsd`. A fill can be partial. `failed` or `rejected` - nothing traded;
   give `approvalFailureReason` as written. `pending` or `signed` - still waiting.

7. [FIXED] Only on `confirmed`, keep the lifecycle duty in step, numbers from
   `approvalOutcome`, never the quote. After an open or a buy, `duty_create`:

   ```json
   {"recipe": "options-lifecycle@3", "triggers": [{"kind": "timer", "intervalSeconds": 900}],
    "params": {"INSTRUMENT": "ETH-20261030-2600-C", "PRODUCT": "long_call", "UNDERLYING": "ETH",
               "TOKEN_ID": "native:8453", "STRIKE": 2600, "SIZE": 2.95, "PREMIUM_USD": 190.03, "COLLATERAL_USD": 0}}
   ```

   Sold put: PRODUCT `cash_secured_put`, PREMIUM_USD `netPremiumUsd`, COLLATERAL_USD
   `collateral`, `DELIVER_ASSET` only if they asked in step 3. Bought: PRODUCT
   `long_call` or `long_put`, PREMIUM_USD `totalCostUsd`, COLLATERAL_USD 0. Always
   SIZE `filledSize`, STRIKE `strike`, UNDERLYING the instrument's prefix. TOKEN_ID:
   ETH is `native:8453`; BTC is the verified, non-stock Base row of `bevo-read
   token-search BTC` as `<address>:8453` (say which; ask if two fit). After a close,
   `duty_delete` that instrument's duty; if part is still open, file it again with SIZE
   from `positions` (positive) and PREMIUM_USD and COLLATERAL_USD scaled to it. Never
   file for an unknown or failed trade.

8. [FIXED] Withdraw only when asked, only free USDC. It pays to the owner's wallet on
   Ethereum in about 20 minutes, less up to $1; bringing it to Base is a second card
   once it shows in `ethereum.usdc`:

   ```sh
   acp options withdraw --amount <USDC> --idempotency-key <KEY>:withdraw
   acp trade --token-in usdc --chain-in 1 --amount-in <USDC_ARRIVED> --token-out usdc --chain-out 8453 --idempotency-key <KEY>:home
   ```

## Idempotency and retries

Quotes are free reads: re-run one past `valid_until` (60 s) rather than act on it.

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
| `no live bid` / `no live ask` | Nobody is trading that option now. Another strike, expiry or asset, or stop. |
| `vol points wide`, `paying N% over fair value` | The price is poor; say so. Never trade it anyway. |
| `fees are N% of the premium` | Ticket too small or tenor too short. Offer monthly or bigger. |
| `collateral too small`, `budget too small` | Under Derive's minimum. Give the figure from the reason. |
| `OPTIONS_SIGNER_NOT_READY` | The signer must be enabled first. Nothing was filed. |
| `OPTIONS_CHAT_ONLY` | A duty tried a money command. Only chat trades. |
| `OPTIONS_BOUNDS_MISMATCH` | Re-quote; never raise a bound past what the owner agreed. |
| No fill (open, buy or close) | Nothing traded, spent or locked: the price moved past the bound. Re-quote and re-offer; never move the bound quietly. |
| Buy failed over `--max-cost` | Give the reason as written, then read `positions`: an option shown there was bought. Never buy again to fix it. |
| Not enough free USDC | Fund (step 4) or re-quote smaller. |
| Close larger than held, or the wrong bound | Refused, nothing done. Re-read `positions`: positive size sells back with `--min-proceeds`, negative buys back with `--max-cost`. |
| Deposit refused, failed or partial | Give the reason as written (a wallet that cannot cover it lists its USDC per chain); re-read the account before any new deposit. Never move funds between chains to fix it. |
| Withdraw or `:home` failed | Give the reason as written, and stop. |
| `OPTIONS_BAD_COMMAND` | Malformed or under a minimum. Nothing was filed. |
| Card swept after 30 minutes | It failed unsigned. Re-quote before offering again. |
| Derive or the account unreachable | Say Butler cannot see it now. Quote nothing; guess nothing. |

## Limits

- Selling: cash-secured puts only, fully collateralised, locked until expiry or
  bought back. Buying: one call or put, paid in full, nothing borrowed; close any time
  the book bids. No spreads, leverage or covered calls; no rolling without a fresh yes.
- **Monthly by default**; weeklies lose too much to fees and the spread.
- **Cash settled.** A sold put ending in the money reduces USDC; a bought option pays
  USDC into the Derive account. Nobody is handed ETH; money stays on Derive until
  withdrawn.
- Prices are the public book; a quote is the worst case. Not advice: never rank,
  never recommend.

## Say to the owner

Worked sentences for each case end `references/selling.md` and `references/buying.md`.
Close: "Selling back now gets about $178.73 after fees, against $190.03 you paid."
