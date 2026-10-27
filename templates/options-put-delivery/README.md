# options-put-delivery

Watches one cash-secured put the owner **sold** on Derive or Paradex (`acp options open`) to its outcome and, if it is assigned, **buys the asset** the put agreed to buy. Both venues settle in cash, so without the buy an assigned put leaves the owner holding the loss in USDC and none of the asset. The options-trading skill files it instead of `options-lifecycle` only when the owner asked, before the open, to end up owning the asset.

## How it is filed

Filed with `recipe: "options-put-delivery@1"` only once `bevo-read request <key> --route options` reads `approvalStatus: confirmed`, with settings from its `approvalOutcome`, never the quote: `INSTRUMENT` and `STRIKE` as filled, `SIZE` = `filledSize`, `PREMIUM_USD` = `netPremiumUsd`, `COLLATERAL_USD` = `collateral`. `TOKEN_ID` is the token to buy, from its `/token-search` row (`native:8453` for ETH on Base). `spendBasis: {"perTrade": "COLLATERAL_USD", "times": 1}`: the buy never costs more than the collateral, so the pocket card opens on it.

## What it does

| When | The owner gets |
| --- | --- |
| `HEADS_UP_HOURS` before expiry, once | where the asset is on the venue's own index, and which way the note is leaning |
| after expiry, once the venue publishes the price | what they kept, or what they agreed to buy; then the duty finishes |
| after an assigned put | a spot buy of SIZE x the settlement price of the `TOKEN_ID` token, through `acp trade`, keyed `note:<duty>:deliver` |

## What it will not do

- **Say "you now own" without a filled buy.** A pending, refused or unknown buy is reported as such.
- **Buy without a settlement price.** No price yet: it waits, saying so once past 6 hours. An unreadable read is reported as broken.
- **Retry the buy.** One key; an unclear answer goes to `exec_status`.
- **Buy for a put it did not see held.** Bought back before expiry, it ends after two `/options/account` reads in a row without it; missing at the last read before expiry, it reports and does not buy.
- **Buy by ticker.** Only the `TOKEN_ID` pin, on its own chain.
- **Move collateral.** Withdrawing it is a separate `acp options withdraw`.

## Settings

| Name | Unit | Means |
| --- | --- | --- |
| `VENUE` | `derive` (default) \| `paradex` | not Rysk, which delivers the asset itself |
| `INSTRUMENT` | venue's name | a put, as filled: `ETH-20261030-2450-P`, `ETH-USD-30OCT26-2450-P` |
| `UNDERLYING` | ticker | the prefix of `INSTRUMENT` |
| `TOKEN_ID` | pin | `native:<chainId>` or `<address>:<chainId>`: the one token the buy trades |
| `STRIKE` | US dollars | the price agreed to buy at |
| `SIZE` | units of the underlying | as filled |
| `PREMIUM_USD` | US dollars | kept, net of the fee |
| `COLLATERAL_USD` | US dollars | USDC locked behind the put; sizes the pocket |
| `HEADS_UP_HOURS` | hours, default `24` | how long before expiry the heads-up is sent |

## Trigger

`{"kind": "timer", "intervalSeconds": 900}`.
