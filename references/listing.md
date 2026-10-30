# What a venue lists

The answer to "what options can I trade on Paradex", "which stocks does Paradex have",
"what does Derive list", "what can I sell on Rysk". Run this one command and nothing
else: not the quote helpers in `references/helper.md` or `rysk-helper.md`, not
`acp options account`, and no other reference. It is read-only and keyless, and
finishes in a few seconds.

It is `scripts/options_list.py`, installed with this skill: run it in place, with
`--venue paradex`, `--venue derive` or `--venue rysk`.

```sh
python3 ~/skills/options-trading/scripts/options_list.py --venue paradex
```

It prints one row per underlying: its `underlying` ticker, `name`, `kind` (`crypto`,
`stock`, `etf`, `index` or `commodity`) and `expiries` (ISO, UTC). Order-book markets
only: an RFQ-only Paradex market cannot be traded here. On Rysk the rows are the assets
it takes **sold puts** on, the one trade there. An asset not listed has no options on
that venue that Butler can trade.

Group by `kind` and say each `name` as given. A `null` name is a ticker the list does not
know yet: say it by ticker alone, never a guess. A stock, index or commodity option
expires at its market's close, not the crypto time: give the time its expiry says.

Strikes and prices come later, from the quote helper, once the owner picks an asset.

## Say to the owner

- *"Paradex lists options on <N> stocks: <TICKER> (<name>), … with expiries out to <the
  last `expiries` date>."* Every ticker, name, count and date from this turn's output.
- *"<Asset> is not listed on <venue>: it has no options there Butler can trade."*
