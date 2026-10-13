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
| `account.positions` | One row per open option. `size` positive = bought, negative = sold, in the asset: 0.16 is 0.16 ETH (`sizeUnit`; `contractSize` is 1: one contract is 1 ETH). |
| `positions[].summary` | The position in one owner-ready line: size, strike, expiry and how long is left, what it cost, its worth at mark, up or down. Relay it as written. |
| `positions[].valueUsd`, `costUsd`, `pnlUsd` | Worth at mark, what it cost (or received, if sold), and up (positive) or down. |
| `positions[].markPerUnitUsd`, `entryPricePerUnitUsd` | Prices **per 1 ETH**, never what the position is worth: that is `valueUsd`. |
| `positions[].expiresIn` | "in 10 days": never work a date out yourself. |
| `ethereum.usdc` | USDC already in the owner's wallet on Ethereum, such as a withdrawal that has arrived. |

## A check

Answer from the fields above and stop: free USDC first, then each position's `summary`,
as written. Asked whether they are up or down: each position's `pnlUsd` as written; that
is at mark, while a close quote says what selling back now would fetch, a different
question. Never work out a value, cost, profit or date yourself; each is a field. On an
older server with no `summary`, give each size in the asset ("0.16 ETH") and any `mark`
labelled per ETH, and never as the position's worth.

Every figure comes from this turn's read, never from your memory or profile. A stored
note that disagrees with the read, such as a size or a unit conversion, is wrong: answer
from the read and correct the note.

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

Check: "On Derive you have $1.62 free USDC. Bought 0.16 ETH of the $2,700 call expiring 23
Oct 2026 (in 10 days), paid $5.49, worth $3.31 at mark, down $2.18; …"

Nothing free: "All $250 on Derive is backing your ETH put until it settles on 30 October.
Buying it back would free it now."

Withdraw: "Withdrawing $1.61 from Derive: it reaches your wallet on Ethereum in about 20
minutes, less a fee of up to $1, so as little as $0.61 may arrive."
