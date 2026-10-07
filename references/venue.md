# Derive v3: the facts that shape a note

Venue facts, not design choices. Measured against Derive v3 on **7 October 2026**
(mainnet unless it says testnet). Re-measure before relying on a spread or a depth:
those move by the hour.

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
- Deposits and withdrawals happen on **Ethereum L1**, in USDC. Butler's money is on
  Base, so a note is funded by bridging Base to Ethereum, then depositing.
- A deposit is credited about **two minutes** after it is mined. The minimum deposit
  is $5; a smaller one is lost to Derive's security module.
- A withdrawal pays to the owner's wallet on Ethereum once Derive's batch is proven:
  about **17 minutes** on testnet, quoted to owners as about 20.
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
per-note cap below it cannot be filled at all.

## Fees

```text
taker fee = base_fee + min(taker_fee_rate x index x size, mark_price_fee_rate_cap x mark x size)
```

Each term is read from the instrument; today it is $0.50 + min(0.03% of index
notional, 12.5% of mark value). This matched a testnet fill to the cent. The $0.50 is
per order and uncapped, which is what makes small notes and short tenors pointless:
the helper refuses a note whose fee is over 15% of the premium.

## Spreads: what decides which assets can carry a note

The gap between Derive's mark IV and the bid IV is what a seller crossing the spread
gives away. The helper refuses anything over **5 vol points**; a 2-point guard would
reject every fill, good ones included.

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

## Execution

An open is an immediate-or-cancel **limit** sell on the public book, priced from the
owner's minimum net premium plus the fee, never a market order and never left
resting. A no-fill sells nothing and locks nothing. Derive's RFQ path usually prices
better for size and is not used yet, so a quote here is the worst case.

## Margin

Derive is a **margin venue**: on testnet a put needing $250 drew about $35 of margin.
Full collateralisation is Butler's rule - the helper sizes to what the collateral
fully covers, and Butler's server refuses an open that free USDC does not cover for
every open put plus the new one.

## Settlement

**Cash settled.** An in-the-money put reduces USDC; it does not deliver ETH. "You now
own ETH at $2,300" is true only after a separate spot buy has filled.
