# options-trading

The `options-trading` skill for [Butler](https://github.com/Virtual-Protocol/butler-skills):
selling cash-secured puts, buying calls and puts, and closing them on **Derive**,
**Paradex** and **Rysk**, through Butler's `acp options` rail. This README is for the
people maintaining the repo. A butler receives `SKILL.md`, `references/**/*.md` and
`scripts/**/*.py`; the registry also serves the duty templates under `templates/`.

- **Version:** 2.17.2 (`SKILL.md`), with `options-lifecycle` 12, `options-put-delivery` 1,
  `options-account` 6 and `options-order-manager` 1.
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

Not covered: covered calls, spreads or leverage.

## Venues

| | Derive | Paradex | Rysk |
| --- | --- | --- | --- |
| Sell a put | yes | yes | yes |
| Buy, close, buy back | yes | yes | no: the collateral is locked to expiry |
| Underlyings | crypto, and XAUT (tokenized gold) | crypto, stocks, indices, commodities | per Rysk's live inventory |
| Quotes from | `scripts/quote.py` (public order book) | `scripts/quote.py` with `--venue paradex` | `scripts/rysk.py` (an RFQ) |
| Deposit | from any chain, bridged (`--from 1` for USDC on Ethereum); credited a few minutes after its card | from any chain, through the owner's wallet on Arbitrum and Layerswap; usually credited within minutes | USDC on Base, into the owner's HyperEVM wallet |
| Withdraw | to Ethereum (about 20 min), then `acp trade` to Base | to the owner's wallet on Arbitrum through Layerswap (about a minute) | from HyperEVM back to Base |
| Settles | cash (USDC), 08:00 UTC | cash (USDC): crypto at 08:00 UTC, other options at their market's close | **physically**: an assigned put delivers the asset |
| What differs | `references/venue.md`, `account.md` | `references/paradex.md` | `references/rysk.md` |

An open is quoted on every venue that offers it unless the owner names one, and offered
side by side with what the quotes do not say (cash or physical settlement, getting out
early, funding), never ranked (`references/which-venue.md`). A close or withdrawal runs
where the position or USDC is. Every helper and `acp options` line for a trade then
carries `--venue paradex` or `--venue rysk`.

## How the pieces fit

| Piece | Where | Does |
| --- | --- | --- |
| Quotes | `scripts/quote.py` (Derive, Paradex) and `scripts/rysk.py` (Rysk), run in place with `python3 "$HOME/skills/options-trading/scripts/<script>.py"`; fields in `references/helper.md` and `rysk-helper.md` | Read-only and keyless, against each venue's public API. Lists what a venue trades (`chain`, with each underlying's `name` and `kind`), and prices sells, buys, closes and buy-backs with every bound already worked out. `minimum` gives the smallest put a venue takes and the USDC it locks, for an owner who has named no amount yet. |
| Account | `acp options account` | Every venue at once, or one with `--venue`: free USDC, positions (positive size is bought), each account's worth, and whether Butler's signer is ready. |
| Funding | `acp options deposit` | One approval card. |
| Trading | `acp options open`, `buy`, `close` | One approval card each. After approval the order is an immediate-or-cancel limit order, inside the bound on the card (`--min-premium`, `--max-cost`, `--min-proceeds`). Rysk's card is good for 5 minutes and is re-quoted against its floor. With `--order gtc` or `post-only` (Derive and Paradex) it is instead a resting order at the owner's price per contract, and `acp options cancel` files a card to take it off the book (`references/resting.md`). With `--order rfq` (Derive and Paradex, when the owner asks) the run asks the market makers for up to 20 seconds and takes the best quote inside the same bound (`references/rfq.md`). |
| Outcome | `bevo-read request <key> --route options` | `approvalStatus`, then `approvalOutcome` (the fill) or `approvalFailureReason`. |
| Withdrawing | `acp options withdraw` | One approval card. A Derive withdrawal also takes an `acp trade` home to Base. |
| Watching to expiry | the `options-lifecycle@12` duty, `templates/options-lifecycle/` | One per owner, filed unasked once any venue account exists, with nothing to set. Watches every option held, sold or bought, in the main wallet's accounts and in every Butler wallet's own: a heads-up the day before expiry and the outcome once it settles, at the size and cost the account shows. Nothing is filed per trade or deleted after a close. Runs no command, so it is filed with `movesFunds: false` and no pocket. |
| Owning the asset after an assigned put | the `options-put-delivery@1` duty, `templates/options-put-delivery/` | Filed for a sold Derive or Paradex put, only when the owner asked before the open to end up owning the asset; its instrument goes in the lifecycle duty's `EXCEPT` so only one duty reports on it. Watches that put, then buys the asset with `acp trade` if it is assigned. The only options duty with a pocket. |
| A duty that trades | the owner's own duty code, `references/duty.md` | Butler's first reply recommends the duty's own wallet (hands-free, one funding card, copyable) or the main wallet (one Start card for the amount set aside, then no card per trade it covers) with a reason, asks how much to set aside in total, and which venue. `scripts/make_duty.py` builds it from `scripts/duty_program.py` and Butler's rule (`trigger()`, `order()`), so the program is never retyped: the money is on the venue before the trigger is watched, never deposited when it fires; it tells the owner when it is ready, when it fires and how each order ended, and when its balance is short of the next trade. |
| Platforms rows | the `options-account@7` duty, `templates/options-account/` | One per owner, filed unasked once any venue account exists. The only writer of the options rows on the wallet's Platforms tab: one row per venue, and one per Derive subaccount, each at the venue's own worth with its positions and resting orders listed. |
| Working an order for a better price | the `options-order-manager@1` duty, `templates/options-order-manager/` | Filed only when the owner asks for a better price than the book (`references/order-manager.md`), from a Derive quote's `worked` block. Trades one Derive order hands-free from the duty's own wallet, funded by one card: it takes a maker who saves half the gap between the book and Derive's mark, rests post-only at the mark, and gives ground toward the book each step, never past the agreed worst price, then sends a receipt against the fill-now price and finishes; the lifecycle duty watches what it holds. Stopped with its `STOP` setting, never by turning it off: only the running duty can cancel its wallet's resting order. |

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

## Venue limits, safeguards and warnings

A quote sorts what stands in a trade's way three ways:

- **Venue limits** (`reasons`, `tradeable: false`): what the venue itself refuses: under
  its minimum size, nobody bidding or asking, a close whose fee is more than the bid
  pays, a Paradex price outside the market's band, a Rysk quote about to die. Nothing
  waives them.
- **Safeguards** (`safeguards`, `waivable: true`): a price poor enough that the butler
  holds the trade back, says why with the figure, and asks if they still want to go
  ahead; their yes waives it. The quote is re-run with `--waive <ids>`, and the
  open or buy passes `--waive` on, so the card and the approval's intent record it
  (bevo-server `feat/options-safeguard-waive`).
- **Warnings** (`warnings`; Rysk `notes`): said as written, never a stop.

The owner's `--min-premium` or `--max-cost` bound still caps what any fill can cost.

| Check | Warns past | Safeguard past | Side | Why |
| --- | --- | --- | --- | --- |
| spread (`1 - bid/mark`, `ask/mark - 1`) | 10% | 20% (`spread`) | sell, buy | Measured as the share of the option's value given away, not vol points: at the 75-120% vols of alts and stocks a 5-point gap is a small spread. Skipped when under $1 in all, where one price tick is a large share. |
| fees / premium | 15% | 30% (`fees`) | sell, buy | Derive's $0.50 base fee is per order and uncapped, so it swamps small tickets and weeklies. Paradex charges no base fee. |
| premium | under $1 | - | sell | Below it the premium rounds to nothing. |
| depth < size | yes | - | all | The best bid or ask is smaller than the size: it may fill part-way, inside the owner's bound. |
| Rysk delta | - | 0.35 (`exercise`) | sell | The put will probably be exercised: a likely purchase, not idle cash earning. |
| Rysk APR | under 4% | - | sell | The premium barely pays for the lock. |

A close or a buy-back only ever warns about price (over 5 vol points), since an owner
cutting a loss may accept a wide market. `MAX_COST_HEADROOM` (1.05) sets `max_cost_usd`
at the total cost plus 5%, and a budget buy is sized so that ceiling fits the budget.
These figures come from four live cases (BTC and ZEC on 2026-11-11, NVDA on
2026-11-16); tune them from how often safeguards hold trades and are waived.

## Measurements

Apart from Derive's $10 minimum deposit and the Base bridge's ~$0.10 (in
`references/venue.md`), nothing a butler reads states a venue figure: fees, minimums,
sizes, times and which assets clear come from the quote, the account read, the card or
its outcome, so they cannot go stale in the skill. What was measured, for the people tuning the warnings, is
here only; re-measure before relying on a spread or a depth.

Derive v3 mainnet, 7 October 2026 (selling) and 9 October 2026 (buying):

- **Fees:** $0.50 + min(0.03% of index notional, 12.5% of mark value) per order, matched
  to a live fill to the cent. Paradex retail orders paid no option fee. On top, bevo-server
  may send the Virtuals platform fee as Derive's `extra_fee` (`DERIVE_BUILDER_FEE_RATE`, a
  share of the premium, unset by default: none); the helper reads the account's
  `platformFeeRate` itself. Measured 2026-11-16 at 0.5%: a $6.28 premium
  filled with a $0.6548 fee, $0.6234 Derive's and $0.0314 the platform's.
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
python3 validate.py --standalone templates/options-order-manager
python3 -m unittest discover -s templates/options-lifecycle/tests
python3 -m unittest discover -s templates/options-put-delivery/tests
python3 -m unittest discover -s templates/options-order-manager/tests
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

- **`options-lifecycle`:** one per owner, watching every option the accounts hold, on
  any of the three venues and in every Butler wallet's own account (found by the
  Platforms row Butler's server keeps for it). A Rysk put's outcome is what Rysk paid
  out. An option's expiry is the one its account row states, since a Paradex stock or
  index option expires at its market's close. It only reports and runs no command, so
  it never asks for a pocket. `@12` supersedes the per-option `@1`–`@11`.
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
   (`options-lifecycle`, `options-put-delivery`, `options-account`,
   `options-order-manager`, each with its `path`) at the new tag.

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
  which-venue.md            quoting every venue for an open, and offering them side by side
  selling.md, buying.md     what to say and ask for each kind of trade
  resting.md                a resting order at the owner's price, and cancelling it
  rfq.md                    an RFQ to the market makers, when the owner asks for one
  duty.md                   a duty whose own code trades: its money first, its notes, topping it up
  order-manager.md          a Derive order worked for a better price by the order-manager duty
  account.md                the account read, subaccounts, withdrawals
  venue.md                  Derive's facts: fees, sizes, spreads, settlement
  paradex.md, rysk.md       what differs on each of those venues
scripts/                    the helpers, run in place: quote.py, rysk.py, options_list.py
                            duty_program.py, the program of a duty that trades, and make_duty.py, which builds one
templates/
  options-lifecycle/        watch every option held to its outcome
  options-put-delivery/     watch one sold put, buying the asset if assigned
  options-account/          the owner's Platforms rows
  options-order-manager/    work one Derive order for a better price
```
