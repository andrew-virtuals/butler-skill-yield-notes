# Derive v3: the facts that shape a trade

Venue facts, not design choices. Measured against Derive v3 on **7 October 2026**
(selling) and **9 October 2026** (buying), mainnet unless it says testnet. Re-measure
before relying on a spread or a depth: those move by the hour.

## Network

Butler's server picks the venue for the whole deployment: **mainnet by default** (real
USDC, settles to Ethereum), or Derive's Sepolia **testnet** (free test USDC). `acp
options account` reports which as `network`. The helper reads mainnet unless run with
`--testnet`, so on a testnet deployment every helper call carries it. Testnet has no
Base bridge: only `deposit --from 1`.

## Where the data comes from

- Public, keyless API at `https://api.derive.xyz/v3` (testnet
  `https://testnet.api.derive.xyz/v3`). Each method is a POST of JSON to
  `/public/<method>`. Derive's edge **rejects a request with no User-Agent**: send
  one, or every call fails for a reason that looks like a ban.
- `public/get_all_instruments` - the chain: strikes, expiries, minimum size, size
  step, tick, and the fee terms, per instrument.
- `public/get_tickers` with an `expiry_date` (`YYYYMMDD`) - every strike of one expiry
  in one call: bid and size, ask and size, mark, index, and delta, mark IV, bid IV.
- v2 (`api.lyra.finance`) has been dead since 6 October 2026.

## The account

- **The owner's wallet is the account.** No smart-contract wallet, no account to
  create: the first deposit creates it, with a subaccount.
- Deposits and withdrawals happen on **Ethereum L1**, in USDC. Derive gives each
  account its own deposit address there (`public/register_deposit_address`), and a
  keeper sweeps what lands in it.
- Butler's money is on Base, so `acp options deposit` has Butler's server bridge Base
  USDC straight to that address: the bridge fee comes out of the amount, and the
  credit lands a few minutes after the bridge. USDC already on Ethereum deposits
  directly (`--from 1`) and is credited about **two minutes** after it is mined.
- The minimum deposit is $5; Derive gives a smaller one to its security module, so
  Butler's server refuses it. A deposit from Base is priced first: if the bridge's
  worst-case arrival is under $6, it is refused with nothing moved. In practice that
  means never under about $10 from Base.
- A withdrawal pays to the owner's wallet on Ethereum once Derive's batch is proven:
  about **20 minutes** (17 measured on testnet), less a fee of up to $1.
- Ethereum gas for a direct deposit is paid by Butler's server wallet path, not asked
  of the owner.
- Login and signing are Butler's server's job: it builds every Derive action, checks
  it against what the owner approved on the card, signs with the owner's wallet and
  submits it. The skill never signs anything, and there is no session key.

## Expiries

All expiries settle at **08:00 UTC**: dailies, Friday weeklies, last-Friday
monthlies, quarterlies. A note's tenor is a choice among listed expiries, never a
date: the helper takes the one nearest the target (monthly = 24 days) and skips
anything inside 24 hours.

## Size and the real minimum

| Asset | Min size | Step | Min collateral at a ~10% OTM monthly strike |
| --- | --- | --- | --- |
| ETH | 0.1 | 0.01 | **~$230** (strike 2,300) |
| BTC | 0.01 | 0.00001 | **~$750** (strike 75,000) |

The minimum is in contracts, so the dollar minimum moves with the strike. A
per-note cap below it cannot be filled at all. Buying, the minimum is the same number
of contracts at the ask: about $7.40 with fees and headroom for a 5% out-of-the-money
monthly ETH call on 9 October, where the $0.50 base fee is already about 9% of the
premium.

## Fees

```text
taker fee = base_fee + min(taker_fee_rate x index x size, mark_price_fee_rate_cap x mark x size)
```

Each term is read from the instrument; today it is $0.50 + min(0.03% of index
notional, 12.5% of mark value). This matched a testnet fill to the cent. The $0.50 is
per order and uncapped, which is what makes small tickets and short tenors pointless:
the helper refuses a sell or a buy whose fee is over 15% of the premium.

## Spreads: what decides which trades clear

The gap between Derive's mark IV and the bid IV is what a seller crossing the spread
gives away; the gap between the ask IV and mark IV is what a buyer gives away. The
helper refuses either over **5 vol points**; a 2-point guard would reject every fill,
good ones included.

Live mainnet, 7 October, $5,000 monthly put about 10% out of the money:

| Asset | Result |
| --- | --- |
| ETH | ETH-20261030-2300-P, 2.17 contracts, $57.94 gross, $2.18 fee, **$55.76 net**, ~17.8% a year, edge -1.28 vol points |
| BTC | tradeable, ~7.6% a year |
| the other ten | refused: no bid, a spread wider than 5 points, a bid thinner than the note, or fees over 15% |

By 13:20 UTC the same day HYPE had cleared as well (edge -1.8 points). The offerable
set is an output of the gates, not a list: it changes as books deepen
or thin. A single empty read just after the 08:00 roll is not evidence an asset is
dead - quote fresh, never cache a book.

Live mainnet, 9 October 05:05 UTC, $200 budget, monthly, strike about 5% out of the
money:

| Buy | Result |
| --- | --- |
| ETH call | ETH-20261030-2600-C, 2.91 contracts at 64.4, $187.40 + $2.67 fee = **$190.07**, max cost $199.58, breakeven $2,665.32, ask 1.03 vol points over mark |
| ETH put | ETH-20261030-2350-P, 3.5 contracts at 53.5, $187.25 + $3.11 fee = **$190.36**, max cost $199.88, breakeven $2,295.61, ask 0.77 vol points over mark |
| BTC call | BTC-20261030-86000-C, 0.14287 contracts at 1,305, **$190.48** total, max cost $200, breakeven $87,333.24 |
| BTC put | BTC-20261030-78000-P, 0.18778 contracts at 987, **$190.47** total, max cost $200, breakeven $76,985.67 |

The same morning XRP's call was refused at 11.5 vol points over mark ("paying 30%
over fair value"), and an $8 weekly ETH call 15% out of the money at 16% fee drag.

## Execution

Every trade is an immediate-or-cancel **limit** order on the public book, never a
market order and never left resting. A no-fill trades nothing, spends nothing and
locks nothing. Derive's RFQ path usually prices better for size and is not used yet,
so a quote here is the worst case.

- **open** (sell): priced from the owner's minimum net premium plus the fee.
- **buy**: refused unless free USDC (what is not backing a sold note) covers
  `--max-cost`; priced at (max cost - fee) / size per contract, rounded down to the
  tick. After the fill, premium plus fee must be within the max cost.
- **close**: only a position the account **bought**, never more than it holds, sent
  `reduce_only` so the venue itself refuses to turn a close into a new short; priced
  from the minimum net proceeds plus the fee, rounded up. A sold note cannot be
  closed in v1.

## Margin

Derive is a **margin venue**: on testnet a put needing $250 drew about $35 of margin.
Full collateralisation is Butler's rule - the helper sizes to what the collateral
fully covers, and Butler's server refuses an open that free USDC does not cover for
every open put plus the new one.

## Settlement

**Cash settled**, at 08:00 UTC on the expiry date. A sold put that ends in the money
reduces USDC; it does not deliver ETH. "You now own ETH at $2,300" is true only after
a separate spot buy has filled. A bought option that ends in the money pays USDC into
the Derive account automatically: (settle - strike) x size for a call, (strike -
settle) x size for a put.
