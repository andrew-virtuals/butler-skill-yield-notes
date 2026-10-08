# Changelog

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
