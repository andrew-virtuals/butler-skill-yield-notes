# options-trading

The `options-trading` skill for [Butler](https://github.com/Virtual-Protocol/butler-skills):
selling cash-secured puts, buying calls and puts, and closing them on **Derive**,
**Paradex** and **Rysk**, through Butler's `acp options` rail. This README is for the
people maintaining the repo. A butler receives `SKILL.md`, `references/**/*.md` and
`scripts/**/*.py`; the registry also serves the duty templates under `templates/`.

- **Version:** 2.9.0 (`SKILL.md`), with `options-lifecycle` 10, `options-put-delivery` 1
  and `options-account` 3.
  What changed in each release: `CHANGELOG.md`.
- **Registry name:** `options-trading`, listed in the hub's `skills.json` from this repo.
  The skill was `yield-notes` before 2.0.0, which is why the repository still has that
  name.

## What it does

An owner asks for one of four things, and the skill takes it from quote to approval card
to outcome:

- **Earn:** sell one fully collateralised cash-secured put on USDC. The owner keeps the
  premium and may end up buying the asset at the strike.
- **Buy:** buy one call or put outright. This is not yield: the owner pays premium plus
  fee and can lose all of it, and the skill gets an explicit yes to that figure.
- **Close:** before expiry, sell back an option the owner bought, or buy back a put they
  sold. Buying back frees the collateral and can cost more than the premium.
- **Look or withdraw:** read the venue account (free USDC, positions) and withdraw free
  USDC to the owner's wallet.

Not covered: covered calls, spreads, leverage, and any trade the helper refuses.

## Venues

| | Derive | Paradex | Rysk |
| --- | --- | --- | --- |
| Sell a put | yes | yes | yes |
| Buy, close, buy back | yes | yes | no: the collateral is locked to expiry |
| Underlyings | crypto, and XAUT (tokenized gold) | crypto, stocks, indices, commodities | per Rysk's live inventory |
| Quotes from | `scripts/quote.py` (public order book) | `scripts/quote.py` with `--venue paradex` | `scripts/rysk.py` (an RFQ) |
| Deposit | from any chain, bridged (`--from 1` for USDC on Ethereum); credited a few minutes after its card | USDC on Base, usually credited within minutes | USDC on Base, into the owner's HyperEVM wallet |
| Withdraw | to Ethereum (about 20 min), then `acp trade` to Base | to Base through Layerswap (about a minute) | from HyperEVM back to Base |
| Settles | cash (USDC), 08:00 UTC | cash (USDC): crypto at 08:00 UTC, other options at their market's close | **physically**: an assigned put delivers the asset |
| What differs | `references/venue.md`, `account.md` | `references/paradex.md` | `references/rysk.md` |

Derive is used unless the owner names a venue or already holds the position there. Every
helper and `acp options` line for a trade then carries `--venue paradex` or
`--venue rysk`, as does its lifecycle duty's `VENUE` setting.

## How the pieces fit

| Piece | Where | Does |
| --- | --- | --- |
| Quotes | `scripts/quote.py` (Derive, Paradex) and `scripts/rysk.py` (Rysk), run in place with `python3 "$HOME/skills/options-trading/scripts/<script>.py"`; fields in `references/helper.md` and `rysk-helper.md` | Read-only and keyless, against each venue's public API. Lists what a venue trades (`chain`, with each underlying's `name` and `kind`), and prices sells, buys, closes and buy-backs with every bound already worked out. |
| Account | `acp options account` | Every venue at once, or one with `--venue`: free USDC, positions (positive size is bought), each account's worth, and whether Butler's signer is ready. |
| Funding | `acp options deposit` | One approval card. |
| Trading | `acp options open`, `buy`, `close` | One approval card each. After approval the order is an immediate-or-cancel limit order, inside the bound on the card (`--min-premium`, `--max-cost`, `--min-proceeds`). Rysk's card is good for 5 minutes and is re-quoted against its floor. |
| Outcome | `bevo-read request <key> --route options` | `approvalStatus`, then `approvalOutcome` (the fill) or `approvalFailureReason`. |
| Withdrawing | `acp options withdraw` | One approval card. A Derive withdrawal also takes an `acp trade` home to Base. |
| Watching to expiry | the `options-lifecycle@10` duty, `templates/options-lifecycle/` | Filed only after a confirmed open or buy, from the fill. Sends a heads-up the day before expiry and the outcome once the option settles. Runs no command, so it is filed with `movesFunds: false` and no pocket. Deleted after a confirmed close. |
| Owning the asset after an assigned put | the `options-put-delivery@1` duty, `templates/options-put-delivery/` | Filed instead of `options-lifecycle`, for a sold Derive or Paradex put, only when the owner asked before the open to end up owning the asset. Watches the same way, then buys the asset with `acp trade` if the put is assigned. The only options duty with a pocket. |
| Platforms rows | the `options-account@3` duty, `templates/options-account/` | One per owner, filed unasked once any venue account exists. The only writer of the options rows on the wallet's Platforms tab: one row per venue, and one per Derive subaccount, each at the venue's own worth with its positions listed. |

## Safety model

- **The model never picks a number.** It passes an intent (side, product, asset, money,
  tenor or date, a strike rule) to the helper and offers only the fields of a quote that
  is `tradeable: true`. A refused quote's `reasons` are told as written.
- **Four checks before anything is filed** (`SKILL.md`): the owner chose it, they hold
  what they are closing, they said yes to the dollar figure, and the quote was taken
  after their last answer.
- **Nothing here signs.** Butler's server builds every venue action, checks it against
  the bound the owner approved on the card, and signs with the owner's wallet. The repo
  has no session key and no secret.
- **One idempotency key per trade**, never re-sent. An unclear answer is looked up with
  `bevo-read request`.
- **Full collateral.** A put's size is what the collateral fully covers; none of the
  venues' margin is used.

## The gates

The helper gates at quote time instead of keeping an allowlist, because on most days only
a few books can be crossed by a retail-sized trade:

| Gate | Default | Side | Why |
| --- | --- | --- | --- |
| `MAX_VOL_GAP_PTS` | 5.0 | both | Bid under mark (selling) or ask over mark (buying). ETH's and BTC's own spreads are a few points wide; a 2-point guard would reject every fill. |
| `MAX_FEE_DRAG` | 15% | both | Derive's $0.50 base fee is charged per order and is uncapped, so it swamps small tickets and weeklies. Paradex charges no base fee. |
| `MIN_PREMIUM_USD` | $1 | sell | Below it the premium rounds to nothing. |
| depth ≥ size | - | both | The best bid (selling) or ask (buying) must cover the whole size, or the order walks the book. |
| `MAX_COST_HEADROOM` | 1.05 | buy | `max_cost_usd` is the total cost plus 5%, and a budget buy is sized so that ceiling fits inside the budget. |

These match Butler's server's reference quote engine; keep the constants and the
`reasons` strings in step with it. A close is refused only with no bid, a bid thinner
than the size, or a fee larger than the proceeds; a buy-back only with no ask or an ask
thinner than the size. A wide market is a warning there, since an owner cutting a loss
may accept it. On Paradex a price outside the market's price band counts as no price.
Rysk's helper has its own gates (`references/rysk-helper.md`).

## Measurements

Apart from Derive's $10 minimum deposit and the Base bridge's ~$0.10 (in
`references/venue.md`), nothing a butler reads states a venue figure: fees, minimums,
sizes, times and which assets clear come from the quote, the account read, the card or
its outcome, so they cannot go stale in the skill. What was measured, for the people tuning the gates, is
here only; re-measure before relying on a spread or a depth.

Derive v3 mainnet, 7 October 2026 (selling) and 9 October 2026 (buying):

- **Fees:** $0.50 + min(0.03% of index notional, 12.5% of mark value) per order, matched
  to a live fill to the cent. Paradex retail orders paid no option fee.
- **Minimums:** ETH 0.1 contracts on a 0.01 step (~$230 of collateral at a ~10% OTM
  monthly strike), BTC 0.01 on 0.00001 (~$750). A 5% OTM monthly ETH call cost about
  $7.40 at the minimum, where the base fee was about 9% of the premium. Paradex: $20 of
  the underlying per order, a 40% price band around the mark, and 5 USDC or 0.001 ETH in
  the wallet to open an account.
- **Funding:** Derive's minimum deposit $10 and the direct Base bridge's ~$0.10, both also
  kept in `references/venue.md`, where the agent sizes a deposit; an Ethereum deposit credited about 2 minutes after it is mined. A withdrawal took 17
  minutes, less a fee capped at $1; the `:home` trade had a $2 minimum and a fee of
  max($1, 0.5%). Opening a new Derive subaccount cost nothing.
- **Margin:** a put needing $250 drew about $35 of Derive margin.
- **$5,000 monthly put, ~10% OTM, 7 October:** ETH-20261030-2300-P, 2.17 contracts,
  $57.94 gross, $2.18 fee, $55.76 net, ~17.8% a year, edge -1.28 vol points. BTC
  tradeable at ~7.6% a year; the other ten refused (no bid, spread over 5 points, a bid
  thinner than the note, or fees over 15%). HYPE cleared by 13:20 UTC (edge -1.8).
- **$200 budget, monthly, ~5% OTM, 9 October 05:05 UTC:** ETH call
  ETH-20261030-2600-C 2.91 contracts, $190.07 (max cost $199.58, breakeven $2,665.32,
  ask 1.03 vol points over mark); ETH put ETH-20261030-2350-P 3.5 contracts, $190.36
  (0.77 over); BTC call BTC-20261030-86000-C $190.48; BTC put BTC-20261030-78000-P
  $190.47. XRP's call was refused at 11.5 vol points over mark, and an $8 weekly ETH call
  at 16% fee drag.
- Derive v2 (`api.lyra.finance`) has been dead since 6 October 2026.

## Testing the helpers

Run them from the repo against mainnet:

```sh
python3 scripts/quote.py chain                                    # what Derive lists
python3 scripts/quote.py chain --venue paradex                    # with name and kind
python3 scripts/quote.py screen --collateral 5000
python3 scripts/quote.py quote --product cash_secured_put --underlying ETH --collateral 5000
python3 scripts/quote.py quote --side buy --product call --underlying ETH --budget 200
python3 scripts/quote.py quote --venue paradex --side buy --product call --underlying ETH --budget 10 --expiry 2026-11-27
python3 scripts/quote.py quote --side close --instrument ETH-20261127-2600-C --size 1
python3 scripts/quote.py quote --side buyback --instrument ETH-20261127-2300-P --size 0.1 --premium-received 3
```

Check these by hand after any change to the helper:

- `chain` with no `--underlying` has a `name` and `kind` for every underlying both
  venues list, and prints exactly what `scripts/options_list.py` prints for
  each venue. The two carry the same `KNOWN` table, so change both together;
  `tests/test_listing.py` fails CI when they differ. A `null` is a ticker missing from `KNOWN`. Add it from the venue's own
  documentation, never from a search on the ticker: Pyth's `CL` is Colgate-Palmolive.
- `--expiry` on a date the venue does not list is refused with the dates it does.
- `--strike` quotes exactly that strike, and one the expiry does not list is refused
  with the strikes it does. Without it the strike rule is unchanged.
- Against the reference fixture (`ETH-20261030-2300-P`, bid 26.7, mark 28.6, index
  2578.7, bid IV 0.4834, mark IV 0.4962) the sell quote gives size 2.17, collateral 4991,
  gross 57.94, fee 2.18, net 55.76, edge -1.28, breakeven 2273.3 and APR about 17.83.

`scripts/rysk.py` runs the same way: `inventory`,
`screen --collateral <USD> --pay-with <address>`, `quote --asset <ASSET> ...`, and
`chain --asset <ASSET>` for one expiry's put strikes. `--expiry` and `--strike` behave
as they do above.

## Validating a change

```sh
curl -sSLO https://virtual-protocol.github.io/butler-skills/tools/validate.py
python3 validate.py --standalone .
python3 validate.py --standalone templates/options-lifecycle
python3 validate.py --standalone templates/options-put-delivery
python3 validate.py --standalone templates/options-account
python3 -m unittest discover -s templates/options-lifecycle/tests
python3 -m unittest discover -s templates/options-put-delivery/tests
python3 -m unittest discover -s templates/options-account/tests
```

CI runs the same. Two limits to keep in mind:

- **`SKILL.md`:** the validator refuses a body over **12,000 characters**, and it is at
  the limit. New detail goes into a reference file, with a pointer to it in `SKILL.md`.
- **Template `README.md` files:** they are loaded into the model's context every time a
  recipe is shown, and the validator warns past 4,096 bytes.

## Duty templates

`templates/` holds the duties this skill files, each a complete template (`recipe.json`,
`duty.py`, `README.md`, `CHANGELOG.md`, `tests/`):

- **`options-lifecycle`:** one per option, from the fill to the outcome, on any of the
  three venues. A Rysk put's outcome is what Rysk paid out. A Paradex option's expiry is
  the one the venue states, since a stock or index option expires at its market's close.
  It only reports and runs no command, so it never asks for a pocket. It supersedes
  `@1`–`@9`.
- **`options-put-delivery`:** one per sold Derive or Paradex put whose owner asked to end
  up owning the asset. The lifecycle watch plus the delivery buy, which `options-lifecycle`
  carried as `DELIVER_ASSET` until `@9`. Kept a separate template because Butler marks a
  duty as spending from any `acp` money command in its code, reachable or not: one file
  with both would put a spending-limit card on every option duty.
- **`options-account`:** one per owner, writing the Platforms rows for every venue whose
  account exists. Each row's name, site and worth come from the account read, so a new
  venue needs no new template and nothing refiled. It supersedes `options-account@1`, `@2` and
  `derive-account@1`, so the registry resolves those refs to it, and `SKILL.md` step 9
  moves a filed `@1` or `@2`, or a fork of one, onto it.

A template's `version` is its own integer, separate from the skill's semver. A filed
duty runs the code it was filed with, so any change to `duty.py` needs a version bump,
the old version added to `supersedes`, a `CHANGELOG.md` entry in the template's folder,
and `SKILL.md` updated to file the new version.

## Releasing

1. Bump `version` in `SKILL.md` and add the `CHANGELOG.md` entry; bump any template
   whose code changed, as above.
2. Merge to `main` and tag `vX.Y.Z`. A published `name@version` is immutable.
3. In `butler-skills`, point `skills.json` (`options-trading`) and `templates.json`
   (`options-lifecycle`, `options-put-delivery`, `options-account`, each with its
   `path`) at the new tag.

When a release depends on a change in Butler's server (a new `acp options` field or
venue behaviour), ship the server change first, or make the skill and duties fall back
safely without it, as `options-lifecycle@9` and later do for Paradex expiries.

## Layout

```
SKILL.md                    the procedure a butler follows
references/
  helper.md                 the Derive and Paradex quote helper's lines and fields
  rysk-helper.md            Rysk's quote helper's lines and fields
  listing.md                what a venue lists, from scripts/options_list.py
  selling.md, buying.md     what to say and ask for each kind of trade
  account.md                the account read, subaccounts, withdrawals
  venue.md                  Derive's facts: fees, sizes, spreads, settlement
  paradex.md, rysk.md       what differs on each of those venues
scripts/                    the helpers, run in place: quote.py, rysk.py, options_list.py
templates/
  options-lifecycle/        watch one option to its outcome
  options-put-delivery/     the same for a sold put, buying the asset if assigned
  options-account/          the owner's Platforms rows
```
