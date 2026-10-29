# Changelog

## 2.8.1

- **"Sell the 2100 put on Rysk for 13 November" sells that put.** Rysk's quote had no
  way to name a strike or a day: it took the listed expiry nearest the tenor and the
  strike nearest 10% under spot, so 30 October and 13 November could never be quoted
  and a named strike only ever approximated, while `selling.md` says a named strike or
  day is quoted exactly or not offered. `rysk.py quote` now takes `--strike` and
  `--expiry`, as the Derive and Paradex helper does, refused with the strikes or days
  Rysk lists when it has no such put.
- **`rysk.py chain --asset ETH --expiry 2026-11-13`** lists one expiry's put strikes,
  each with its `delta` and `pct_otm`: the answer to "which strikes are there". No
  price, since Rysk only prices on request.
- `rysk.md` says `--tenor weekly` is how to ask for a weekly.
- **A Rysk deposit or withdrawal is never under $2.** Both ride `acp trade` between
  Base and HyperEVM, which refuses a move under $2; `rysk.md` sized a deposit as the
  bare shortfall with no floor, so a small one was filed only to be refused.
- **No Derive `:home` leg under $2.** It is the same `acp trade`, from Ethereum to
  Base; `account.md` now says a smaller arrival stays on Ethereum instead of filing a
  card that is refused after approval.

## 2.8.0

- **A duty that only watches no longer asks for a spending limit.** Seen in QA: a bought
  BTC call's lifecycle duty came with a "Set spending limit" card proposing $50, while
  the butler said it never spends. `options-lifecycle@9` carried the delivery buy for
  assigned puts (`DELIVER_ASSET`), and Butler marks a duty as spending from any `acp`
  money command in its code, reachable or not. Step 7 now files `options-lifecycle@10`,
  which runs no command, with `movesFunds: false`: no pocket and no card, for every
  bought option and every sold put without delivery.
- **Owning the asset after an assigned put is its own template.** When the owner asked
  for it in step 3, step 7 files `options-put-delivery@1` instead (`references/selling.md`):
  the same watch, plus the buy, with its pocket card opening on the collateral rather
  than $50. It never buys for a put missing from the account at the last check before
  expiry.
- **"What can I trade on Rysk" uses the listing, not the Rysk helper.** Seen in QA on
  2.7.3: the agent followed `rysk.md`'s command block, which still showed
  `python3 /tmp/rysk.py inventory`, began writing the 29 KB Rysk helper, and ended the
  turn after 1m41s without an answer; the line saying a listing is `listing.md` sat in
  the prose under it. No command block in `rysk.md`, `rysk-helper.md` or `helper.md`
  shows a whole-venue listing any more (`rysk.py inventory`, `derive_helper.py chain
  --venue paradex`), and `rysk.md` and `rysk-helper.md` say first that a listing is
  `listing.md`.

## 2.7.3

- **"Buy the 2100 put" buys the 2100 put.** Seen in QA: the agent quoted and offered
  `ETH-USD-13NOV26-2200-P`, the helper's 5%-OTM rule, because a quote had no way to name
  a strike; it then filed the 2100 with a `--max-cost` it worked out itself. A buy or
  sell quote takes `--strike`, refused with the listed strikes when the expiry has no
  such strike. `SKILL.md` step 2's sell and buy lines carry `--expiry` and `--strike`, and
  `buying.md` and `selling.md` pass a strike or day the owner named that way and offer no
  quote that differs from it.
- **"What can I trade on Paradex" no longer writes the quote helper.** Seen in QA: the
  answer took about 3.7 minutes, of which the API call was 1 second. The agent read the
  51 KB `helper.md` and wrote its 42 KB script out twice (a file tool that cannot write
  `/tmp`, then a heredoc), about 178 seconds of output. `references/listing.md` is the
  same list from a small script, in one shell command; `SKILL.md` sends a listing there
  and nowhere else.
- **Rysk too.** "What can I sell on Rysk" is `listing.md` with `--venue rysk` (the puts
  Rysk takes, by asset and expiry), not the 29 KB Rysk helper; and "how did my puts end"
  reads `acp options account --venue rysk` first, whose `settled` lists recent
  settlements, writing the helper only for a put in neither list.
- **No venue figure in what a butler reads.** Fees, minimums, size steps, the price
  band, expiry times, withdrawal times and fees, and which assets clear were written
  into the references as measured on 7-9 October, and one was already wrong (Derive
  charges nothing to open a subaccount, not $1). Each now points at the quote, account
  read, card or outcome that gives it live, except Derive's $10 minimum deposit and the
  ~$0.10 Base bridge, kept in `venue.md`; the measurements are in `README.md`, for
  maintainers. `screen` screens what each venue lists now instead of a fixed list, and
  the listing's example answer names no asset.
- **The helper ships as a ready-to-run block.** `helper.md`'s script is one
  `cat > /tmp/derive_helper.py <<'PYEOF'` shell command, as `listing.md`'s is, written
  once and reused, never with a file tool. The copy in QA had dropped the script's
  comments and renamed a variable; told so only in prose, the agent still used a file
  tool or retyped it with lines changed.
- `tests/test_listing.py`, run in CI, fails when `listing.md`'s ticker table differs from
  the helper's.

## 2.7.2

- Files `options-account@3`: a Rysk put is listed on its Platforms row, with no value, the
  premium received and its collateral, and a Paradex row lists its free USDC first as
  `Cash`. Step 9 updates a duty on `@1` or `@2`, or a fork of one, in place, unasked.

## 2.7.1

- Files `options-account@2`: one Platforms row per Derive subaccount (`PRIME`, `RWA`),
  each at its own worth with its cash and positions, replacing the one row that merged
  them. Step 9 updates a duty still on `@1` in place, unasked.
- **The helper names what each ticker is.** `chain` with no `--underlying` now gives each
  underlying a `name` and a `kind` (`crypto`, `stock`, `etf`, `index`, `commodity`) from a
  list in the helper of every underlying Derive and Paradex list today. Neither venue's
  API names a ticker, and Paradex tags its stocks, indices and commodities alike as
  `RWA`. Seen in QA: told to say the ticker alone, the agent guessed instead - MU as
  "e.g. MUFG", SPCX as "an SP/ETF index ticker", CL as a stock. They are Micron, SpaceX
  and WTI crude oil. A ticker the list does not know comes back `null` and is said by
  ticker alone; the list is never filled by searching a ticker (Pyth's CL is
  Colgate-Palmolive).
- **A Paradex option's expiry is the market's, not its name's.** A Paradex name gives only
  the day, and everything read 08:00 UTC into it; a stock, index or commodity option
  expires at its market's close instead (META 20:00 or 21:00 UTC, CL 18:30 or 19:30).
  `references/paradex.md`, `helper.md` and `buying.md` now say so, and step 7 files
  `options-lifecycle@9`, which takes the expiry Paradex states. Butler's server states it
  on the card, the account's positions and the ticker.
- **A day the owner names is quoted on that day.** `quote` and `chain` take
  `--expiry YYYY-MM-DD`, and each `chain` row names its `expiry`. Seen in QA: asked for
  an ETH call "expiring this Friday", the agent read `chain --underlying ETH`, which shows
  only the tenor's one expiry (13 November), and told the owner Paradex had no 30 October
  expiry, though its own listing showed one. "Weekly" aims 9 days out, so a Friday 4 days
  away could not be reached at all.

## 2.7.0

- **Rysk, as a third venue.** Selling a cash-secured put on Rysk is the same procedure as
  on Derive and Paradex with `--venue rysk`: the checks, the
  bad case first, one key, the card, the lifecycle duty. `references/rysk.md` is only
  what differs - puts only, no buy-back, USDC in the owner's HyperEVM wallet, a card good
  for 5 minutes that the server re-quotes against the floor, and **physical
  settlement**: an assigned put delivers the asset, which is never sold unless the owner
  asks. Replaces the separate `rysk` skill (`mamamatcha/butler-skill-rysk`, deprecated),
  so an owner installs one skill for all three venues.
- `references/rysk-helper.md`: Rysk's quote script, now speaking the Derive helper's
  field names (`net_premium_usd`, `fee_usd` from Rysk's `/api/gas`, `min_premium_usd`,
  `bad_case`), so `SKILL.md` steps 3 and 5 read either. Rysk names no stablecoin and a
  skill may carry no address, so the collateral comes from the account read
  (`collateral.address`, passed as `--pay-with`).
- Files `options-lifecycle@8`, which reads exactly as @7 for Derive and Paradex and adds
  `VENUE: rysk`, reporting what Rysk actually paid out.
- `templates/options-lifecycle` 8: Rysk names, no early-close check or delivery buy on
  Rysk, and the outcome from `settled` in `/options/account` rather than from the price,
  since near the strike the maker chooses whether to exercise.
- CI validates `templates/options-account`; it still named `derive-account`, removed in
  2.6.0, so every run since failed.

## 2.6.2

- **What a venue lists comes from the helper.** `chain` with no `--underlying` lists every
  underlying the venue has order-book options on, with its expiries (ISO, UTC), from one
  read of the venue's market list (Derive: its option currencies). Seen in QA: asked
  "what stock options can I trade on Paradex", an agent answered from web docs, wrote
  Paradex's symbols in Derive's form (`META-USD-20261130-650-C`) and named `MU`
  "Mitsubishi UFJ Financial Group". SKILL.md step 2 now names the listing, and names are
  said as listed, never with a company name (no venue gives one). `references/paradex.md`
  notes that Paradex's list includes stocks, indices and commodities.
- Check 4 of "Never file without all four" is the **helper's** quote: in the same test the
  agent filed a buy priced from Paradex's raw mark, with no quote at all.
- To stay under 12,000 characters: the `"title"` line in step 7 is dropped (the JSON there
  already carries one) and step 6's pointer to `references/paradex.md` is shorter.

## 2.6.1

- **Derive's minimum deposit is $10, not $5.** Derive's docs now say a deposit worth less
  than $10 is not credited and goes to its Security Module, and Butler's server refuses
  under $10. `references/venue.md` names $10 alone: the $5.05 bridge floor and the
  "never send under $6" line are gone.

## 2.6.0

- **Paradex, a second venue.** Every command takes `--venue paradex` (bevo-server's options
  rail is venue-neutral: `docs/options-venues.md`). New `references/paradex.md`: names
  (`ETH-USD-27NOV26-2600-C`), the $20-of-underlying minimum, Paradex's retail fee and
  price band, order-book markets only, the account fields (`address`, `otherPositions`),
  funding from Base USDC only, and withdrawing to Base.
- The helper reads Paradex with `--venue paradex` (any command): Paradex's market list
  and summaries, reshaped into Derive's fields so the quote logic, its gates and every
  field are the same; RFQ-only markets are skipped, fees follow Paradex's retail
  schedule (Butler's orders are retail), and a side priced outside the market's price
  band is dropped, since no order can reach it. Derive's output is byte-identical
  (replayed against the same Derive answers through 2.5.0's script and this one).
- SKILL.md: a venue rule (Before you start, 6); the lifecycle duty is `options-lifecycle@7`
  with `VENUE`; step 9 files one `options-account` duty for every venue; one failure row for every
  `OPTIONS_*` refusal, whose reply now carries the server's `hint`; the helper lines drop
  flags that were their defaults, to stay under 12,000 characters.
- `templates/options-lifecycle` 7: `VENUE`, Paradex names, settlement read by instrument.
- **One Platforms duty for every venue.** New `templates/options-account` 1: one duty per
  owner reads bevo-server's `/options/account` once and keeps a row for each venue whose
  account exists (Derive and Paradex), at the venue's own `worthUsd`, with its positions
  listed and the row's name and site from the read. A venue bevo-server adds appears on
  the next check, with nothing refiled. It keeps Derive's deposit-landed note, only for a
  venue with `depositsLandLater`. Step 9 files it whenever an account exists and it is
  missing, unasked, and deletes any `derive-account` duty, which it supersedes. Needs
  bevo-server's `worthUsd` and `depositsLandLater` (bevo-server#1179).
- **`templates/derive-account` removed.** `options-account` supersedes `derive-account@1`,
  so the registry resolves that ref to it; a duty already running it keeps its stored code
  and writes the same Derive row until step 9 replaces it. Its last copy is at `v2.4.0`.
- **Paradex withdrawals.** `acp options withdraw --venue paradex` pays to the owner's
  wallet on Base through Layerswap, usually within a minute, less a few cents; no
  `:home` leg (`references/paradex.md` § Withdrawing).

## 2.5.0

- **Options outside ETH and BTC trade.** Derive splits its markets into risk universes
  (PRIME: ETH, BTC; ALT: SOL, XRP, ADA, ZEC…; MIDCAP: HYPE; RWA: gold), and an account
  trades only its own. Every SOL attempt failed as `Zero liquidity … (11009)` because the
  owner's only account was PRIME. Butler's server now opens the owner's account in the
  option's universe on first use and moves just the USDC a trade needs into it after the
  card is approved (bevo-server: risk-universe funding). The skill files the same commands;
  it does not move funds itself.
- `account.md`: free USDC and positions total every Derive account, `account.accounts`
  lists each, and a new section says what the server moves and when, and what to tell
  the owner (`funding` in the outcome, the card's `Account` line). Withdrawals take the
  total; the server gathers it first.
- `venue.md`: one subaccount per risk universe, and why the wrong one says 11009.
- SKILL.md: step 4 says free USDC spans the accounts and the server moves it; step 6
  relays `funding`; step 5's one-bound line shortened to stay under 12,000 characters.

## 2.4.0

- **Derive on the wallet's Platforms tab.** After a confirmed `acp options deposit`, and
  in step 1 whenever `account.exists`, the skill files the new `derive-account@1` duty
  once, if `duty_list` has none (new step 9; step 4 sends a deposit there once it
  lands, so the watcher is filed in the same turn). That duty keeps one Platforms row at what
  the account is worth, every 10 minutes, and tells the owner when a deposit lands.
  Butler never writes its own Derive watcher and never runs `bevo-platforms set` for
  Derive: the duty owns the row. Butler itself no longer explains `acp options` and
  follows a skill's own steps for a platform row (virtuals-agent#218).
- **Every duty has a `"title"`.** The container refuses a create without one, and step 7's
  JSON had none.
- **A second duty from the same template in one chat** names the earlier ones in
  `"alongside"`, or the container refuses it as a follow-up. A duty from another template,
  like the account watcher beside a per-position one, needs none.
- **The duty templates live here now**, under `templates/`, beside the skill that files
  them: `options-lifecycle` (moved from the deprecated `butler-skill-options-lifecycle`)
  and the new `derive-account`. The hub lists each with a `path` into this repo.
- Step 7 files `options-lifecycle@6` (was `@4`): an option closed early ends the duty
  whenever it was closed (`@5`), and its Duties row shows a status line (`@6`).
- `account.md`: the Platforms row belongs to the watcher duty and catches up within
  about 10 minutes, so a row behind the read is that delay.
- SKILL.md stays under 12,000 characters by dropping lines that say again what is said
  elsewhere: the failure rows "not enough free USDC" (step 4), "close larger than held"
  (the "they hold it" gate and step 2) and "Derive unreachable" (step 1 and
  `account.md`); step 1's field list, the position sign and Look's `summary` / `pnlUsd`
  (all in `account.md`); "buying back can cost more" (step 3's `result_usd`); and the
  withdrawal's route detail in step 8 (`account.md`).

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
