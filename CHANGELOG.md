# Changelog

## 2.1.1

- Funding no longer says "from Base". Butler's trade bot takes deposit USDC from
  whichever chains the owner's wallet holds it on, gathering from several when none
  covers alone, so the skill tells the agent never to judge a deposit by one chain's
  balance and how to answer "can I fund this?". Ethereum USDC stays the `--from 1`
  exception. New failure row for a wallet that cannot cover the deposit.
- Mainnet only: the helper's network flag and every mention of a test venue are gone.
  Butler's server trades Derive mainnet.

## 2.1.0

- **Buying back a sold note** before expiry: `acp options close --instrument --size
  --max-cost`. A close now takes one bound, which names the direction:
  `--min-proceeds` sells back a bought option, `--max-cost` buys back a sold one. The
  helper's new `quote --side buyback --instrument --size [--premium-received <usd>]`
  prices it on the ask and returns `total_cost_usd`, `max_cost_usd` (5% room),
  `frees`, and `result_usd` (premium received less the buy-back cost), with a warning
  when that is a loss. Refused only with no ask or an ask thinner than the size.
- The first-time check for selling no longer says "no early exit": getting out early
  means buying the note back, which can cost more than it brought in.
- After a close either way, the lifecycle duty is deleted, or re-filed for what is
  still open.
- Funding: never under $6 from Base. The server bridges at a fixed 1% slippage and
  refuses a bridge whose guaranteed arrival is under $5.05; the bridge itself costs
  about $0.10.

## 2.0.0

- Renamed from `yield-notes` to `options-trading` (a new skill name, so a major
  version). Keywords cover buying calls and puts and hedging as well as income.
- **Buying**: `acp options buy --instrument --size --max-cost`. The helper's new
  `quote --side buy --product call|put --budget <usd>` (or `--size` for a hedge) sizes
  what the budget buys at the ask plus Derive's fee with 5% room, and returns
  `total_cost_usd`, `max_loss_usd`, `breakeven` and `max_cost_usd` (the `--max-cost`
  bound, never over the budget). Buyer gates: no live ask, ask thinner than the size,
  ask more than 5 vol points over mark ("paying N% over fair value"), fees over 15% of
  the premium, budget under Derive's minimum. The skill says plainly it is not yield
  and gets an explicit yes to losing the whole cost.
- **Closing**: `acp options close --instrument --size --min-proceeds` sells back a
  bought option before expiry. The helper's `quote --side close` prices it on the
  bid (`net_proceeds_usd`, `min_proceeds_usd`, `warnings`). A sold note still cannot
  be closed.
- The lifecycle duty is `options-lifecycle@3` for every trade: `cash_secured_put` as
  before, `long_call` / `long_put` after a confirmed buy (`PREMIUM_USD` =
  `totalCostUsd`, `COLLATERAL_USD` 0). After a confirmed close the skill deletes it.
- Funding: never under about $10 from Base, since the server refuses a bridge whose
  worst-case arrival is under $6.
- `SKILL.md` is restructured around the three intents; the explanation moved to
  `references/selling.md` (formerly `notes.md`) and the new `references/buying.md`.
  Selling behaves as in 1.2.1, and the sell quote is unchanged.

## 1.2.1

- The lifecycle duty is filed with `TOKEN_ID`, the underlying pinned to one token
  (`native:8453` for ETH; the verified Base row from `bevo-read token-search` for
  BTC), which options-lifecycle@2 prices with `/token-stats` and delivers.

## 1.2.0

- Funding is one command: `acp options deposit` bridges the owner's Base USDC
  straight into their own Derive account (Butler's server picks the deposit address;
  the bridge fee comes out of the amount). The separate `acp trade` Base-to-Ethereum
  leg and the "deposit what arrived" step are gone.
- The skill deposits the shortfall plus a small margin for the bridge fee (about 1%,
  at least $1), says so to the owner, and waits on `acp options account` until the
  credit covers the note. `--from 1` only when the owner already holds USDC on
  Ethereum.
- A failed or partial deposit is reported with its reason as given, and the account
  is re-read before any new deposit - never a re-run. Withdrawing is unchanged.

## 1.1.0

- Cash-secured puts only, as the rail offers in v1. The covered-call offer is gone
  from the procedure; Limits says calls come later. The helper still quotes them.
- The fill is read from `bevo-read request <key> --route options`:
  `approvalOutcome` (`filledSize`, `netPremiumUsd`, `collateral`, `instrument`,
  `strike`) once `approvalStatus` is `confirmed`, `approvalFailureReason` when it
  failed. The lifecycle duty is filed from those fields.
- The skill waits for the server's outcome note or checks the request; it never
  re-runs a command to find out. A failed bridge, deposit or withdrawal card is
  reported with its reason as given.
- Never asks the owner about Ethereum gas (Butler's server covers it). Deposits under
  $5 are refused by the server as well as by the skill.
- Withdrawals: about 20 minutes, a fee of up to $1.

## 1.0.0

- Derive v3. The helper reads `api.derive.xyz/v3`: one `public/get_tickers` call per
  expiry instead of a ticker per strike, the slim ticker keys, and the fee terms from
  each instrument. v2 has been dead since 6 Oct 2026.
- Opening is live through Butler's `acp options` rail: `acp options account` to read
  the Derive account, `acp trade` to bridge USDC from Base to Ethereum,
  `acp options deposit`, `acp options open` and `acp options withdraw`, each an
  approval card the owner signs in the app. The helper has no money path left.
- The quote carries the open's bounds: `min_premium_usd` (95% of the net premium,
  rounded down) and `collateral.amount` in the unit `--max-collateral` takes (USDC for
  a put, the asset for a call), plus `collateral.usd`.
- The `options-lifecycle@2` duty is filed only after a confirmed fill, with the fill's
  own size and net premium.
- Removed `spikes/`: v3 has no session key to register, and funding goes through the
  rail.

## 0.1.0

- First prototype. Screens and quotes fully collateralised single-leg notes
  (cash-secured put, covered call) against Derive's public API.
- Quote-time liquidity gating instead of an asset allowlist: a note is offered only
  when the bid is within 5 vol points of mark, fees are under 15% of the premium,
  and the best bid covers the whole note. On a measured day that clears ETH and BTC
  and rejects the other ten listed assets.
- Monthly tenors by default. Weeklies lose ~15% of the premium to fees at $5,000 and
  far more below that, so the fee-drag gate rejects them at retail size.
- Money paths (`open`, `close`, `positions`, `withdraw`) refuse with an explanation
  until spikes A1 and A4 pass.
