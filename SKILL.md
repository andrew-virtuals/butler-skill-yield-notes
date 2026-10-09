---
name: options-trading
description: Trade options on Derive - earn on idle USDC by selling cash-secured puts, or buy a call or a put for upside or a hedge, and sell it back before expiry.
version: 2.0.0
metadata: {"butler":{"moneyMoving":true,"keywords":["yield","earn on my usdc","make my money work","idle cash","options income","cash secured put","sell options","sell a put","premium","get paid to wait","buy the dip","yield note","options","buy a call","buy a put","call option","put option","hedge","protect my eth","upside","bet on eth","close my option","sell my option back"],"requires":{"bins":["python3","bevo-read","acp"]}}}
---

## When to use

Your owner wants one of three things on Derive's options market:

- **Earn** - "earn on my USDC", "get paid to buy the dip": **sell** one cash-secured
  put, fully collateralised in USDC. They keep the premium and may end up buying the
  asset at the strike. Detail: `references/selling.md`.
- **Buy** - "buy an ETH call", "hedge my ETH with a put": **buy** one call or put.
  This is not yield: they pay up front and can lose all of it. Detail:
  `references/buying.md`.
- **Close** - "sell my call back": sell an option they **bought** before expiry.

Not this skill: covered calls, spreads, leverage, closing a sold note, or any trade the
helper refuses. It never picks a trade *for* them.

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

Money commands need Butler's server signer and run from chat only, never a duty.

## Procedure

1. [ADAPT] Read what they hold and their Derive account:

   ```sh
   bevo-read assets
   acp options account
   ```

   `signerReady: false` - stop: the owner must enable Butler's signer first. Note
   `network`, `account.freeForNewPutsUsd` (free USDC; `exists: false` is no account
   yet), `account.positions` (positive `size` = bought, negative = sold) and
   `ethereum.usdc`. An unreadable account is not an empty one.

2. [FIXED] Write the script in `references/helper.md` to `/tmp/derive_helper.py`.
   If `network` is `testnet`, put `--testnet` straight after the script name in every
   call. Quote with the line for the intent; the strike is a rule, never your number:

   ```sh
   python3 /tmp/derive_helper.py screen --tenor monthly --collateral <USD>
   python3 /tmp/derive_helper.py quote --product cash_secured_put --underlying <ASSET> --collateral <USD> --tenor monthly --otm-pct 10
   python3 /tmp/derive_helper.py quote --side buy --product <PRODUCT> --underlying <ASSET> --budget <USD> --tenor monthly --otm-pct 5
   python3 /tmp/derive_helper.py quote --side close --instrument <INSTRUMENT> --size <SIZE>
   ```

   Selling: screen first, then quote. Buying: `<PRODUCT>` is `call` or `put`,
   `--budget` the most they will spend. `--delta 0.3` holds the odds steady instead
   of `--otm-pct`. Closing: the instrument and size from `positions`. **Offer only
   `tradeable: true`**; give the `reasons` as written.

3. [ADAPT] Offer it using **only** quote fields (the references map each to a
   sentence; never compute a premium, a breakeven or an APR):
   - **Sell:** bad case first, then `net_premium_usd`, `fee_usd`, the lock to
     `expiry`. Then a **separate** yes: *"Happy to own 2.17 ETH at $2,300 on 30
     October?"* A yes to the yield is not a yes to this. Derive settles in cash;
     Butler buys the asset after settlement only if they ask for that now.
   - **Buy:** say it is not yield; `max_cost_usd` is the most they pay and can lose,
     all of it; `breakeven` is where it starts paying at expiry, and it loses value
     each day the price stands still. Get an explicit yes to *"you can lose the whole
     $199.54"*.
   - **Close:** `net_proceeds_usd` now, against what they paid (the duty's
     PREMIUM_USD); they agree the floor (`min_proceeds_usd` unless they name one).

4. [FIXED] Fund a sell or a buy only when `freeForNewPutsUsd` is below
   `collateral.amount` (sell) or `max_cost_usd` (buy). Deposit the shortfall plus about
   1% (at least $1) for the bridge fee, rounded up to the cent, and **never under $10
   from Base** (the server refuses a bridge that could land under $6). Say the bridge
   fee comes out of the amount:

   ```sh
   acp options deposit --amount <DEPOSIT_USDC> --idempotency-key <KEY>:deposit
   ```

   Add `--from 1` only when `ethereum.usdc` already covers it (the only source on
   testnet; $5 minimum). Never ask about gas or an address. Re-read
   `acp options account` until free USDC covers the trade; if it ends short, re-quote
   smaller and re-offer.

5. [FIXED] Quote again if `valid_until` has passed, then file the one command for the
   intent, with the quote's own fields:

   ```sh
   acp options open --instrument <instrument> --size <size> --min-premium <min_premium_usd> --max-collateral <collateral.amount> --idempotency-key <KEY>:open
   acp options buy --instrument <instrument> --size <size> --max-cost <max_cost_usd> --idempotency-key <KEY>:buy
   acp options close --instrument <instrument> --size <size> --min-proceeds <AGREED_FLOOR> --idempotency-key <KEY>:close
   ```

   The reply is an approval card, not a fill: tell the owner to approve it in the app.
   Nothing has traded yet.

6. [FIXED] Wait for the outcome; never re-run the command to find it. Butler's server
   posts a note in this chat when the card lands and you are nudged. Then:

   ```sh
   bevo-read request <KEY>:<OP> --route options
   ```

   `approvalStatus: confirmed` - `approvalOutcome` holds the fill: open
   `filledSize`, `netPremiumUsd`, `collateral`; buy `filledSize`, `totalCostUsd`;
   close `filledSize`, `netProceedsUsd`. A fill can be partial. `failed` or
   `rejected` - nothing traded; give `approvalFailureReason` as written. `pending` or
   `signed` - still waiting.

7. [FIXED] Only on `confirmed`, keep the lifecycle duty in step, numbers from
   `approvalOutcome`, never the quote. After an open or a buy, `duty_create`:

   ```json
   {"recipe": "options-lifecycle@3",
    "params": {"INSTRUMENT": "ETH-20261030-2600-C", "PRODUCT": "long_call",
               "UNDERLYING": "ETH", "TOKEN_ID": "native:8453", "STRIKE": 2600,
               "SIZE": 2.95, "PREMIUM_USD": 190.03, "COLLATERAL_USD": 0},
    "triggers": [{"kind": "timer", "intervalSeconds": 900}]}
   ```

   Sold put: PRODUCT `cash_secured_put`, PREMIUM_USD `netPremiumUsd`, COLLATERAL_USD
   `collateral`, `DELIVER_ASSET` only if they asked in step 3. Bought: PRODUCT
   `long_call` or `long_put`, PREMIUM_USD `totalCostUsd`, COLLATERAL_USD 0. Always
   SIZE `filledSize`, STRIKE `strike`, UNDERLYING the instrument's prefix. TOKEN_ID:
   ETH is `native:8453`; for BTC take the verified, non-stock Base row from
   `bevo-read token-search BTC` as `<address>:8453` (say which; ask if two fit).
   After a close, `duty_delete` that instrument's duty; if part is still held, file it
   again with SIZE what `positions` shows. Never file for an unknown or failed trade.

8. [FIXED] Withdraw only when asked, only free USDC. It pays to the owner's wallet on
   Ethereum in about 20 minutes, less up to $1; bringing it to Base is a second card,
   only once it shows in `ethereum.usdc`:

   ```sh
   acp options withdraw --amount <USDC> --idempotency-key <KEY>:withdraw
   acp trade --token-in usdc --chain-in 1 --amount-in <USDC_ARRIVED> --token-out usdc --chain-out 8453 --idempotency-key <KEY>:home
   ```

## Idempotency and retries

Quotes are free reads: re-run them rather than act on one past `valid_until` (60 s).

Derive one key per trade, such as `ot:eth:20261030:2600c:1`, with `:deposit`,
`:open`, `:buy`, `:close`, `:withdraw`, `:home`. On an error, a timeout or an unclear
answer, **do not re-run** the command - a retried buy can buy twice, a retried
deposit can bridge twice. Look it up:

```sh
bevo-read request <KEY>:<OP> --route options
```

`not_found` means nothing was filed under that key. A deposit still crediting is not a
failed one: re-read `acp options account` and wait. The `:home` leg is `acp trade`:
look it up with `--route trade`.

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
| No fill (open, buy or close) | Nothing traded: nothing sold, bought, spent or locked. The price moved past the bound; re-quote and re-offer, never move the bound quietly. |
| Buy failed over `--max-cost` | Give the reason as written, then read `positions`: an option shown there was bought. Never buy again to fix it. |
| Not enough free USDC | Fund (step 4) or re-quote smaller. |
| Close larger than held, or of a sold note | Refused. Close what `positions` shows as bought; a sold note runs to expiry. |
| Deposit failed or partial | Give the reason as written; re-read the account before any new deposit. |
| Withdraw or `:home` failed | Give the reason as written, and stop. |
| `OPTIONS_BAD_COMMAND` | Malformed or under a minimum. Nothing was filed. |
| Card swept after 30 minutes | It failed unsigned. Re-quote before offering again. |
| Derive or the account unreachable | Say Butler cannot see it right now. Quote nothing; guess nothing. |

## Limits

- Selling: cash-secured puts only, fully collateralised, locked to expiry, **no early
  close**. Covered calls come later.
- Buying: one call or put, paid in full, nothing borrowed. Close any time the book
  bids; otherwise it settles at expiry.
- No spreads, no leverage, no rolling without a fresh yes.
- **Monthly by default**; weeklies lose too much to fees and the spread.
- **Cash settled.** A sold put that ends in the money reduces USDC; a bought option
  pays USDC into the Derive account. Nobody is handed ETH. Money stays on Derive
  until withdrawn.
- Prices are the public book; a quote is the worst case. Not advice: never rank,
  never recommend.

## Say to the owner

Sell: "If ETH is below $2,300 on 30 October, you pay $2,300 each for 2.17 ETH - at
$2,000 that is about $650 more than they are worth, and the $56 does not cover it. If
it is above, your $4,991 earns **$55.76** over 23 days. The money is locked until then."

Buy: "This is a bet, not yield. You pay at most **$199.54** for 2.95 ETH calls at
$2,600, and if ETH is not above about $2,664 on 30 October you lose all of it. Each
day ETH stands still it is worth a little less. You can lose the whole $199.54 - yes?"

Close: "Selling back now gets about $178.73 after fees, against $190.03 you paid."

Nothing clears: "Nothing worth doing today - the market is wide, and you would give
away too much to get filled."
