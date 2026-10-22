# The Derive account: checking it and withdrawing from it

## Where the numbers come from

`acp options account` is the Derive portfolio, and the only source of it. It now lists
every venue, Derive first; Paradex's account is in `references/paradex.md`. Read it fresh
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
| `account.usdc` | All USDC on Derive, across every account below: free plus locked. |
| `account.lockedForPutsUsd` | USDC backing sold puts. It cannot leave until the put settles or is bought back. |
| `account.freeForNewPutsUsd` | **Free USDC**, across every account: what can be withdrawn, or spent on a new sell or buy. |
| `account.accounts` | Each Derive account on its own (below): `universe`, `usdc`, `freeForNewPutsUsd`, `positions`. Only for a question about one of them; answer totals from the fields above. |
| `account.positions` | One row per open option, from every account. `size` positive = bought, negative = sold, in the asset: 0.16 is 0.16 ETH (`sizeUnit`; `contractSize` is 1: one contract is 1 ETH). |
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

## More than one Derive account

Derive keeps its markets in separate groups ("risk universes"), and an account trades only
its own group: **PRIME** (ETH, BTC), **ALT** (SOL, XRP, ADA, ZEC and others), **MIDCAP**
(HYPE), **RWA** (gold). Deposits land in PRIME. A SOL option needs the owner's ALT account.

Butler's server handles this after the owner approves the card, never you:

- If that account holds less free USDC than the trade needs, the server moves **only the
  gap** into it from their other Derive accounts, then trades. The first time, it opens
  the account: at least $5 moves, and Derive charges a $1 fee for opening it. Moves
  between accounts that already exist are free.
- What is left over stays where it is; the next trade, or a withdrawal, moves it again.
  So free USDC is the total across accounts: never ask the owner to move it, and never
  deposit just because one account is short while the total covers the trade.
- A card for such an option says so under `Account`, and a confirmed one reports
  `funding: {movedUsd, createdAccount, universe}` in its outcome. Tell the owner.
- A move that has not shown up when the trade runs trades nothing; the reason says the
  USDC is still theirs. Re-read the account before anything else.

## The Platforms row

The wallet page shows each venue (Derive, Paradex) as one row on its Platforms tab, with no
separate options line in the wallet total. Every one of those rows belongs to the one
`options-account` duty (step 9), which reads every venue every 10 minutes, writes each at
the venue's own figure for what the account is worth, and also tells the owner when a
Derive deposit lands. An older `derive-account` duty is replaced by it (step 9). Butler
never writes a row itself: no `bevo-platforms set`, and no watcher of its own. A row catches up within about 10 minutes of a deposit, trade, withdrawal or settlement.
A row behind this turn's read is that delay, not a discrepancy: answer from the read.

## A withdrawal

"Withdraw my free USDC" means out of Derive, to the owner's wallet. It is `acp options
withdraw` (step 8), never an `acp trade` from the wallet to the owner's own address: that
moves nothing and still costs a fee. Out of Paradex it pays to Base instead
(`references/paradex.md`); the rest of this section is Derive's.

- The amount is at most this turn's `freeForNewPutsUsd` (the total across accounts; the
  server gathers it into one before paying out), rounded down to the cent. "All
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

Moved first: "To buy the SOL call, $45 moved from your main Derive account into a new SOL
account (Derive charged $1 to open it). Bought 0.5 SOL-20261106-116-C for $5.63."

Withdraw: "Withdrawing $1.61 from Derive: it reaches your wallet on Ethereum in about 20
minutes, less a fee of up to $1, so as little as $0.61 may arrive."
