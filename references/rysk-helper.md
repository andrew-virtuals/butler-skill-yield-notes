# The Rysk helper

`scripts/rysk.py`, installed with this skill and run where it is (`references/rysk.md`
says when).
Stdlib only - no key, no account, no signature. Inventory and quotes are public reads.
A listing ("what can I trade on Rysk") is `references/listing.md`, never this helper.

```sh
python3 ~/skills/options-trading/scripts/rysk.py screen --collateral 5000 --pay-with <collateral.address>
python3 ~/skills/options-trading/scripts/rysk.py quote --asset ETH --collateral 5000 --pay-with <collateral.address>
python3 ~/skills/options-trading/scripts/rysk.py quote --asset ETH --collateral 5000 --pay-with <collateral.address> --delta 0.20
python3 ~/skills/options-trading/scripts/rysk.py quote --asset ETH --collateral 5000 --pay-with <collateral.address> --expiry 2026-11-13 --strike 2100
python3 ~/skills/options-trading/scripts/rysk.py chain --asset ETH --expiry 2026-11-13
python3 ~/skills/options-trading/scripts/rysk.py positions --address <smart account>
```

The expiry is the tenor's (`--tenor weekly`, `monthly` by default, `quarterly`: the
listed expiry nearest 7, 30 or 90 days out) unless the owner named a day: `--expiry`
(`YYYY-MM-DD`, UTC), refused with the days Rysk lists when it lists none then. The
strike is the one nearest 10% under spot (`--otm-pct`), or nearest a delta (`--delta`),
unless the owner named one: `--strike`, exactly, refused with the strikes that expiry
lists when it is not among them. `chain` gives one expiry's put strikes on one asset,
each with its `delta` and `pct_otm`, and no price: Rysk has no book, so a price is only
ever a quote.

`--pay-with` is the address of the collateral Butler sells on - **USDC on HyperEVM** -
as `acp options account --venue rysk --json` gives it (`collateral.address`). Rysk names
no stablecoin, so this helper knows a collateral only by that address. `inventory`
lists every collateral per asset (`put_collateral`), and every quote carries
`collateral_options` too. In `positions`, a `received` leg with `collateral: true` is
the stablecoin the put was backed by, coming back.

## The quote, field by field

Named as the Derive helper names them, so `SKILL.md` reads both the same way:

| Field | Means |
| --- | --- |
| `instrument` | Rysk's fields as one name, e.g. `SOL-30OCT26-95-P`; passed to `--instrument` as is |
| `strike`, `expiry`, `days_to_expiry` | the price and the instant the put turns on, as Rysk states it |
| `size` | units of the asset; passed to `--size` as is |
| `collateral.amount` | the USDC the put locks; passed to `--max-collateral` |
| `premium_usd` | `premium_per_unit` times the size, before Rysk's fee |
| `fee_usd` | Rysk's execution fee (`/api/gas`); `null` when it could not be read |
| `net_premium_usd` | what the owner receives: `premium_usd` less `fee_usd` |
| `min_premium_usd` | 95% of `net_premium_usd`, rounded down to the cent; passed to `--min-premium` unless the owner named a floor |
| `apr_pct` | the net premium over the collateral, annualised - "if you kept doing this" |
| `bad_case` | `price`, the asset `fall_pct` (25) below spot, and `loss_usd`, what the put is down at expiry there, premium counted. The owner then **holds** the asset |
| `valid_for_seconds` | how long the maker's quote has left; it is for choosing, never for acting on |

Exit codes: `0` the read succeeded, `1` it did not.

Every quote comes back with `tradeable`, a `reasons` list when that is false, and a
`notes` list of things worth saying either way. An amount under Rysk's minimum is a
quote with `tradeable: false`, `size` 0 and `min_size`, the least Rysk prices; its
reason, `collateral too small`, says what that needs, and what the same size needs at
the day's lowest strike when a maker prices it there; it carries no premium and no
`bad_case`: nothing was priced for the owner. Finding the minimum takes one ask per
size step, so `screen` skips it and says only that Rysk would not price the amount. **Never offer a quote that is not
`tradeable`**, always read the `notes`, and never soften either - they are written
for an owner already.

It contains a small WebSocket client because Rysk is RFQ over a socket and the
container ships no websocket package. Nothing else in the script is unusual.

