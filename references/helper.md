# The options helper

`scripts/quote.py`, installed with this skill and run where it is. A listing
needs none of this: `references/listing.md` is far quicker. Stdlib only, no API key, no
secret, read-only: it screens and quotes against Derive v3's public API, or Paradex's
with `--venue paradex`, and nothing else. Selling, buying, closing, funding and withdrawing are
`acp options` commands in `SKILL.md`, never this file.

```sh
python3 ~/skills/options-trading/scripts/quote.py screen --tenor monthly --collateral 5000
python3 ~/skills/options-trading/scripts/quote.py quote --product cash_secured_put --underlying ETH --collateral 5000 --tenor monthly --otm-pct 10
python3 ~/skills/options-trading/scripts/quote.py quote --product cash_secured_put --underlying ETH --collateral 5000 --tenor monthly --delta 0.20
python3 ~/skills/options-trading/scripts/quote.py quote --side buy --product call --underlying ETH --budget 200 --tenor monthly --otm-pct 5
python3 ~/skills/options-trading/scripts/quote.py quote --side buy --product put --underlying ETH --size 1 --tenor monthly --delta 0.30
python3 ~/skills/options-trading/scripts/quote.py quote --side close --instrument ETH-20261030-2600-C --size 2.95
python3 ~/skills/options-trading/scripts/quote.py quote --side buyback --instrument ETH-20261030-2300-P --size 2 --premium-received 61.40
python3 ~/skills/options-trading/scripts/quote.py chain --underlying ETH --tenor monthly --type C
python3 ~/skills/options-trading/scripts/quote.py quote --venue paradex --side buy --product call --underlying ETH --budget 10 --expiry 2026-10-30
python3 ~/skills/options-trading/scripts/quote.py quote --venue paradex --side buy --product call --underlying ETH --budget 50
python3 ~/skills/options-trading/scripts/quote.py quote --venue paradex --side buy --product put --underlying ETH --budget 5 --expiry 2026-11-13 --strike 2100
python3 ~/skills/options-trading/scripts/quote.py quote --venue paradex --side close --instrument ETH-USD-27NOV26-2600-C --size 0.1
```

`--venue paradex` (any command) reads Paradex instead, and every field below means the
same there: names like `ETH-USD-27NOV26-2600-C`, sizes in the asset on the market's own
step with Paradex's own order minimum (both in `size_step` and `min_size`), Paradex's fee, and only
markets its order book trades (never an RFQ-only one). `venue` on every quote says
which venue priced it; file the command on that venue (`references/paradex.md`).

It prints one JSON object (a list for `screen` and `chain`) on stdout. Exit `0`: the
read succeeded. Exit `1`: it did not, with a one-line `error: …` on stderr - Derive is
unreachable, does not list that asset, or the option named is not active. Exit `2`: the
command line was wrong (usage on stderr).

`chain` with no `--underlying` lists what the venue trades: one row per underlying, its
`underlying` ticker, `name`, `kind` (`crypto`, `stock`, `etf`, `index` or `commodity`)
and `expiries` (ISO, UTC), order-book markets only. "What can I trade on Derive or
Paradex" is answered by `references/listing.md`, the same list from a far smaller
script; `chain --underlying <ticker>` gives **one** expiry's
strikes, each row naming its `expiry`: the tenor's (monthly by default), so a date it
does not show is not missing from the venue; the list above has every expiry. When the
owner names a day ("this Friday", "30 October"), pass it as `--expiry 2026-10-30` to
`chain` and to `quote`; a day the venue does not list is refused with the days it does.
Group by `kind` and say each `name` as given. Neither venue names its tickers,
so the helper carries a list: `null` means a ticker it does not know yet. Say that one
by ticker alone, never a guess at what it is.

`quote` is the sell side unless `--side buy`, `--side close` or `--side buyback` says
otherwise. Every
quote carries `tradeable` and, when false, `reasons` in plain English. **Never offer a
trade whose quote is not `tradeable`**, and never rewrite a reason into something
softer - they are already written for an owner.

## The sell quote, field by field

| Field | Means |
| --- | --- |
| `instrument` | Derive's name, e.g. `ETH-20261030-2300-P`; passed to `--instrument` as is |
| `strike`, `expiry`, `days_to_expiry` | the price and the instant the note turns on, as the venue states it (a Paradex stock, index or commodity option at its market's close) |
| `size` | contracts, which are units of the asset; passed to `--size` as is |
| `collateral.amount` | what the note locks: USDC for a put, units of the asset for a call; passed to `--max-collateral` |
| `collateral.usd` | the same in dollars |
| `premium_usd` | the bid times the size, before fees |
| `fee_usd` | Derive's taker fee for the whole note |
| `net_premium_usd` | what the owner receives: `premium_usd` less `fee_usd` |
| `min_premium_usd` | 95% of `net_premium_usd`, rounded down to the cent; passed to `--min-premium` |
| `apr_pct` | the net premium over the collateral, annualised - "if you kept doing this" |
| `breakeven` | strike less the bid for a put, plus it for a call |
| `bad_case` | put only: `price`, the asset `fall_pct` (25) below spot, and `loss_usd`, what the note is down at expiry there, premium already counted. The bad case is said with these, first |
| `edge_vs_fair_vol_pts` | how far the bid sits under Derive's own mark; negative for a seller |
| `bid_depth` | contracts on the best bid; a note bigger than this is refused |
| `valid_until` | 60 seconds after the read; quote again past it |

Gates: the bid within 5 vol points of mark, fees at most 15% of the premium, a
premium of at least $1, and the best bid covering the whole note. Size is always what
the collateral **fully** covers, rounded down to Derive's step.

## The buy quote, field by field

`--product call` or `put`. `--budget` is the most the owner will spend, fees
included; `--size` asks for an exact number of contracts instead (a hedge sized to
what they hold). `--otm-pct` defaults to 5 for a buy: the strike nearest spot moved 5%
up for a call, down for a put. `--delta 0.30` picks by delta instead. `--strike 2100`
takes exactly the strike the owner named (sell quotes too); an expiry that does not list
it is refused with the strikes it does.

| Field | Means |
| --- | --- |
| `instrument`, `strike`, `expiry`, `days_to_expiry` | as for a sell; `instrument` is passed to `--instrument` |
| `size` | contracts; passed to `--size`. From a budget: the most the budget buys at the ask plus fee **with 5% room**, floored to Derive's step |
| `ask_price`, `ask_depth` | the best offer per contract, and how many contracts sit on it |
| `premium_usd` | the ask times the size |
| `fee_usd` | Derive's taker fee for the whole buy |
| `total_cost_usd` | `premium_usd` plus `fee_usd`: what the owner pays at today's ask |
| `max_loss_usd` | the same number: a bought option can lose all of what it cost, and no more |
| `max_cost_usd` | about 5% over `total_cost_usd`, rounded up to the cent, never over the budget; passed to `--max-cost`. It is what the owner agrees they can lose |
| `breakeven` | at expiry: strike plus total cost per contract for a call, minus it for a put |
| `overpay_vs_fair_vol_pts` | how far the ask sits over Derive's own mark; positive for a buyer |
| `fair_value_usd` | Derive's mark times the size |
| `fee_drag_pct` | the fee as a share of the premium |
| `budget_usd` | the budget asked for (absent with `--size`) |
| `valid_until` | 60 seconds after the read |

Buyer gates, each a reason in `reasons`: no live ask; the ask thinner than the size;
the ask more than 5 vol points over mark ("you would be paying N% over fair value");
fees over 15% of the premium; a budget (or size) under Derive's minimum, with what the
minimum costs.

## The close quote, field by field

Prices selling back `--size` contracts of `--instrument`, an option the owner holds
(a positive `size` in `acp options account`), on the bid now.

| Field | Means |
| --- | --- |
| `bid_price`, `bid_depth` | the best bid per contract, and its size |
| `proceeds_usd` | the bid times the size, before fees |
| `fee_usd` | Derive's fee for the sale |
| `net_proceeds_usd` | what the owner receives: `proceeds_usd` less `fee_usd` |
| `min_proceeds_usd` | 95% of `net_proceeds_usd`, rounded down; the suggested `--min-proceeds` |
| `fair_value_usd` | Derive's mark times the size |
| `edge_vs_fair_vol_pts` | how far the bid sits under mark; negative is the spread |
| `warnings` | the market is wide, or fees take a big share: say so, it does not stop a close |

A close is refused (`tradeable: false`) only when there is no bid, the bid is thinner
than the size, or the fee is more than the bid pays. An owner cutting a loss may accept
a wide market; tell them it is wide.

## The buy-back quote, field by field

Prices buying back `--size` contracts of `--instrument`, a note the owner **sold** (a
negative `size` in `acp options account`), on the ask now. `--premium-received` is
what they got for it: `netPremiumUsd` from the open's outcome, or the lifecycle duty's
`PREMIUM_USD`, scaled to the size being bought back.

| Field | Means |
| --- | --- |
| `ask_price`, `ask_depth` | the best offer per contract, and its size |
| `cost_usd` | the ask times the size, before fees |
| `fee_usd` | Derive's fee for the buy-back |
| `total_cost_usd` | `cost_usd` plus `fee_usd`: what ending the note costs at today's ask |
| `max_cost_usd` | about 5% over `total_cost_usd`, rounded up to the cent; the suggested `--max-cost` |
| `premium_received_usd` | as given (absent without `--premium-received`) |
| `result_usd` | `premium_received_usd` less `total_cost_usd`: what the note made, or lost if negative, once bought back |
| `frees` | the collateral it releases: USDC for a put, units of the asset for a call |
| `fair_value_usd` | Derive's mark times the size |
| `overpay_vs_fair_vol_pts` | how far the ask sits over mark; positive is the spread |
| `warnings` | the market is wide, or the buy-back costs more than the note brought in |

A buy-back is refused only when there is no ask or the ask is thinner than the size. An
owner getting out of a falling put may accept a wide market; tell them it is wide.

