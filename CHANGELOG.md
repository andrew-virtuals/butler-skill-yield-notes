# Changelog

## 2.3.2

- **Sizes are in the asset.** 1 contract is 1 ETH: 0.16 is 0.16 ETH, and Derive's 0.1
  is only its minimum. Owners hear sizes as "0.16 ETH", never "contracts", and the
  agent never converts. Seen live: told "sell 5 of my ETH calls", an agent said
  "five contracts would be 0.5 ETH", while cards and duties count 1 contract as 1 ETH.
- **Derive figures come only from this turn's reads**, never memory: a stored note
  that disagrees with `acp options account` is wrong and gets corrected. The "0.5 ETH"
  came from the agent's own working memory, saved in an earlier session as something
  the owner had "clarified".
- **Positions are relayed, not priced.** `acp options account` now gives each position
  an owner-ready `summary` plus `valueUsd`, `costUsd`, `pnlUsd` and `expiresIn`, with the
  per-unit prices renamed `markPerUnitUsd` and `entryPricePerUnitUsd` (bevo-server and
  virtuals-agent changes that ship with this). `account.md` relays `summary` as written,
  answers "up or down" from `pnlUsd`, and never works out a value, profit or date. Seen
  live: "marked at ~$20.69" for a 0.16 ETH position worth about $3.30. Replays with a
  poisoned memory: account checks right 8 of 8 with the new fields; without `pnlUsd`,
  agents asked "up or down" computed it themselves and one flipped the sign of a whole
  position. On an older server, sizes are said in the asset and `mark` labelled per ETH.
- SKILL.md drops lines `account.md`, step 1 and the failure table already carry, to
  stay under 12,000 characters.

## 2.3.1

- **Selling says the bad case first, with a dollar figure.** The sell quote gains
  `bad_case`: the asset 25% below spot (`price`, `fall_pct`) and `loss_usd`, what the
  note is down at expiry there, premium counted. The skill forbids computing numbers,
  and no field carried a loss, so agents dropped the loss example and led with APR.
  `selling.md`'s four beats now open with the bad case (they used to put it third,
  against SKILL.md); `apr_pct` comes last, if at all.
- **The ownership question stands alone, and a no ends it.** "Happy to own 0.13 ETH at
  $2,200 on 30 October?" is asked on its own after the offer. A no, a "maybe", or a
  yes to the money with a no to the asset ends selling: no other strike, tenor, size
  or asset, since every cash-secured put carries the same promise. Seen in testing:
  told no to owning ETH, an agent offered quarterly ETH puts.
- `screen` is never shown as an APR menu; with more than one tradeable asset, the
  owner names the one they would own.
- **Never file without all four**, a gate in Before you start that every `acp options
  open`, `buy` or `close` must pass, from the owner's own words: they chose it (asset
  and amount, or option and size), they hold it (a close is at most `positions`' size),
  they said yes to the number (loss, ownership, floor or ceiling, with its dollar
  figure), and the quote is fresh (re-quoted after their last answer). Seen in
  testing: told "just buy whatever ETH call looks good", an agent made up a $10 budget
  and quoted the default strike; told "sell 5 of my ETH calls" with 0.16 held, it
  filed 0.16 at a floor it chose, on a 91-second-old quote, never saying 5 was more
  than held.
- Closing asks for the floor or ceiling, with `min_proceeds_usd` / `max_cost_usd` as
  the suggestion, instead of using it unless the owner names one. `buying.md` gains
  "Choosing is theirs" (no picking, no made-up budget, the strike rule said as a
  starting point; the loss figure goes in the question itself) and a size check
  before any close.
- A close that does not fill is "nobody bought at that floor", never "no liquidity",
  and is re-quoted, never re-filed at the same floor. Seen in testing: three
  sell-backs at a $4.05 floor above the bid failed and were reported as zero
  liquidity. `no live bid` on a close says holding to expiry costs nothing.
- Step 5 opens with "run the quote again now, after their last answer", and selling
  quotes the asset the owner named, screening only when they named none. Found by
  replaying the test prompts against this skill: an agent filed from its pre-answer
  quote, and one screened every asset after the owner had said ETH.
- The gate covers `acp options deposit` too, and step 4 funds only with all four met:
  in a replay an agent took "yes to all, go ahead" after the first-time check as
  approval and filed a $307 deposit without asking the ownership question. `selling.md`
  says those yeses are not a yes to a trade, and that a no to owning the asset is not
  followed by an invitation to name another.
- Step 7's `duty_create` example uses placeholders; an agent had taken its real-looking
  `SOL-20261030-160-C` for a holding and tried to close it. The `DELIVER_ASSET` token
  rules moved to `selling.md`; SKILL.md trims repeated limits and funding detail
  (still in `venue.md`) to stay under 12,000 characters.

## 2.3.0

- Routes more check and withdraw asks here, on top of 2.2.1's **Look or withdraw**:
  keywords `derive positions`, `my option positions`, `withdraw from derive`, `withdraw
  my free usdc`, and a description that names checking and withdrawing, so an installed
  skill is picked for them too. "Free USDC" is Derive's `freeForNewPutsUsd`, not wallet
  cash; a look is step 1 and then stop.
- The Derive portfolio comes from `acp options account` and only from it. `bevo-read
  assets` has no Derive section: its `perps` is Hyperliquid and its `cashUsd` the wallet.
  A butler had reported Derive as empty from Hyperliquid's $0 while the account held
  $1.62 free and four options. Step 1 now reads the account first, and the wallet only
  to fund a trade.
- A withdrawal is at most this turn's `freeForNewPutsUsd`, rounded down to the cent; the
  owner hears the up-to-$1 fee before it is filed.
- New `references/account.md`: what each `acp options account` field means, how to answer
  a check, the withdrawal rules, and worked sentences.
- Some wording in steps 4 to 7 is shorter, with the same rules, to keep the body under the
  hub's 12,000-character limit.

## 2.2.1

- A fourth case, **Look or withdraw**: "what's my free USDC in Derive", "list my
  positions", "withdraw my free USDC" are answered from `acp options account` and
  step 8. Derive money is never in `bevo-read assets`, and a withdrawal is `acp
  options withdraw`, never an `acp trade`. Seen live: asked to withdraw, an agent
  without this skill loaded traded Base USDC for Base USDC and called it done, then
  read Hyperliquid's $0 as the Derive balance. Keywords gain `withdraw`, `derive`,
  `options account`, `options positions`, `free usdc`.

## 2.2.0

- Every asset Derive lists options on, not only ETH and BTC. The lifecycle duty is
  `options-lifecycle@4`, which reads Derive's own index for the heads-up, so a trade
  files it with no `TOKEN_ID`. The token pin is filed only with `DELIVER_ASSET`, when
  the owner asked to own the asset after an assigned put.

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
