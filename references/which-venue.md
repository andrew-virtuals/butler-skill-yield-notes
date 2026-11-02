# Which venue

Three venues trade options here, and they do not offer the same promise. An owner who
names none hears every venue that can do what they asked, so the choice is theirs and
made knowingly. Derive is not a default for an open.

| Trade | Venues |
| --- | --- |
| Sell a cash-secured put | Derive, Paradex, Rysk |
| Buy a call or a put | Derive, Paradex |
| Close, buy back, withdraw | only the venue it is on |

## Opening: quote every venue that offers it

- **They named a venue** ("on Rysk"): that one alone. Otherwise every venue in the
  table's row, even one holding no USDC: an empty venue is a funding question, never a
  reason to skip it.
- **The amount is theirs.** Never make one up to quote with, not a round number and
  not their whole balance: it hides the venues whose minimum is above it.
- **No amount named: minimums, not quotes.** Run each venue's `minimum` for the asset
  (and any expiry or strike they named), then say each venue, its smallest put and the
  USDC it locks, and ask how much. No premium, no APR and no table of strikes yet:
  nothing was priced for them.

  ```sh
  python3 ~/skills/options-trading/scripts/quote.py minimum --underlying <ASSET>
  python3 ~/skills/options-trading/scripts/quote.py minimum --venue paradex --underlying <ASSET>
  python3 ~/skills/options-trading/scripts/rysk.py minimum --asset <ASSET> --pay-with <collateral.address>
  ```

  Each gives `instrument`, `min_size` and `min_collateral_usd` at the strike rule's put
  (or theirs), `lowest_strike` with the same at the day's lowest strike (`null` when it
  is that one), `expiry` and `settlement`. A venue that does not list the asset says so
  (exit 1): one line. **Then stop and send that reply.** No `quote`, `screen` or
  `chain` this turn: a venue's minimum is not an amount to quote at, and neither is a
  round number or their balance. Quote as below once they name an amount.
- **One asset, the same terms on each:** the amount, and any expiry or strike they
  named. All in the same turn, before anything is offered:

  ```sh
  python3 ~/skills/options-trading/scripts/quote.py quote --product cash_secured_put --underlying <ASSET> --collateral <USD>
  python3 ~/skills/options-trading/scripts/quote.py quote --venue paradex --product cash_secured_put --underlying <ASSET> --collateral <USD>
  python3 ~/skills/options-trading/scripts/rysk.py quote --asset <ASSET> --collateral <USD> --pay-with <collateral.address>
  ```

  A buy is the same two `quote.py` lines with `--side buy`. Rysk's `--pay-with` is from
  `acp options account --venue rysk --json` (`references/rysk.md`).
- **No asset named:** each venue's `screen` at their amount; name the assets each one
  can carry and ask which (`references/selling.md`). Never an APR menu.
- **Not listed** (`does not list` from a helper): that venue has no options on the
  asset. Say so in one line.

## Offering

- **Each venue whose quote is `tradeable`**: offered as `SKILL.md` step 3 says, every
  figure from that venue's own quote, the bad case first and `apr_pct` last. A table with
  one column per venue is fine, `bad_case` its first row.
- **Each venue whose quote is not**: one line with its `reasons` as written, figures and
  all. The owner still learns it is there. Rysk's `notes` are said either way.
- **A venue whose minimum is above their amount** (`collateral too small`, `budget too
  small`): say plainly that this venue's minimum differs from the others', with the
  size and dollar figure its reason gives, and that a larger amount would open it. Ask
  nothing more and quote it at no other amount unless they name one.
- **What the quotes do not say**, every time two venues are on the table:
  - *Settlement.* Derive and Paradex settle in cash: a put below its strike is a loss in
    USDC and never the asset. Rysk delivers the asset to the HyperEVM wallet.
  - *Getting out.* Derive and Paradex can buy a put back early. Rysk locks the money
    until expiry.
  - *Funding.* Where its USDC comes from (`SKILL.md` step 4 and each venue's file), and
    what is already free there from step 1's read.
- **Never rank or recommend one.** No "better rate", "wins", "I'd go with". Ask which
  venue; the ownership question follows, on that venue's quote alone.
- Once they pick, steps 4 and 5 run on that venue only, with `--venue` on every line
  and its own file read first: `references/paradex.md` or `rysk.md` (Derive:
  `venue.md`).

## Closing, withdrawing, looking

On the venue it is on: `acp options account` names it, and `--venue` it everywhere,
as that venue's file says (`references/paradex.md`, `rysk.md`). Never move a trade
from one venue to another on your own.

## Say to the owner

- *"<Asset> puts are on Derive and Rysk; Paradex does not list <asset>."*
- *"On Derive, if <asset> ends below $<strike> you take the loss in USDC and never get
  <asset>; on Rysk you receive it. Derive lets you buy the put back early; Rysk locks
  your money until <expiry>."*
- *"<Asset> puts for <expiry> start at $<min_collateral_usd> on Derive (<min_size>
  <asset> at $<strike>), $<…> on Paradex and $<…> on Rysk; lower strikes need less.
  Derive and Paradex settle in cash, Rysk delivers the <asset>. How much USDC would you
  put behind it?"* Every figure from this turn's `minimum` output.
- *"Rysk's minimum is different: it prices no less than <min_size> <asset>, which needs
  $<figure>. It is there if you want that size."*
- *"Which venue would you like?"*
