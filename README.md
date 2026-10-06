# butler-skill-yield-notes

The `yield-notes` skill for [Butler](https://github.com/Virtual-Protocol/butler-skills).
For the humans maintaining this repo — never published to a butler. Only `SKILL.md`
and `references/**/*.md` reach one.

**Status: prototype (v0.1.0), not listable.** Quoting and screening work against
Derive's live public API today. Opening a note does not: it needs a registered
session key, and the helper refuses rather than pretend. See "What is blocked" below.

## What it does

Sells one fully collateralised option on [Derive](https://derive.xyz) so idle money
earns while it waits — a cash-secured put on USDC, or a covered call on a long bag.
The model never picks an instrument, a strike or a premium: it passes an intent and
gets back a quote object with every number already fixed.

## The gates, and why they exist

Derive lists options on twelve assets. **Two of them have books you can sell into.**
Measured 6 Oct 2026, the bid sits ~3.9 vol points under mark on ETH and ~3.5 on BTC;
everything else is 10 to 60 points wide, or has no bid at all.

So the helper screens at quote time rather than carrying an asset allowlist. Three
gates, each tuned to a measured number in `references/venue.md`:

| Gate | Default | Why |
| --- | --- | --- |
| `MAX_VOL_GAP_PTS` | 5.0 | ETH's own spread is ~3.9p. A 2p guard rejects every fill, including good ones. |
| `MAX_FEE_DRAG` | 15% | The $0.50 base fee is uncapped and per-order; it is 82% of a minimum-size weekly. |
| bid depth ≥ note size | — | A note bigger than the best bid walks the book. |

The list of offerable assets is therefore an output, not a config. It widens by
itself as Derive's books deepen.

These thresholds are calibrated for **crossing the public spread**, which is all the
prototype can do. Derive's RFQ path is open to retail size (25% of option flow; 36%
of RFQ taker trades are under $6k notional) and prices inside that spread, so once a
session key exists the gates should be re-tuned against RFQ fills, not book fills.
`MAX_VOL_GAP_PTS` in particular should come down.

## What is blocked

| Spike | Question | Status |
| --- | --- | --- |
| A1 | Can a Butler wallet register a Derive session key? Privy smart-account EIP-712 signatures are ERC-1271 and Derive may reject them. | **untested — needs a wallet** |
| A2 | Can a container reach Derive's API? | passed (200; send a `User-Agent` or the edge 403s you) |
| A3 | `eth_account` available in the container? | **unmet locally** — not installed, and system Python is 3.9 |
| A4 | Does the Base deposit path work end to end? | **untested — needs funds** |
| A5 | Venue facts | passed — written up in `references/venue.md` |

A1 is the one that can change the architecture: if it fails, the fallback is a
per-user signer EOA controlled by the rail, which is a custodial model and a
different legal question.

## Data sources, all keyless

- `api.lyra.finance/public/get_all_instruments` — the chain, min size, steps, fees.
- `api.lyra.finance/public/get_ticker` — bid/ask/mark, IVs, delta, `five_percent_bid_depth`.
- `api.lyra.finance/public/get_all_currencies` — which assets exist at all.

## Validating a change

```sh
curl -sSLO https://virtual-protocol.github.io/butler-skills/tools/validate.py
python3 validate.py --standalone .
```

## Releasing

Bump `version` in `SKILL.md`, add the `CHANGELOG.md` entry, merge to `main`. A
published `name@version` is immutable. Listing a skill is maintainer-only — and this
one is not listable while it can move funds outside Butler's approval cards.
