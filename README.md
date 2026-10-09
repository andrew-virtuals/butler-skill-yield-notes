# butler-skill-yield-notes (now `options-trading`)

The `options-trading` skill for [Butler](https://github.com/Virtual-Protocol/butler-skills),
formerly `yield-notes`. For the humans maintaining this repo - never published to a
butler. Only `SKILL.md` and `references/**/*.md` reach one.

**The repository name still says `yield-notes`.** The skill is `options-trading` from
2.0.0; the repo should move to `Virtual-Protocol/butler-skill-options-trading`, and the
hub's `skills.json` entry list it under the new name and repo. Until then this repo
serves it.

**Status: v2.0.0, built for Derive v3 and the `acp options` rail.** Selling needs the
hub validator that knows `acp options open|deposit|withdraw|account`; buying and
closing need the one that also knows `acp options buy|close` (see "Validating a
change").

## What it does

Three intents on [Derive](https://derive.xyz)'s options market:

- **Earn**: sell one fully collateralised cash-secured put on USDC, so idle money
  earns while it waits to buy the asset lower. Behaviour unchanged from yield-notes
  1.2.1. Covered calls come later: the rail accepts one only when the asset is already
  in the Derive account, and deposits move USDC only.
- **Buy**: buy one call or put outright. Not yield - the owner pays premium plus fee
  and can lose all of it; the skill gets an explicit yes to that number.
- **Close**: before expiry, sell back an option the owner bought, or buy back a note
  they sold. Buying back frees the collateral and can cost more than the premium.

The model never picks an instrument, a strike or a price: it passes an intent to the
helper and gets back a quote object with every number fixed, including the bound the
`acp options` command takes (`--min-premium`, `--max-cost`, `--min-proceeds`).

## How the pieces fit

| Piece | Where | Does |
| --- | --- | --- |
| Screen and quote | `references/helper.md`, run in the container with `python3` | Reads Derive v3's public, keyless API (`public/get_all_instruments`, `public/get_tickers`). Sell, buy and close quotes. Read-only. |
| Account read | `acp options account` | The owner's Derive account: network, free USDC, positions (positive size = bought), USDC on Ethereum, signer readiness. |
| Funding | `acp options deposit` | One approval card: bevo-server bridges Base USDC straight to the owner's own Derive deposit address (`--from 1` deposits USDC already on Ethereum). |
| Selling | `acp options open` | Approval card; an IOC limit sell after approval. |
| Buying | `acp options buy --max-cost` | Approval card; an IOC limit buy whose premium plus fee stays within `--max-cost`. |
| Closing | `acp options close --min-proceeds` or `--max-cost` | Approval card; an IOC `reduce_only` limit sell of a bought position, or limit buy of a sold one. |
| Outcome | `bevo-read request <key> --route options` | `approvalStatus`, plus `approvalOutcome` (`filledSize`, `netPremiumUsd` / `totalCostUsd` / `netProceedsUsd`, …) or `approvalFailureReason`. |
| Withdrawing | `acp options withdraw`, then `acp trade` back to Base | Approval cards. |
| Watching to expiry | the `options-lifecycle@4` duty template | Filed only when `approvalStatus` is `confirmed`, from `approvalOutcome`: `cash_secured_put`, `long_call` or `long_put`. Deleted after a confirmed close. |

The rail contract is bevo-server's `docs/derive-options.md`. bevo-server is the only
thing that signs: there is no session key and nothing in this repo touches a key.

## The gates, and why they exist

Derive lists options on twelve assets; on most days only a few have books a retail
trade can cross. So the helper gates at quote time instead of carrying an allowlist.
The sell gates are the same constants as bevo-server's reference quote engine
(`deriveQuote.ts`); keep them, and the `reasons` strings, in step:

| Gate | Default | Side | Why |
| --- | --- | --- | --- |
| `MAX_VOL_GAP_PTS` | 5.0 | both | Bid under mark (sell) or ask over mark (buy). ETH's and BTC's own spreads sit a few points wide; a 2-point guard rejects every fill. |
| `MAX_FEE_DRAG` | 15% | both | The $0.50 base fee is per order and uncapped; it swamps small tickets and weeklies. |
| `MIN_PREMIUM_USD` | $1 | sell | Below it the premium rounds to nothing. |
| depth >= size | - | both | Best bid (sell) or ask (buy) must cover the whole size, or it walks the book. |
| `MAX_COST_HEADROOM` | 1.05 | buy | `max_cost_usd` is the total cost plus 5%, and a budget buy is sized so that ceiling fits inside the budget. |

A close is refused only with no bid, a bid thinner than the size, or a fee larger
than the proceeds; a buy-back only with no ask or an ask thinner than the size. A wide
market is a warning, since an owner cutting a loss may accept it.

Live checks, mainnet:

- Sell, 7 Oct 2026 13:22 UTC, $5,000 monthly put: ETH `ETH-20261030-2300-P`, 2.17
  contracts, $61.20 net, 19.7% APR, edge -1.15 vol points; BTC `BTC-20261030-75000-P`,
  $28.10 net, 9.0% APR. The 10:57 UTC capture ($55.76 net) is what the selling
  examples use.
- Buy, 9 Oct 2026 04:59 UTC, $200 monthly ETH call 5% out of the money:
  `ETH-20261030-2600-C`, 2.95 contracts, $187.33 + $2.70 fee = $190.03, max cost
  $199.54, breakeven $2,664.42 - the capture the buying examples use. More in
  `references/venue.md`.

## Testing the helper

Extract the script from `references/helper.md` and run it against mainnet:

```sh
python3 derive_helper.py screen --tenor monthly --collateral 5000
python3 derive_helper.py quote --product cash_secured_put --underlying ETH --collateral 5000
python3 derive_helper.py quote --side buy --product call --underlying ETH --budget 200
python3 derive_helper.py quote --side buy --product put --underlying BTC --budget 200 --delta 0.3
python3 derive_helper.py quote --side close --instrument ETH-20261030-2600-C --size 1
python3 derive_helper.py quote --side buyback --instrument ETH-20261030-2300-P --size 0.1 --premium-received 3
```

Against the reference fixture (`ETH-20261030-2300-P`, bid 26.7, mark 28.6, index
2578.7, bid IV 0.4834, mark IV 0.4962) the sell quote must give size 2.17, collateral
4991, gross 57.94, fee 2.18, net 55.76, edge -1.28, breakeven 2273.3, APR ~17.83.
The sell quote's output is byte-for-byte what 1.2.1 printed (checked live against the
old script for ETH and BTC).

## Validating a change

```sh
curl -sSLO https://virtual-protocol.github.io/butler-skills/tools/validate.py
python3 validate.py --standalone .
```

This needs a hub validator that knows the `acp options` group, including `buy` and
`close` as money commands (butler-skills branch `feat/options-buy-close` until it
merges); an older one does not count them as money.

## Releasing

Bump `version` in `SKILL.md`, add the `CHANGELOG.md` entry, merge to `main`. A
published `name@version` is immutable. Listing a skill is maintainer-only; 2.0.0 is a
new name, so it is a new listing, and `yield-notes` should be de-listed with it.
