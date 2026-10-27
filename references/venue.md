# Derive v3: the facts that shape a trade

Derive's facts only; Paradex's are in `references/paradex.md`.

How Derive works, not what it costs today. Every figure said to the owner - a fee, a
minimum, a size, a time, a price - comes from this turn's read: a quote, `acp options
account`, a card or its outcome. The one exception is the deposit minimum and the Base
bridge's cost below; a spread or a depth moves by the hour.

## Where the data comes from

- Public, keyless API at `https://api.derive.xyz/v3`. Each method is a POST of JSON to
  `/public/<method>`. Derive's edge **rejects a request with no User-Agent**: send
  one, or every call fails for a reason that looks like a ban.
- `public/get_all_instruments` - the chain: strikes, expiries, minimum size, size
  step, tick, and the fee terms, per instrument.
- `public/get_tickers` with an `expiry_date` (`YYYYMMDD`) - every strike of one expiry
  in one call: bid and size, ask and size, mark, index, and delta, mark IV, bid IV.

## The account

- **The owner's wallet is the account.** No smart-contract wallet, no account to
  create: the first deposit creates it, with a subaccount.
- **One subaccount per risk universe.** Derive splits its markets into risk universes,
  each with its own subaccounts, and rejects a trade between two (from the wrong one it
  says `Zero liquidity for market or IOC/FOK order (11009)`, whatever the book holds).
  Deposits land in PRIME; Butler's server moves the USDC a trade needs into the right one
  after approval (`account.md`). Which universe an option is in is Derive's
  (`public/get_risk_universes`, the option's `risk_universe_id`); the card names it.
- Deposits and withdrawals happen on **Ethereum L1**, in USDC. Derive gives each
  account its own deposit address there (`public/register_deposit_address`), and a
  keeper sweeps what lands in it.
- `acp options deposit` has Butler's trade bot bridge USDC from the owner's wallet
  straight to that address. It sources from whichever chains hold the money: Base when
  it covers, otherwise any other supported chain, gathering from several when none
  covers alone. The bridge fee comes out of the amount, and the credit lands a few
  minutes after the bridge. Ethereum USDC is the exception: the bot does not gather from
  it, so it deposits directly with `--from 1` and is credited shortly after it is mined.
- The minimum deposit is $10; Derive gives a smaller one to its security module, so
  Butler's server refuses it. A bridged deposit is priced first: if the bridge's
  guaranteed arrival (bounded at 1% slippage) is under $10, it is refused with nothing
  moved. The direct Base bridge costs about $0.10; a route from another chain costs
  more. The card gives the bridge's fee and what arrives.
- A withdrawal pays to the owner's wallet on Ethereum once Derive's batch is proven, in
  the window its card gives, less a fee Derive does not state in advance. Bringing it to
  Base (the `:home` leg) is an ordinary `acp trade`, whose quote gives its own minimum
  and fee. Whether a small amount routes is the quote's call, never yours: quote it,
  then say the number.
- Ethereum gas for a direct deposit is paid by Butler's server wallet path, not asked
  of the owner.
- Login and signing are Butler's server's job: it builds every Derive action, checks
  it against what the owner approved on the card, signs with the owner's wallet and
  submits it. The skill never signs anything, and there is no session key.

## Expiries

Dailies, Friday weeklies, last-Friday monthlies and quarterlies, each settling at the
time its quote's `expiry` gives. A note's tenor is a choice among listed expiries, never a
date: the helper takes the one nearest the target (monthly = 24 days) and skips
anything inside 24 hours.

## Size and the real minimum

The minimum is in contracts (the quote's `min_size`, on its `size_step`), so the dollar
minimum moves with the strike: a put needs `min_size` x the strike of collateral. A
per-note cap below it cannot be filled at all, and the quote says what the minimum needs
(`collateral too small`, `budget too small`). Buying, the minimum is the same number of
contracts at the ask.

## Fees

```text
taker fee = base_fee + min(taker_fee_rate x index x size, mark_price_fee_rate_cap x mark x size)
```

Each term is read from the instrument, and the quote's `fee_usd` is the result. The base
fee is per order and uncapped, which is what makes small tickets and short tenors
pointless: the helper refuses a sell or a buy whose fee is over 15% of the premium.

## Spreads: what decides which trades clear

The gap between Derive's mark IV and the bid IV is what a seller crossing the spread
gives away; the gap between the ask IV and mark IV is what a buyer gives away. The
helper refuses either over **5 vol points**; a 2-point guard would reject every fill,
good ones included.

The offerable set is an output of the gates, not a list: it changes as books deepen or
thin, often within a day. A single empty read just after an expiry rolls is not evidence
an asset is dead - quote fresh, never cache a book, and never say which assets clear from
memory.

## Execution

Every trade is an immediate-or-cancel **limit** order on the public book, never a
market order and never left resting. A no-fill trades nothing, spends nothing and
locks nothing. Derive's RFQ path usually prices better for size and is not used yet,
so a quote here is the worst case.

- **open** (sell): priced from the owner's minimum net premium plus the fee.
- **buy**: refused unless free USDC (what is not backing a sold note) covers
  `--max-cost`, in the option's own subaccount once the server has moved the gap there; priced at (max cost - fee) / size per contract, rounded down to the
  tick. After the fill, premium plus fee must be within the max cost.
- **close**: never more than the account holds, always `reduce_only`, so the venue
  itself refuses to turn a close into a new position. With `--min-proceeds` it sells
  back a **bought** option, priced from the minimum net proceeds plus the fee, rounded
  up. With `--max-cost` it buys back a **sold** note, priced as a buy; it may be paid
  from free USDC plus, for a put, the USDC that put itself locks, never another note's
  collateral. The bound must match the position, or nothing is done.

## Margin

Derive is a **margin venue**: it would carry a put on a fraction of its strike.
Full collateralisation is Butler's rule - the helper sizes to what the collateral
fully covers, and Butler's server refuses an open that free USDC does not cover for
every open put plus the new one.

## Settlement

**Cash settled**, at the `expiry` time. A sold put that ends in the money reduces USDC;
it does not deliver the asset. "You now own ETH at the strike" is true only after a
separate spot buy has filled. A bought option that ends in the money pays USDC into
the Derive account automatically: (settle - strike) x size for a call, (strike -
settle) x size for a put.
