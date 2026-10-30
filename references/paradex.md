# Paradex: what is different

Everything in `SKILL.md` holds on Paradex - the four intents, the four checks before
filing, the bad case first, one key per trade, the approval card, the lifecycle duty.
This file is only what differs. Use Paradex when the owner names it, or when the
position or the USDC they mean is there; never move a trade from one venue to the
other on your own.

## Every command names it

Add `--venue paradex` to every helper line and every `acp options` line of `SKILL.md`
for that trade, and `"VENUE": "paradex"` to its lifecycle duty's `params`. A quote's
`venue` says which venue priced it: file the command on that one. A helper quote on
Paradex, for example:

```sh
python3 ~/skills/options-trading/scripts/quote.py quote --venue paradex --side buy --product call --underlying ETH --budget 50
```

## The market

- **What it lists**: `references/listing.md` with `--venue paradex` - crypto, stocks,
  indices and commodities alike, each by ticker with its `name` and `kind`
  (`MU` is Micron Technology, a stock; `CL` is WTI crude oil, a commodity). Say those as
  given; a `null` one by its ticker alone, never a guess. An asset not listed there has
  no options on Paradex.
- **Names** are `ETH-USD-27NOV26-2600-C`; a decimal strike is written with `_`
  (`HYPE-USD-6NOV26-72_5-P`). Pass them exactly as the quote gives them.
- **Sizes** are in the asset, on each market's own step (`size_step`), and an order has a
  minimum value of the underlying set by the market; the quote's `min_size` includes both.
- **Fees**: Butler's orders are Paradex retail orders; the quote's `fee_usd` is what
  applies, and it can be 0. They can also fill against quotes shown only to retail
  orders, so a fill at or better than the quoted price is normal.
- **Price band**: an order may pay no more than the mark plus the market's price band, or
  sell for no less than the mark minus it; the helper reads each market's band. It leaves
  out a price outside that, so such an option quotes `tradeable: false`; never chase it
  with a higher bound.
- **Only order-book markets.** Some Paradex options trade only by RFQ; the helper never
  offers one, and Butler's server refuses one.
- **Expiries** settle in cash (USDC), into the Paradex account, at a time each market
  sets: a stock, index or commodity option at its market's close, not the crypto time.
  Say the time the quote's `expiry` (or a position's `expiresIn`) gives, never one from
  memory.
- Spreads outside ETH are often wide: the helper's gates apply unchanged, so expect
  more `tradeable: false` there. Say so; never loosen a gate.

## The account

`acp options account` lists every venue, Derive first; `--venue paradex` reads Paradex
alone, and `--json` gives its fields:

| Field | Meaning |
| --- | --- |
| `account.exists` | `false`: no Paradex account yet; the first deposit opens it |
| `account.address` | the Paradex account (not a wallet to send to) |
| `account.usdc`, `freeForNewPutsUsd`, `lockedForPutsUsd`, `positions` | as on Derive (`references/account.md`); each position's `summary` is relayed as written |
| `account.otherPositions` | positions that are not options (perps) on the same account; they share its USDC. Say so when it is not 0 |

There is no `ethereum` and no `accounts` on Paradex. Its USDC is separate from
Derive's: free USDC on one never pays for a trade on the other.

## Funding

`SKILL.md` step 4's deposit, with `--venue paradex`:

- From **USDC on Base** only (no `--from`): the owner's wallet must hold it there. Size
  it as in step 4, $6 at least.
- The first deposit opens the account, and Paradex opens one only for a wallet holding a
  minimum balance. A refusal for that moves nothing: say what its reason says it needs.
- It is usually credited within minutes. The outcome's `depositStatus` is `CREDITED`
  with the amount credited, or still on its way; re-read the account, never deposit
  again to find out.
- Once it is credited, do `SKILL.md` step 9 in the same turn: the owner should never
  have to ask for the row.

## Withdrawing

`SKILL.md` step 8's withdraw line with `--venue paradex` added, as everywhere, and
never its `:home` line.

- At most this turn's `freeForNewPutsUsd`, rounded down to the cent, as on Derive.
- It pays to the owner's wallet **on Base**, usually quickly, less a bridge fee
  (Layerswap). No `:home` leg: it is already on Base.
- The outcome says what arrived, to the unit (`Received`, `Bridge fee`). If Layerswap
  is still paying it out, the outcome says it is on its way: check the wallet, never
  withdraw again to find out. A refund, if Layerswap fails, goes back to the Paradex
  account.

## The Platforms row (step 9)

Paradex's row on the wallet's Platforms tab is written by the same `options-account`
duty as Derive's: one per owner, for every venue, filed by `SKILL.md` step 9 as soon as
the Paradex account exists, unless `duty_list` already has it. There is no Paradex duty
of its own, and never write a Paradex row with `bevo-platforms`.

It reads every venue every 10 minutes and lists each position. It sends no note for a
Paradex deposit: the deposit card already says when the USDC is credited.

## What does not exist on Paradex

- No `:home` leg: nothing comes back to Ethereum to bring home.

## Say to the owner

- *"This one is on Paradex, not Derive: a separate account with its own USDC."*
- *"Withdrawn: 1.995943 USDC arrived in your wallet on Base; the bridge took 0.004057."*
- *"Paradex wants the wallet to hold <what the refusal names> before it opens an account,
  and you have <the wallet's USDC>. Nothing moved."*
