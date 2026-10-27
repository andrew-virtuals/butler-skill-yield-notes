# options-lifecycle

Watches one option on Derive, Paradex or Rysk from the fill to the outcome: a note the owner **sold** (`acp options open`) or an option they **bought** (`acp options buy`). The options-trading skill files it once the fill is confirmed, one duty per option.

## How it is filed

Filed with `recipe: "options-lifecycle@10"` and `movesFunds: false` only once `bevo-read request <key> --route options` reads `approvalStatus: confirmed`, with settings from its `approvalOutcome`, never the quote: `INSTRUMENT` and `STRIKE` as filled, `SIZE` = `filledSize`, `PREMIUM_USD` = `netPremiumUsd` (sold) or `totalCostUsd` (bought), `COLLATERAL_USD` = `collateral` (0 if bought). An unknown, refused or pending open gets no duty. A sold put whose owner asked to end up owning the asset is filed as `options-put-delivery` instead.

## What it does

| When | The owner gets |
| --- | --- |
| `HEADS_UP_HOURS` before expiry, once | where the asset is on the venue's own index, and which way the note is leaning |
| after expiry, once the venue publishes the price | a sold note: what they kept, or what they agreed to buy or sell; a bought option: what it paid out against what it cost, or that it expired worthless; then the duty finishes |
| on Rysk, once paid out | the asset or the USDC (`settled` in `/options/account`) |

Expiry and option type are read out of `INSTRUMENT` (08:00 UTC; Paradex: its ticker's `expirySec`) and checked against `PRODUCT` and `UNDERLYING`; a mismatch stops the duty.

## What it will not do

- **Spend anything.** It runs no command, so it files as a duty that moves no money, with no pocket. Buying the asset after an assigned put is `options-put-delivery`.
- **Say "you now own" after an assigned put.** Derive and Paradex settle in cash: the owner holds the loss in USDC, not the asset.
- **Guess a settlement.** No price (or Rysk payout) yet: it waits, saying so once past 6 hours. An unreadable read is reported as broken.
- **Price off a DEX.** The heads-up reads the venue's index (`/options/ticker`); an empty read skips that tick.
- **Move collateral.** Withdrawing it after settlement is a separate `acp options withdraw`.
- **Watch an option closed early.** Sold or bought back (not possible on Rysk), it ends quietly after two `/options/account` reads in a row without it; the skill normally deletes it on the close.
- **Open, roll or close anything.** It only watches the one it was filed for.

## Settings

| Name | Unit | Means |
| --- | --- | --- |
| `VENUE` | `derive` (default) \| `paradex` \| `rysk` | the venue it trades on; Rysk: sold puts only |
| `INSTRUMENT` | venue's name | as filled: `ETH-20261030-2450-P`, `ETH-USD-30OCT26-2450-P`, `ETH-30OCT26-2450-P` |
| `PRODUCT` | `cash_secured_put` \| `covered_call` (sold) \| `long_call` \| `long_put` (bought) | must match the `P`/`C` in `INSTRUMENT` |
| `UNDERLYING` | ticker | the prefix of `INSTRUMENT`: any currency the venue lists |
| `STRIKE` | US dollars | the price agreed to buy (put) or sell (call) at |
| `SIZE` | contracts = units of the underlying | as filled |
| `PREMIUM_USD` | US dollars | sold: kept, net of the fee; bought: paid, fee included |
| `COLLATERAL_USD` | US dollars | USDC locked behind a sold put; `0` otherwise |
| `HEADS_UP_HOURS` | hours, default `24` | how long before expiry the heads-up is sent |

## Trigger

`{"kind": "timer", "intervalSeconds": 900}`. Settlement is usually published within minutes of expiry, so a 15-minute timer reports it within the half hour.
