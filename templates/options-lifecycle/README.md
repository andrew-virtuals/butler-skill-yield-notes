# options-lifecycle

Watches one option on Derive, Paradex or Rysk from the fill to the outcome: a note the owner **sold** (`acp options open`) or an option they **bought** (`acp options buy`). The options-trading skill files it once the fill is confirmed, one duty per option.

## How it is filed

Filed with `recipe: "options-lifecycle@8"` only once `bevo-read request <key> --route options` reads `approvalStatus: confirmed`, with settings from its `approvalOutcome`, never the quote: `INSTRUMENT` and `STRIKE` as filled, `SIZE` = `filledSize`, `PREMIUM_USD` = `netPremiumUsd` (sold) or `totalCostUsd` (bought), `COLLATERAL_USD` = `collateral` (0 if bought). `TOKEN_ID` only with `DELIVER_ASSET`: the token the delivery buy trades, from its `/token-search` row (`native:8453` for ETH on Base). An unknown, refused or pending open gets no duty.

## What it does

| When | The owner gets |
| --- | --- |
| `HEADS_UP_HOURS` before expiry, once | where the asset is on the venue's own index, and which way the note is leaning |
| after the 08:00 UTC expiry, once the venue publishes the price | a sold note: what they kept, or what they agreed to buy or sell; a bought option: what it paid out against what it cost, or that it expired worthless; then the duty finishes |
| after an assigned put, only with `DELIVER_ASSET` on | a spot buy of the underlying, through `acp trade`, keyed `note:<duty>:deliver` |
| on Rysk, once paid out | the asset or the USDC (`settled` in `/options/account`) |

Expiry and option type are read out of `INSTRUMENT` (08:00 UTC on its date) and checked against `PRODUCT` and `UNDERLYING`; a mismatch stops the duty.

## What it will not do

- **Say "you now own" without a filled buy.** Derive and Paradex settle in cash: an assigned put leaves the owner holding the loss in USDC, not the asset. Only an executed delivery buy changes that; a pending, refused or unknown one is reported as such.
- **Guess a settlement.** No price (or Rysk payout) yet: it waits, saying so once past 6 hours. An unreadable read is reported as broken.
- **Retry the delivery buy.** One key; an unclear answer goes to `exec_status`.
- **Price off a DEX, or buy by ticker.** The heads-up reads the venue's index (`/options/ticker`); an empty read skips that tick. The delivery buy trades only the `TOKEN_ID` pin, on its own chain.
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
| `TOKEN_ID` | pin, only with `DELIVER_ASSET` | `native:<chainId>` or `<address>:<chainId>`: the one token the delivery buy trades |
| `STRIKE` | US dollars | the price agreed to buy (put) or sell (call) at |
| `SIZE` | contracts = units of the underlying | as filled |
| `PREMIUM_USD` | US dollars | sold: kept, net of the fee; bought: paid, fee included |
| `COLLATERAL_USD` | US dollars | USDC locked behind a sold put; `0` otherwise |
| `DELIVER_ASSET` | on/off, default **off** | buy the `TOKEN_ID` token after an assigned put, spending SIZE x the settlement price of wallet USDC on its chain; needs `TOKEN_ID` |
| `HEADS_UP_HOURS` | hours, default `24` | how long before expiry the heads-up is sent |

## Trigger

`{"kind": "timer", "intervalSeconds": 900}`. Settlement is usually published within minutes of 08:00 UTC, so a 15-minute timer reports it within the half hour.
