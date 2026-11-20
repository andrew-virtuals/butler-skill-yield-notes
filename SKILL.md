---
name: options-trading
description: Trade options on Derive, Paradex or Rysk - earn on idle USDC by selling cash-secured puts, buy a call or a put, close before expiry, and check or withdraw USDC and positions.
version: 2.16.0
metadata: {"butler":{"moneyMoving":true,"keywords":["yield","earn on my usdc","make my money work","idle cash","options income","cash secured put","sell options","sell a put","premium","get paid to wait","buy the dip","yield note","options","buy a call","buy a put","call option","put option","hedge","protect my eth","upside","bet on eth","close my option","sell my option back","buy back my put","close my note","exit my put","get my collateral back","withdraw","withdraw my usdc","derive","my options","options account","options positions","free usdc","derive positions","my option positions","withdraw from derive","withdraw my free usdc","paradex","paradex options","paradex positions","rysk","rysk options","rysk positions","physically settled","hyperevm","limit order","resting order","at my price","or better","leave it on the book","cancel my order","options duty","automate options","options strategy"],"requires":{"bins":["python3","bevo-read","acp"]}}}
---

## When to use

Your owner wants, on Derive, Paradex or Rysk options:

- **Earn** - "earn on my USDC", "get paid to buy the dip": **sell** one cash-secured
  put, fully collateralised in USDC. They keep the premium and may end up buying the
  asset at the strike (`selling.md`).
- **Buy** - "buy an ETH call", "hedge my ETH with a put": **buy** one call or put.
  Not yield: they pay up front and can lose all of it (`buying.md`).
- **Close** - before expiry: "sell my call back" **sells back** an option they
  **bought**; "get out of my put", "free my collateral" **buys back** a note they
  **sold**.
- **At their price** - "or better", "cancel my order": `resting.md`.
- **Later** - on a condition, time or schedule: a duty.
- **Look or withdraw** - "my free USDC in Derive" (`freeForNewPutsUsd`, not wallet
  cash), "my positions": step 1, then stop. "Withdraw my free USDC": step 8, never an
  `acp trade` (`account.md`). Listing: `listing.md`.

Not this skill: covered calls, spreads or leverage.

## Before you start

1. **Now or later.** A trade that waits, or may (a condition, time, schedule), is a duty:
   read `duty.md`, and file nothing in the turn they ask it.
2. **Which one.** Earning and buying are different promises; never blur them.
   Selling fits only USDC whose owner would happily buy the asset lower; a no to that
   ends selling, every put on it.
3. **Sizes are in the asset:** say "0.16 ETH", never "contracts", never convert;
   `min_size` is only its minimum.
4. **The bad case first, in their words, before any upside number:** selling, from
   `bad_case`; buying, that what it costs is gone.
5. **First time for that kind of trade:** the plain yes answers in
   `selling.md` or `buying.md`. A no or a vague answer stops it.
6. **Figures come only from this turn's reads:** sizes, prices and positions
   from `acp options account` and quotes, never memory; fix a note that
   disagrees.
7. **Venue.** Quote an open on each venue offering it, unless they name one; the
   rest where it is. `--venue` it everywhere.

### Never file without all four

Before any `acp options` deposit, open, buy or close, from the owner's words in
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

1. [ADAPT] Read the account before answering or filing, and the wallet only to
   fund (step 4):

   ```sh
   acp options account
   bevo-read assets
   ```

   `signerReady: false` - stop: the owner must enable Butler's signer first. Fields:
   `account.md`. An unreadable account is not an empty one. On
   `exists: true` on any venue, step 9.

2. [FIXED] Run the helper in place; never write, copy or edit a script, or trim its
   output. Missing: say so, and stop. Quote with the line for the intent
   (`helper.md`); the strike is a rule or theirs:

   ```sh
   python3 ~/skills/options-trading/scripts/quote.py screen --collateral <USD>
   python3 ~/skills/options-trading/scripts/quote.py quote --product cash_secured_put --underlying <ASSET> --collateral <USD> [--expiry <DAY>] [--strike <N>]
   python3 ~/skills/options-trading/scripts/quote.py quote --side buy --product <PRODUCT> --underlying <ASSET> --budget <USD> [--expiry <DAY>] [--strike <N>]
   python3 ~/skills/options-trading/scripts/quote.py quote --side close --instrument <INSTRUMENT> --size <SIZE>
   python3 ~/skills/options-trading/scripts/quote.py quote --side buyback --instrument <INSTRUMENT> --size <SIZE> --premium-received <USD>
   ```

   Selling: the asset they named, or screen (never an APR menu) and ask. **No amount
   from them:** each venue's `minimum` (`which-venue.md`), then ask it; no quote,
   screen or chain till then. Buying: `<PRODUCT>` is `call` or `put`,
   `--budget` the most they will spend. Closing: instrument and size from `positions`;
   positive is `--side close`; negative, `--side buyback` with the size positive and
   `--premium-received` the note's `netPremiumUsd` (or its duty's PREMIUM_USD) scaled
   to it. `reasons`: a venue limit, give them as written. `waivable: true`: a
   safeguard (`helper.md` § Safeguards). A strike or
   day they named: `buying.md`.

3. [ADAPT] Offer it using **only** quote fields, its `warnings` said as written and
   never a reason to withhold it; never compute a number:
   - **Fees:** "$0.65 in fees: $0.62 to Derive, $0.03 Virtuals platform fee"; 0: "no Virtuals platform fee".
   - **Sell:** `bad_case` first, then `net_premium_usd`, the lock to
     `expiry`; `apr_pct` last. Then, on its own: *"Happy to own 0.13 ETH at $2,200 on
     30 October?"* A no or a vague answer ends it: no other strike, tenor or asset.
     Butler buys the asset later only if they ask now.
   - **Buy:** not yield; `max_cost_usd` is the most they pay and can lose, all of it;
     `breakeven` is where it pays at expiry. Get an explicit yes to *"you can lose the whole $199.54"*.
   - **Close (sell back):** `net_proceeds_usd` now, against what they paid (the duty's
     PREMIUM_USD). Ask the floor (`min_proceeds_usd` suggested).
   - **Close (buy back):** `total_cost_usd` now, then `result_usd` (what the note made
     or lost); it frees `frees`. Ask the ceiling (`max_cost_usd`
     suggested). Waiting costs nothing: say so when `result_usd` is negative.

4. [FIXED] With all four met, fund a sell or a buy only when `freeForNewPutsUsd` is below
   `collateral.amount` (sell) or `max_cost_usd` (buy). Deposit the shortfall plus 2% for
   the bridge fee and its 1% slippage bound, rounded up, and **never under $6**. Say
   the bridge fee comes out of the amount:

   ```sh
   acp options deposit --amount <DEPOSIT_USDC> --idempotency-key <KEY>:deposit
   ```

   The bot gathers stablecoins from **every chain**, any venue.
   `--from 1` only when `ethereum.usdc` covers it alone. Never ask about gas or an
   address. Re-read the account until free USDC covers it, and do step 9; if
   short, re-quote smaller and re-offer.

5. [FIXED] Run the quote again now, after their last answer. With all four met, file
   the command, with that quote's fields and the bound they agreed:

   ```sh
   acp options open --instrument <instrument> --size <size> --min-premium <min_premium_usd> --max-collateral <collateral.amount> [--waive <waive>] --idempotency-key <KEY>:open
   acp options buy --instrument <instrument> --size <size> --max-cost <max_cost_usd> [--waive <waive>] --idempotency-key <KEY>:buy
   acp options close --instrument <instrument> --size <size> --min-proceeds <AGREED_FLOOR> --idempotency-key <KEY>:close
   acp options close --instrument <instrument> --size <size> --max-cost <AGREED_CEILING> --idempotency-key <KEY>:close
   ```

   One bound per close. The reply is an approval card, not a fill: tell the owner to
   approve it in the app. At their price: `resting.md`; by RFQ: `rfq.md`.

6. [FIXED] Wait for the outcome; never re-run the command for it. Then:

   ```sh
   bevo-read request <KEY>:<OP> --route options
   ```

   `approvalStatus: confirmed` - `approvalOutcome` holds the fill, maybe partial:
   `filledSize`, plus open `netPremiumUsd`, `collateral`; buy `totalCostUsd`; close
   `direction`, `netProceedsUsd` or `totalCostUsd`; `funding`: USDC moved first, say so; fees split as `summary` does, Virtuals named, at 0 too.
   `failed` or `rejected` - nothing traded; give `approvalFailureReason` as written.
   `pending` or `signed` - still waiting.

7. [FIXED] Only on `confirmed`, keep the lifecycle duty in step, numbers from
   `approvalOutcome`, never the quote. After an open or a buy, `duty_create`:

   ```json
   {"recipe": "options-lifecycle@11", "movesFunds": false, "title": "Watch {INSTRUMENT} to expiry",
    "triggers": [{"kind": "timer", "intervalSeconds": 900}],
    "params": {"VENUE": "<venue>", "INSTRUMENT": "<instrument>", "PRODUCT": "<product>", "UNDERLYING": "<instrument prefix>",
    "STRIKE": <strike>, "SIZE": <filledSize>, "PREMIUM_USD": <usd>, "COLLATERAL_USD": <usd>}}
   ```

   Sold put: PRODUCT `cash_secured_put`, PREMIUM_USD `netPremiumUsd`, COLLATERAL_USD
   `collateral`. Bought: PRODUCT `long_call` or `long_put`, PREMIUM_USD `totalCostUsd`,
   COLLATERAL_USD 0. Resting: `resting.md`. Asked in step 3 to own the asset: `options-put-delivery@1`
   (`selling.md`). After a close, `duty_delete` that instrument's duty; if
   part is still open, file it again with SIZE from `positions` (positive) and
   PREMIUM_USD and COLLATERAL_USD scaled to it. Never file for an unknown or failed
   trade. A second options duty in one chat needs
   `"alongside": [<this chat's earlier ones>]`; step 9's needs none.

8. [FIXED] Withdraw only when asked, only free USDC: at most this turn's
   `freeForNewPutsUsd`, rounded down to the cent. It lands on Ethereum in its card's
   window, less Derive's fee (say so first); `:home` brings it to Base once in
   `ethereum.usdc`:

   ```sh
   acp options withdraw --amount <USDC> --idempotency-key <KEY>:withdraw
   acp trade --token-in usdc --chain-in 1 --amount-in <USDC_ARRIVED> --token-out usdc --chain-out 8453 --idempotency-key <KEY>:home
   ```

9. [FIXED] Once any venue has an account, unasked: with no `options-account` duty,
   file it and delete any `derive-account` one; an older one or a fork,
   `duty_update` to this recipe.

   ```json
   {"recipe": "options-account@6", "title": "Options accounts", "triggers": [{"kind": "timer", "intervalSeconds": 600}]}
   ```

   It alone writes Platforms rows; never `bevo-platforms set`.

## Idempotency and retries

Derive one key per trade, such as `ot:eth:20261030:2600c:1`, with `:deposit`,
`:open`, `:buy`, `:close`, `:withdraw`, `:home`. On an error, a timeout or an unclear
answer, **do not re-run** the command: a retry can buy or bridge twice. Look it up as
in step 6: `not_found` means nothing was filed. A deposit still crediting has not
failed: re-read the account and wait. Look up `:home` with `--route trade`.

## Failure handling

| Outcome | What to do |
| --- | --- |
| `waivable: true` | A safeguard: offer it with its `text` and ask if they still want to go ahead. Their yes re-quotes with `--waive` (`helper.md`). |
| `no live bid` / `no live ask` | Opening: another strike, expiry or asset, or stop. Closing: nobody bids for theirs now; holding costs nothing. |
| `collateral too small`, `budget too small` | Under the minimum. Give the reason's figures, work out no others, and stop unless they name another strike, expiry or amount. |
| An `OPTIONS_*` refusal | Nothing filed: follow its hint; never raise a bound the owner agreed. |
| No fill | Nobody took it at the agreed bound (never "no liquidity"); nothing moved. Re-quote, re-ask, never re-file the same bound. |
| Buy failed over `--max-cost` | Give the reason as written, then read `positions`: anything shown there was bought. Never buy again. |
| Deposit refused, failed or partial | Give the reason as written; re-read the account before another deposit. Never move funds between chains to fix it. |
| Withdraw or `:home` failed | Give the reason as written, and stop (`only $N is free`: the rest backs sold puts). |
| Card swept after 30 minutes | Unsigned; re-quote before offering again. |

## Limits

- Selling locks collateral until expiry or a buy-back; buying is paid in full. No rolling
  without a fresh yes.
- **Cash settled** on Derive and Paradex, kept there till withdrawn; Rysk delivers the asset.
- Not advice: never rank or recommend a trade.

## Say to the owner

Worked sentences end each reference.
