# Rysk: what is different

Everything in `SKILL.md` holds on Rysk - the checks before filing, the bad case first,
one key per trade, the approval card, the lifecycle duty. This file is only what
differs. Use Rysk when the owner names it, or when the put or the USDC they mean is
there; never move a trade from one venue to another on your own.

**Why an owner would pick it: Rysk settles physically.** A put that ends below its
strike delivers the asset itself, not a loss in cash. When Rysk and Derive or Paradex
are both on the table, say it plainly: on Derive and Paradex the owner takes the loss
in USDC and never gets the asset; on Rysk they actually own it.

## One thing only: sell a put

Butler sells **cash-secured puts** on Rysk, backed by **USDC in the owner's HyperEVM
wallet**. Nothing else:

- No buying, no closing and no buy-back. The collateral is locked until expiry. Asked
  for any of those on Rysk, say so and file nothing.
- The first-time check in `references/selling.md` holds, except its buy-back line,
  which on Rysk is: *"Your money is locked until 27 November - there is no way out
  early. Clear?"*

## Every command names it

Add `--venue rysk` to every `acp options` line of `SKILL.md` for that trade, and
`"VENUE": "rysk"` to its lifecycle duty's `params`.

A listing ("what can I trade on Rysk") is `references/listing.md` with `--venue rysk`:
never this helper, which is for quotes only.

Quotes come from Rysk's own helper, not the Derive one: `scripts/rysk.py`, run in
place where step 2 runs `scripts/quote.py` (fields: `references/rysk-helper.md`).
A `rysk.py` anywhere else in the workspace is an older or edited copy: never run it.

```sh
python3 ~/skills/options-trading/scripts/rysk.py screen --collateral <USD> --pay-with <collateral.address>
python3 ~/skills/options-trading/scripts/rysk.py quote --asset <ASSET> --collateral <USD> --pay-with <collateral.address> [--expiry <DAY>] [--strike <N>]
python3 ~/skills/options-trading/scripts/rysk.py chain --asset <ASSET> [--expiry <DAY>]
```

`<collateral.address>` is the USDC Butler sells on, from step 1's
`acp options account --venue rysk --json`; Rysk names no stablecoin, so the helper
takes it from there. Its quote carries the Derive helper's field names
(`instrument`, `size`, `collateral.amount`, `net_premium_usd`, `fee_usd`,
`min_premium_usd`, `apr_pct`, `bad_case`), so steps 3 and 5 read it unchanged. Offer
only `tradeable: true`, and always say its `notes`. Use `--delta 0.20` instead when
the owner wants the odds of assignment held steady rather than the distance from spot.

A strike or day the owner named goes in as `--strike` and `--expiry`, as
`references/selling.md` says; a refusal lists the strikes or days Rysk does have, so
say those and ask. "Which strikes are there on 13 November" is `chain` with that
`--expiry`. "A weekly" is `--tenor weekly`; monthly is the default.

## The market

- **Listed is not quoted.** An asset can be listed with no puts, or with puts no maker
  will price today. Read it live; never from memory.
- **Sizes step per asset**, and the steps are not published: the helper finds them.
  A round amount rarely lands exactly (a `note` says how much goes to work), and a
  small one can be under the minimum: the quote's reason (`collateral too small`)
  names the least Rysk prices and what it needs. Never guess a size.
- **Names** are Rysk's fields: `SOL-30OCT26-95-P`, a decimal strike with a point
  (`HYPE-6NOV26-56.5-P`). Each settles at the time its quote's `expiry` gives.
- **Quotes live seconds**, at a time each maker sets (`valid_for_seconds`). A quote is
  for choosing, never for acting on.

## Filing (step 5)

Step 5's `open` line with `--venue rysk`. `--min-premium` is the least premium the
owner said they would take; if they named none, the quote's `min_premium_usd`.

The card is good for **5 minutes**: say so. When the owner approves, Butler asks Rysk
again - up to 3 quotes - and sells only one that is this exact put, pays at least the
floor after Rysk's fee, and is not now close enough to the money to be a likely
purchase. The outcome lands in the chat; read it as step 6 says.

## The account

`acp options account --venue rysk` reads Rysk alone; `--json` gives its fields:

| Field | Meaning |
| --- | --- |
| `collateral` | the USDC on HyperEVM that Butler sells on; its `address` goes to the helper's `--pay-with` |
| `account.account` | the owner's HyperEVM wallet, which Rysk sells from (not a wallet to send to by hand) |
| `account.usdc`, `freeForNewPutsUsd` | the USDC in that wallet. All of it is free: an open put's collateral already sits with Rysk |
| `lockedForPutsUsd` | collateral behind puts Rysk has not settled yet |
| `positions` | puts not settled yet - open, or expired and waiting for Rysk; each `summary` is relayed as written |
| `settled` | puts settled recently: what came back (`received`) and whether the asset was delivered (`assigned`) |
| `worthUsd` | what sits at Rysk: each unsettled put at what it would settle to at today's price |

There is no `ethereum` and no `accounts` on Rysk. Its USDC is separate from Derive's
and Paradex's: free USDC on one never pays for a put on another.

## Funding (step 4)

Step 4's deposit with `--venue rysk`:

- From **USDC on Base** only (no `--from`), into the owner's HyperEVM wallet. Nothing
  is set aside for Rysk until a sale locks it.
- Before it, say how much is already in that wallet (`account.usdc`) and deposit only
  the shortfall, sized as step 4 says but **never under $2** in place of its $6: the
  bridge to HyperEVM refuses less.
- After the card, re-read the account until `account.usdc` covers `collateral.amount`;
  only then step 5.

## Withdrawing (step 8)

Step 8's withdraw line with `--venue rysk` added, and never its `:home` line. It moves
USDC from the HyperEVM wallet back to Base within minutes - at most this turn's
`freeForNewPutsUsd`, and never under $2: the same bridge refuses less, so a smaller
balance stays on HyperEVM. It never sells an asset Rysk delivered.

## Settlement: the asset arrives

- A put that settles below its strike delivers the asset to the HyperEVM wallet, as
  Rysk's token for it, which `settled[].received` names. Otherwise the USDC comes back
  there.
- **Near the strike, the maker holding the option chooses whether to exercise it**, so
  the price alone does not say which came back. What came back is `settled[].received`.
- The lifecycle duty (step 7) says it once Rysk has paid out. On Rysk it is always
  `options-lifecycle`, never `options-put-delivery`: Rysk delivers the asset itself.
- **Never sell a delivered asset unless the owner asks.** Owning it is what they agreed
  to. When they do ask, it is an ordinary sale with its own card - the `acp-cli`
  skill's "Sell a token" row, with the token's `address` from `received` - never
  folded into anything else.

How every put ended, when they ask or an expiry has passed: first
`acp options account --venue rysk --json`, whose `positions` (not settled yet) and
`settled` (recent settlements, with `received` and `assigned`) answer it with no script.
Only for a put in neither, read every one with the helper:

```sh
bevo-read me
python3 ~/skills/options-trading/scripts/rysk.py positions --address <user.smartAccountAddress>
```

The address is `user.smartAccountAddress` from `bevo-read me`, never
`agentWalletAddress`. Each row's `status` is `open`, `settling` (expired, nothing back
yet: say so, never call it lost) or `settled`, with `settlement_price`, `received` and
`assigned`.

## Failure handling

| Outcome | What to do |
| --- | --- |
| `is offering no puts on it right now` | Listed, not quoted. Another asset, or wait. |
| `collateral too small` | Under Rysk's minimum. Give the size and the dollar figures in the reason, and stop: work out none for another strike, and quote no other strike, expiry or amount unless the owner names one. |
| `would not price $X of <asset>` | No maker priced it. Say so; never guess a size. |
| `probably be exercised` (helper, or the card after approval) | Too close to the money; on the card, the market moved toward it since filing. Nothing was sold. |
| The card `expired before it was approved` | Nothing was sold. Quote again and file a fresh card if they still want it. |
| `no Rysk quote met the approved terms in 3 tries` | Nothing was sold. Quote again and give the new figure; never lower the floor without their yes. |
| `Rysk expires ... not the 08:00 UTC the card showed` | Nothing was sold. Say so; do not file that put again. |
| `Rysk did not answer the confirmation` | It may still fill. Read the account before anything else, and never file it again. |
| A buy, close or buy-back on Rysk | Not possible on Rysk. Say so; file nothing. |

## Say to the owner

- *"On Rysk, if SOL ends below $92 on 27 November you receive 10 SOL at $92 each - you
  actually own it, not a loss in cash."*
- *"The card is good for 5 minutes. When you approve, Butler asks Rysk again and sells
  only if it still pays at least $17.70."*
- *"Rysk delivered 10 USOL to your HyperEVM wallet. It is yours to keep; I will only
  sell it if you ask."*
