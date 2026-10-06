# Derive: the facts that shape a note

Measured against the live public API on **6 October 2026, ~08:10 UTC**. Everything
here is a venue fact, not a design choice. Re-measure before launch: the numbers
that matter most (spreads, depth) move.

API base is `https://api.lyra.finance`. Derive's edge **403s urllib's default
User-Agent** - send one, or every call fails for a reason that looks like a ban.

## Expiries

All expiries settle at **08:00 UTC**. Dailies for the next few days, then Fridays
weekly, then the last Friday monthly, then quarterlies. Twelve live at once on ETH
and BTC.

A note's tenor is a *choice among listed expiries*, never a date. The helper picks
the listed expiry nearest the tenor's target and skips anything inside 24 hours.

## Size, ticks and the real minimum

| Asset | Min amount | Step | Min collateral at a ~10% OTM strike |
| --- | --- | --- | --- |
| ETH | 0.1 | 0.01 | **~$245** |
| BTC | 0.01 | 0.00001 | **~$780** |
| SOL | 1 | 0.1 | ~$108 |
| XRP | 100 | 10 | ~$135 |
| HYPE | 10 | 1 | ~$850 |
| ZEC | 1 | 0.1 | ~$1,200 |
| XAUT | 0.1 | 0.01 | ~$380 |

The minimum is in *contracts*, so the dollar minimum moves with the strike. Any
per-note cap below these cannot be filled - it is not a tight limit, it is an
impossible one.

## Fees

```text
taker fee = $0.50 + min(0.03% x index notional, 12.5% x premium)
maker fee =         min(0.01% x index notional, 12.5% x premium)
```

The **$0.50 is per order and is not capped**. That single term is what makes small
notes pointless: on a minimum-size ETH weekly the premium is about $0.70 and the fee
is $0.58.

Fee drag is why the tenor matters more than anything else:

| Collateral | Weekly drag | Monthly drag |
| --- | --- | --- |
| $245 | 82% | 21% |
| $1,000 | 29% | 7% |
| $5,000 | 15% | 4% |
| $10,000 | 13% | 3% |

## Spreads: the number that decides the product

Derive quotes a `mark_price` off its own IV surface, and a real book around it. The
gap between the **bid** and the **mark** is what a seller crossing the spread gives
away. In vol points, at the strikes a note actually targets:

| Asset | bid -> mark gap | What crossing costs the seller |
| --- | --- | --- |
| ETH | ~3.9p | ~26% of fair value |
| BTC | ~3.5p | ~27% |
| HYPE | ~11.8p | ~40% |
| SOL | ~21p | ~78% |
| XRP | ~21p | ~89% |
| ZEC | ~61p | ~70% |
| ADA, LIT, VVV, PUMP, CC, XAUT | no bid at all | not sellable |

**This is the single most important fact in the file.** Derive lists options on
twelve assets. Two of them have books you can sell into.

It also means a fair-value guard set at **2 vol points rejects every fill**,
including good ones - ETH's own spread is twice that. The helper uses **5 points**,
which clears ETH and BTC and rejects everything else. If execution later rests a
limit order between bid and mark instead of crossing, tighten it.

## RFQ: the better execution path, and it is open to us

Derive has a full request-for-quote surface, and it is **not block-only**. Measured
over ~36 hours of ETH and BTC option trades (6,000 trades sampled):

| | RFQ | Orderbook |
| --- | --- | --- |
| Share of option trades | **25%** | 75% |
| Median taker notional | $13,608 | $8,180 |
| Taker fee, % of notional | 0.0300% | 0.0196% |
| Trades at or below $6k notional | **271 of 752 takers (36%)** | — |

Retail-size RFQ is not theoretical: the smallest decile of RFQ taker trades is under
$865 notional, and the median small one is 0.5 contracts at ~$2,663. Butler-sized
notes are ordinary flow here.

**RFQ is not cheaper on fees** - a taker pays the same ~0.03% either way. The whole
benefit is *price*: a maker quoting inside the public spread. That matters because
the public spread is where a quarter of the premium goes (see above).

### Scopes: RFQ needs no withdrawal rights

`ProtocolScope` is granular, and RFQ has its own:

```text
trade:rfq:option        <- what a note needs
trade:orderbook:option
withdraw                <- separate, and not required
admin                   <- separate, and not required
transfer:*              <- separate, and not required
```

A session key scoped to `trade:rfq:option` can request and execute option quotes and
**cannot withdraw, transfer or administer anything**. This is stronger than the plan
assumed: not just "trade but not withdraw", but options-only and RFQ-only.

### Shape of the taker flow

1. `send_rfq` - unpriced legs, amounts positive, direction carries the sign. Nothing
   is signed yet. `max_total_cost` / `min_total_cost` bound the package.
2. Makers answer with signed quotes. **They may take seconds, or never arrive** -
   quoting is voluntary and depends on makers being live.
3. `execute_quote` - the taker's single EIP-712 signature, committing to the maker's
   exact legs and prices.

Two consequences worth designing around. The taker signs **after** seeing the price,
which fits an approval card far better than the orderbook flow does - the owner
approves a real number, not a limit. And an unexecuted RFQ **sits in makers' books
until it expires**, so every path must cancel it, including the error paths.

## Depth

`five_percent_bid_depth` on the ticker is the honest liquidity read. At the ~10% OTM
strikes: ETH shows 60-200 contracts, BTC 2.6-5.5, and everything else is thin enough
that a retail note walks the book. The helper refuses when the best bid is smaller
than the note.

## Liquidity moves with the hour

Measured minutes after the 08:00 UTC settlement roll, parts of the ETH chain showed
**no bid at all**; the same strikes showed 200 contracts a few minutes later. A
single empty read is not evidence an asset is dead.

Quote fresh, never cache a book, and treat `valid_until` (~60s) as real.

## Margin

Derive is a **margin venue**. It will happily let an account sell more puts than its
cash covers. Full collateralisation is *our* rule and nothing on the venue enforces
it: size x strike <= free USDC for puts, size <= the asset held for calls, one
subaccount per user per product.

The failure to design against is two notes funded from one pot of collateral.

## Settlement

**Cash settled.** An in-the-money put reduces USDC. It does not deliver ETH. The
"you now own ETH at $2,450" story is only true if the optional post-settlement spot
buy actually runs - otherwise the owner is simply down money and holds no asset.

Never describe an outcome as ownership before the buy has filled.
