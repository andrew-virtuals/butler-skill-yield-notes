# butler-skill-yield-notes

The `yield-notes` skill for [Butler](https://github.com/Virtual-Protocol/butler-skills).
For the humans maintaining this repo - never published to a butler. Only `SKILL.md`
and `references/**/*.md` reach one.

**Status: v1.2.0, built for Derive v3 and the `acp options` rail.** Not listable until
the hub's `acp options` support merges (see "Validating a change").

## What it does

Sells one fully collateralised option on [Derive](https://derive.xyz) so idle money
earns while it waits - a cash-secured put on USDC. v1 offers puts only: the rail
accepts a covered call only when the asset is already in the Derive account, and
deposits move USDC only. The helper still quotes calls, for screening. The model never picks an instrument, a strike
or a premium: it passes an intent to the helper and gets back a quote object with
every number fixed, including the bounds `acp options open` takes.

## How the pieces fit

| Piece | Where | Does |
| --- | --- | --- |
| Screen and quote | `references/helper.md`, run in the container with `python3` | Reads Derive v3's public, keyless API (`public/get_all_instruments`, `public/get_tickers`). Read-only. |
| Account read | `acp options account` | The owner's Derive account: free USDC, open positions, USDC on Ethereum, signer readiness. |
| Funding | `acp options deposit` | One approval card: bevo-server bridges Base USDC straight to the owner's own Derive deposit address (`--from 1` deposits USDC already on Ethereum). |
| Opening | `acp options open` | Files an approval card; bevo-server executes an IOC limit sell after approval, posts the outcome note and nudges the butler. |
| Outcome | `bevo-read request <key> --route options` | `approvalStatus`, plus `approvalOutcome` (`filledSize`, `netPremiumUsd`, `collateral`, …) or `approvalFailureReason`. |
| Withdrawing | `acp options withdraw`, then `acp trade` back to Base | Approval cards. |
| Watching to expiry | the `options-lifecycle@2` duty template | Filed by the skill only when `approvalStatus` is `confirmed`, with the numbers from `approvalOutcome`. |

The rail contract is bevo-server's `docs/derive-options.md`. bevo-server is the only
thing that signs: there is no session key and nothing in this repo touches a key.

## The gates, and why they exist

Derive lists options on twelve assets; on most days only ETH and BTC have books a
retail note can be sold into. So the helper screens at quote time instead of carrying
an allowlist. The gates are the same constants as bevo-server's reference quote
engine (`deriveQuote.ts`); keep them, and the `reasons` strings, in step:

| Gate | Default | Why |
| --- | --- | --- |
| `MAX_VOL_GAP_PTS` | 5.0 | ETH's and BTC's own spreads sit a few points wide. A 2-point guard rejects every fill. |
| `MAX_FEE_DRAG` | 15% | The $0.50 base fee is per order and uncapped; it swamps small notes and weeklies. |
| `MIN_PREMIUM_USD` | $1 | Below it the premium rounds to nothing. |
| bid depth >= note size | - | A note bigger than the best bid walks the book. |

Live check, mainnet, 7 Oct 2026 (13:22 UTC), $5,000 monthly put: ETH
`ETH-20261030-2300-P`, 2.17 contracts, $63.36 gross, $2.17 fee, $61.20 net, 19.7% APR,
edge -1.15 vol points; BTC `BTC-20261030-75000-P`, 0.06666 contracts, $28.10 net,
9.0% APR. The reference capture at 10:57 UTC ($55.76 net, 17.8%) is what the
examples in `SKILL.md` and `references/notes.md` use.

## Testing the helper

Extract the script from `references/helper.md` and run it against mainnet (or
`--testnet`):

```sh
python3 derive_helper.py screen --tenor monthly --collateral 5000
python3 derive_helper.py quote --product cash_secured_put --underlying ETH --collateral 5000
```

Against the reference fixture (`ETH-20261030-2300-P`, bid 26.7, mark 28.6, index
2578.7, bid IV 0.4834, mark IV 0.4962) it must give size 2.17, collateral 4991,
gross 57.94, fee 2.18, net 55.76, edge -1.28, breakeven 2273.3, APR ~17.83.

## Validating a change

```sh
curl -sSLO https://virtual-protocol.github.io/butler-skills/tools/validate.py
python3 validate.py --standalone .
```

This needs a hub validator that knows the `acp options` group (butler-skills branch
`feat/acp-options-group` until it merges); an older one reports each `acp options`
line as an unknown group.

## Releasing

Bump `version` in `SKILL.md`, add the `CHANGELOG.md` entry, merge to `main`. A
published `name@version` is immutable. Listing a skill is maintainer-only.
