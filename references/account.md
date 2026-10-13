# The Derive account: checking it and withdrawing from it

## Where the numbers come from

`acp options account` is the Derive portfolio, and the only source of it. Read it fresh
for every check and before every withdrawal; never reuse an earlier turn's figures.

`bevo-read assets` knows nothing about Derive. Its `perps` block, `futuresUsd` and
`hlAccountUsd` are the owner's **Hyperliquid** account, and its `cashUsd` is spendable
cash in their wallet. A `perps.accountValueUsd` of 0 says nothing about Derive. Read it
only to see what a deposit can draw on (step 4).

If `acp options account` fails, Butler cannot see the account now: say so. Never fall
back to `bevo-read assets`, and never report an unreadable account as empty.

## The fields

| Field | Meaning |
| --- | --- |
| `signerReady` | `false`: Butler's signer is not enabled, so nothing can be filed. Reads still answer. |
| `account.exists` | `false`: no Derive account yet. The first deposit creates it. |
| `account.usdc` | All USDC in the account: free plus locked. |
| `account.lockedForPutsUsd` | USDC backing sold puts. It cannot leave until the put settles or is bought back. |
| `account.freeForNewPutsUsd` | **Free USDC**: what can be withdrawn, or spent on a new sell or buy. |
| `account.positions` | One row per open option. `size` positive = bought, negative = sold. `mark` and `averagePrice` are Derive's per-contract prices. |
| `ethereum.usdc` | USDC already in the owner's wallet on Ethereum, such as a withdrawal that has arrived. |

## A check

Answer from the fields above and stop: free USDC first, then each position's instrument,
bought or sold, size and `mark`, as written. Never work out a profit, a loss or a value
from `mark` and `averagePrice`; if asked, closing quotes (`--side close` / `--side
buyback`) say what a position would fetch now.

A position is not cash. A bought option turns into USDC only when it is sold back (Close)
or settles in the money; a sold put's collateral frees up only when it settles or is
bought back.

## A withdrawal

"Withdraw my free USDC" means out of Derive, to the owner's wallet. It is `acp options
withdraw` (step 8), never an `acp trade` from the wallet to the owner's own address: that
moves nothing and still costs a fee.

- The amount is at most this turn's `freeForNewPutsUsd`, rounded down to the cent. "All
  of it" is that figure. Butler's server refuses more with `only $N is free; the rest
  backs open notes until they settle`.
- It pays to the owner's wallet on **Ethereum**, about 20 minutes later, less a fee of up
  to $1. Say that before filing, so a small withdrawal is not a surprise: from $1.61, as
  little as $0.61 may arrive.
- Bringing it to Base is the `:home` card, filed once it shows in `ethereum.usdc`, for the
  amount that arrived. The trade has its own minimum and fee (`references/venue.md`); if
  it refuses a small amount, the USDC stays on Ethereum. Give the reason as written.

## Say to the owner

Check: "On Derive you have $1.62 free USDC and four options you bought: 0.16 of
ETH-20261023-2700-C at a mark of $25.96, …"

Nothing free: "All $250 on Derive is backing your ETH put until it settles on 30 October.
Buying it back would free it now."

Withdraw: "Withdrawing $1.61 from Derive: it reaches your wallet on Ethereum in about 20
minutes, less a fee of up to $1, so as little as $0.61 may arrive."
