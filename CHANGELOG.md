# Changelog

## 2.18.0

- **Auto-roll: a put every week, from the duty's own wallet.** `make_duty.py --preset
  auto-roll` builds it with a rule the script holds (`AUTO_ROLL`), so none is written in
  chat. Once nothing is open and the last put has settled (no collateral locked, 20 minutes
  past its expiry) it sells this week's put: the strike nearest spot at least 8% under it
  with a delta of 0.15 or less and a bid, the expiry nearest 9 days (a Friday), sized to all
  its free USDC, at the quote's bound. Cash only: it never buys the asset. It needs
  `--end-at` and `--max-loss`, runs on Derive every 300 seconds, and sells a put a week to
  its end date when `--times` is left out. `duty.md` has a new "Auto-roll" section: the
  first reply fixes its own wallet and Derive, the second quotes the first put with the same
  rule and makes the short offer (the trade and its yield, what a fall below the strike
  costs in cash, the weekly target, stop anytime). `SKILL.md` Limits and `selling.md` allow
  rolling only through an auto-roll duty the owner set up.
- **`quote.py quote --max-delta`**, with `--otm-pct`, on a sell: the strike nearest spot at
  least that far out of the money whose delta is at most that, with a bid. A strike whose
  delta is unread or not a number is skipped, never read as 0; none fits, it is refused
  saying so. Replayed on Derive's trades of 18 Sep to 16 Nov 2026 (ETH down 22%), weekly ETH
  puts by `--otm-pct 8 --max-delta 0.15` netted +1.4% a year where puts 5% out of the money
  lost 44%.
- **A duty can end itself and bring its money home** (every duty, not only auto-roll):
  `--end-at YYYY-MM-DD` and, on its own wallet, `--max-loss <USD>` and
  `--withdraw-on-finish` (`END_AT`, `MAX_LOSS_USD`, `WITHDRAW_ON_FINISH`, `WALLET_LABEL`).
  It makes no new trade from its end date, after `--times` trades, on `"STOP": true` in its
  params (a real yes: `"false"` or `"0"` never stops it), or once the loss limit is reached:
  counted from what it deposited, with nothing open, and still short six hours later
  (settled cash that lands late is not a loss), trading nothing while it checks. With the
  wind-down it then waits until nothing ties money to the venue (no position, no locked
  collateral, no fill or deposit still landing), withdraws everything free (a cent under
  the figure read, less again only after "only $N is free"), waits for that to reach its
  wallet, sends everything back to the main wallet and finishes, saying what went home.
  The send home reads its wallet's USDC on each chain (`bevo-wallet list --fresh`) and
  files one `bevo-wallet withdraw --amount <that> --token usdc --chain-id <chain>` per
  chain holding $1 or more: with no `--to` it pays the owner's own wallet, and from the
  duty's own session it runs without a card (`withdraw --all` always asks one, and
  finishing would withdraw it). Should the server file a card anyway, the duty says so
  once and finishes only after the owner's approval has emptied its wallet. Money that
  lands on the venue before the end is withdrawn too. A refused withdrawal is said once
  and tried again; an unclear one is tried again after an hour if the money is still
  there; a send home that went through despite an error is not sent again.
- **A duty's money comes home from chat, whether the duty runs or not.** `account.md` has a
  new "A duty's own wallet" section: read its account with `bevo-read get
  '/options/account?venue=derive&walletId=<LABEL>'`, stop it if it still runs, cancel what
  rests (`acp options cancel --order <id> --wallet <LABEL>`, a card), withdraw into the
  duty's wallet (`acp options withdraw --wallet <LABEL>`, a card; `--wallet` left out in
  that duty's own chat), then, once it has landed, `bevo-wallet withdraw --wallet <LABEL>
  --all` into the main wallet, a second card; never `:home`. Derive keeps about $1 a
  withdrawal, said first. `order-manager.md` no longer says a cancel with `--wallet` is
  refused, or reads the account with `acp options account --wallet`, and `duty.md` no
  longer edits a duty's code to withdraw: both point to the new section. "Holds nothing to
  withdraw" right after a venue withdrawal means not landed yet: wait.
- **Locked collateral is not "short".** A duty with a sold put open no longer tells the
  owner to top up: the collateral comes back when the put settles. It is short only when
  its trigger fires, or free and locked USDC together cannot pay for the next trade.
- Tests: the end date, the loss limit (after six hours, from what it deposited, not on a
  late settlement, never on a main wallet), `STOP` and `"STOP": "false"`, a last fill or a
  deposit still landing, locked collateral, late settled cash, refused, unclear and
  shrinking withdrawals, cash already in its wallet, a send home that errs or goes through
  anyway, a send per chain at the amount read, a card filed instead of a send, an unread
  wallet, a restart mid wind-down, and a weekly roll from funding to its second put across
  a settlement (`tests/test_duty_program.py`); the preset's payload, refusals and weeks, and
  the strike rule with unread deltas (`tests/test_make_duty.py`). No new file: the repo stays
  within the hub's 50.
## 2.17.2

- **An ask that says "buy" is not the yes: nothing is filed before the owner answers the
  offer.** Seen in live-model evals: "buy the minimum size of the ETH $1,550 put expiring
  4 Dec on Derive" named everything, and Butler quoted and filed `acp options buy` in the
  same turn, skipping the first-time questions and "you can lose the whole $X - yes?".
  "Never file without all four" rule 3 now says a "buy it" in the ask is not that yes:
  offer, and file nothing until they answer. One-turn asks on three phrasings, 90 trials
  each: 2.17.1 filed early 4 times, this version 0. The fees, spread and RFQ flows were
  re-run with no change. To stay under the body cap, the "Later" bullet in When to use
  (Before you start 1 says it) and two words elsewhere were cut.

## 2.17.1

- **A fee warning the owner already said yes to is not asked again at filing.** Seen in
  QA: a minimum-size Derive buy offered with fees at about 29% of the premium (a warning), the
  owner said yes and deposited, and step 5's re-quote came back held by the `fees`
  safeguard at 32%: the premium had moved and Derive's $0.50 base fee had not. Butler
  asked a second yes. `helper.md` § Safeguards rule 4: for the same strike, expiry and
  size, a yes to an offer that gave the fees warning covers the re-quote; it is quoted
  with `--waive fees`, filed, and the new share is said with the card. A `spread`
  safeguard or any other change still asks. A dollar floor on the fee was not used: it
  would also free the NVDA $140 put, a $0.55 fee on a $0.87 premium, which the
  safeguard is for.
- **Asked for an RFQ quote, Butler says the figure is the order book's.** Seen in QA:
  "get me an RFQ quote, just show me the quotes" got the book's prices with no word that
  they were not the makers'. The makers are asked only once the card is approved, so
  `rfq.md` § Asked for the RFQ price before filing gives the book's figure as the book's,
  and says the makers' price comes after approval, never above the limit.

## 2.17.0

- **A buy offer gives today's price and the ceiling as two numbers, and the owner can set
  the ceiling.** Seen in QA (F6): "You pay at most $2.60 ($1.92 premium + $0.55 fee)",
  but those add up to $2.47. $2.60 was `max_cost_usd`, today's total plus 5% room for the
  price moving before the fill. The buy quote now prints `cost_line`: "About $2.47 at
  today's price ($1.92 premium plus $0.55 in fees). The order allows 5% for the price
  moving before it fills, so you pay at most $2.60; you can set a different ceiling."
  `max_loss_usd`, which repeated `total_cost_usd` under a name that read as a second
  maximum, is gone. `buying.md` § The ceiling: a ceiling the owner names replaces
  `max_cost_usd` in the yes, funding and `--max-cost`. It gets its own yes before
  filing, and it is never under `total_cost_usd` or over the budget. `SKILL.md`'s buy
  command files `<AGREED_CEILING>`. Live-model eval (virtuals-agent `options-ceiling`,
  0.1 ETH 1800 call on Derive, v4-1-flash, 10 trials a cell, old = this PR's head before
  the change): the room was said in 2/10 offers before and 10/10 after; "you can set a
  different ceiling" in 0/10 before and 7/10 after. When the owner named a ceiling, a yes
  to it came before filing in 8/10 before and 10/10 after. Every trial filed the right
  `--max-cost`. The false breakdown did not reproduce on the order book in either arm
  (0/40).
- **One duty watches every option to expiry.** Files `options-lifecycle@12`, once per owner
  beside `options-account` (step 9), with nothing to set. It was one duty per option, filed
  after each fill and deleted after each close; step 7 now files nothing per trade, and a
  resting order and a part close need no duty work either. It reads what every account
  holds, a Butler wallet's own included, so a worked order's position is watched like any
  other. Step 9 deletes the per-option `@11` duties. What a close compares against is the
  position's `costUsd` from `acp options account`, no longer a duty's `PREMIUM_USD`.
- **`options-put-delivery` is filed beside it**, no longer instead of it, with its
  instrument in the lifecycle duty's `EXCEPT` so only one duty reports on that put.
- **A deposit starts at $11, not $6.** Derive and Paradex refuse a deposit under $10, and
  one whose bridge could deliver less, so Butler tried $6, then $10, then $11, and guessed
  what would arrive. Step 4 now starts at $11, files the `deposit at least $N` a refusal
  names once, and says what arrives only from the card.
- **A Derive order can be worked for a better price.** New `options-order-manager@1` duty
  and `references/order-manager.md`, used only when the owner asks ("get me a better price",
  "work the order"). The duty trades one put sale, buy or close from a wallet of its own,
  funded by one card: it takes a market maker's quote that saves half the gap between the
  book and Derive's mark, rests post-only at the mark, gives ground toward the book step by
  step, and never passes the worst price the owner agreed. It ends with a receipt: the
  average, the saving against the book, and where each fill came from. Needs
  `DUTY_WALLET_OPTIONS_ENABLED` on the server.
- **A worked order chooses on what the owner nets after fees.** A resting fill pays Derive's
  maker fee and no $0.50 base fee, so on a small order the duty rests rather than take a
  maker's quote or the book, unless it beats resting by more than the taker fee.
- **A Derive quote carries the duty's settings.** `worked.params`, `worked.fund_usdc` and
  `worked.at_mark_saves_usd` on a put sale, a buy, a close and a buy-back, so nothing is
  worked out in the chat.
- **A worked order is stopped with `STOP`, never by turning its duty off.** Only the running
  duty can cancel an order resting from its wallet: the server refuses a chat cancel with
  `--wallet`.
- **A resting order the market has passed is said.** Files `options-account@7`: the account
  duty's check now compares every order still resting in the owner's accounts with its
  option's mark, and says once per order when a sale sits more than 2% under the mark, or a
  buy more than 2% over it, and would give away $1 or more. It cancels nothing: the note
  asks the owner. Step 9 updates an `@6` duty in place.
- **Butler offers RFQ in three cases.** An owner who has never heard of RFQ cannot ask for
  it. On Derive or Paradex, Butler now offers it beside the order book, in one line and
  once per trade, when the order is bigger than the book's best price holds (the "is only
  N contracts" warning), when the book's price is poor (a `spread` safeguard or a
  wide-market warning), and when a book order did not fill. The owner still picks:
  `--order rfq` is filed only on their word. A safeguard still needs its yes and
  `--waive`. No offer for an order at the quote's `min_size`, and never for an empty book.
  - `scripts/quote.py` decides the first two: such a quote carries `rfq_offer`, the line
    for the owner, said as written at the end of the offer. Prose alone did not work: in
    the live-model eval Butler built its offer from the quote's fields and left the line
    out. New tests in `tests/test_quote_warnings.py`. The buy and sell reply shapes
    (`references/buying.md`, `references/selling.md`) give the warnings and `rfq_offer`
    a place before the closing question, with a worked sentence: a first-time buyer's
    three questions were crowding the line out.
  - New section "When Butler brings it up" in `references/rfq.md`; `rfq_offer` in
    `references/helper.md`, `references/buying.md` and `references/selling.md`; SKILL.md's
    "No fill" row offers RFQ with the re-quote.

- **Listed is not priced, and an empty book is not a reason for RFQ.** References only.
  Paradex's stock, index and commodity options often have no bid or ask at any strike or
  expiry, so their quote says `no live ask` or `no live bid`. Measured on mainnet on
  2026-11-20, before the US cash open: the helper's source already carries the quotes
  shown only to retail orders, those options had none either, and a small RFQ on them
  drew no maker quote while one on ETH drew many. So the quote's reason was true, and
  nothing in the helper changes.
  - `references/paradex.md`: a new point under The market says this, has Butler run
    one more quote, at another expiry, and no third when opening, before saying the
    asset has no price on Paradex right now, never offer RFQ for it, and never point to
    another venue that does not list the asset.
  - `references/listing.md`: a list with stocks, indices or commodities is said with one
    line that listed is not always priced.
  - `references/rfq.md`: "Never offered for an empty book". A `no live ask` or
    `no live bid` quote never brings up RFQ, on either venue. On Paradex, an owner who
    asks for RFQ on a stock, index or commodity option with no price hears that there is
    no quote to take the bound from, so nothing can be filed. Derive's RFQ is as it was.

## 2.16.0

- **A duty that trades options has its money in place before it can trade.** New
  `references/duty.md`. `SKILL.md` routes to it twice: "**Later** - on a condition, time
  or schedule" in When to use, and a new first check in Before you start, "**Now or
  later.**", which has Butler read `duty.md` before its first reply. Any trade the owner
  wants to happen later is a duty, never a trade filed now; a condition already met, or
  a date that may be the expiry, is asked about. The other Before you start checks are
  renumbered. To fit the body cap, `resting.md`'s pointer is shortened, and step 7's
  two rarer cases (part of a position still open after a close, a second options duty
  in one chat) move to a new `references/lifecycle.md`; nothing else is cut.
  - **The first reply has a fixed shape**, ahead of any quote or question about the
    rule, even when it also clears up the rule: (1) Butler recommends a wallet (the
    duty's own, or the main one) with one reason from the chat, and offers the other;
    (2) how much to set aside for the duty in total, with one trade's need as the
    floor; (3) which venue. The owner's pick stands.
  - **Its own wallet:** `bevo-wallet create`, then `duty_create` with `walletId` and
    `fundUsdc` (one funding card): the amount set aside plus 2%, rounded up to the dollar
    ($10 is $11), and no other headroom; at least $10 set aside, the venue's minimum
    deposit, else Butler recommends the main wallet. Hands-free, kept apart from the
    owner's account, and copyable.
  - **The main wallet:** Butler deposits the gap now, as step 4 does (none when free USDC
    already covers the amount set aside), then files the duty with `pocketUsdc` set to that
    amount and `spendBasis`, so its one Start card proposes the owner's own figure and is
    never asked about in chat. Once held, each trade it covers runs with no card;
    `pocketUsdc` 0 only when the owner asked for a card on every trade. Not copyable.
  - **Its program is a file, never retyped.** `scripts/duty_program.py` is the one program
    every such duty runs, and `scripts/make_duty.py` builds a duty from it: Butler writes
    only the rule (`trigger()` and `order()`, in a `rule.py`), and the script saves the
    whole program in the workspace and prints the complete `duty_create` payload, which
    names it by `codePath`. The script sets the title (`{NAME}`, at most 38 characters),
    the timer, `spendBasis`, the status lines, the settings, the helper's full path
    (`QUOTE_PY`: a duty runs in its own folder, where `~/skills` and `python3` are not
    found, so `quote()` runs the helper with the duty's own interpreter), and what funds
    it: `fundUsdc`, the amount set aside plus 2%, for its own wallet; `pocketUsdc`, the
    amount set aside, for the main one. A main wallet short on the venue gets
    `deposit_first`, sized to the amount set aside, in place of a payload. It refuses a
    rule that sends notes, runs the helper by a path or redefines the program's parts;
    one whose `order()` leaves out the quote's bound (`--min-premium` and
    `--max-collateral`, or `--max-cost`) or names a resting price; one whose `trigger()`
    answers anything but `(True or False, "a line")`; and one that reads the clock's hour
    or weekday, which the agent refuses under an interval timer (`duty.md` shows a
    schedule by timestamps, and `traded_at`, which the program sets on a fill). It
    prints `statusTemplate` and `params` as JSON text, the type `duty_create` declares,
    and refuses a `--name` or `--spec` the shell ate a `$` figure from (`duty.md` puts
    both in single quotes).
    Checked against virtuals-agent's own `prepare()`: both wallets file with no refusal
    and no warning. In evals a program copied from `duty.md` by hand was rewritten or cut
    in about one duty in ten, and a main-wallet deposit was sized to one trade.
  - **What the program does, for every duty:** whatever USDC lands in its own wallet (the
    funding card, a later top-up) is deposited on the venue in a run that trades nothing;
    it says it is ready once the money is there; on every run it checks its free USDC
    covers the next trade and, when it does not, tells the owner once per balance and
    again if it fires while short; it says when it fired and how the order ended
    (`bevo.settled`, route `options`), retrying a not-filled order under a new key and
    never resending an unclear one; it stops after `--times` trades.
  - `tests/test_duty_program.py` runs the program against a fake duty runtime (set-up,
    short and top-up, an unfunded wallet, a held-back trade, a missed order, a failing
    quote, an unclear order); `tests/test_make_duty.py` covers the payload and refusals.
  - **Its timer runs from the moment it is filed** until done (every 60 seconds for a
    set time, every 300 for a price or a schedule), never a `startsAt` or an `at`: the
    time, day or price is in `trigger()`, so the runs before it move the money onto the
    venue. A 14:55 duty that only started at 14:55 deposited then.
  - **Never filed in the turn it is asked**, even when the ask names the time, venue and
    money and free USDC covers it: the first reply recommends the wallet and waits.
  - **A new ask is a new duty, and a fast first reply.** In that turn Butler never opens,
    checks, edits or fixes the owner's other duties, orders or cards, nor copies how an
    earlier duty was filed; one that bears on the money gets one line. When the owner
    named the money (a budget, the collateral, a size), the first reply comes before any
    tool call after reading `duty.md`, and the quote waits for filing.
  - **A wallet still empty after 30 minutes is said once**, with a push ("its wallet is
    still empty, so it has not started"), and its status reads "Waiting for its funding
    card": a funding card declined or left waiting no longer shows "Setting up" for good.
  - **One note per trouble, with its real reason.** While its trigger holds the duty
    tries again every five minutes and says each kind of trouble once: an order nobody
    took; a trade the server held back, named as such (a Start card or an earlier card
    still waiting, a limit used up), where it used to say "did not fill at its floor"; a
    quote that failed three times running (a blip is only logged); an order the server
    refused outright, with the server's own reason. A refused order is never counted as
    a trade: before, one that left no ledger row read as "may have gone through" and the
    duty stopped without trading. The program names the venue on every command itself,
    so a Paradex rule that leaves `--venue` out still files on Paradex. Repeats go to its log
    and its "retrying" status; a fill, or the trigger passing, clears them. Before, each
    run could push the same note again.
  - **By RFQ**, only when the owner asked for it, on Derive or Paradex, from either
    wallet: `order()` adds `--order rfq` with the same bound. `rfq.md` now says makers
    may not quote a small order at all, and to offer the order book for one.
  - The first reply reads a price trigger's condition before it answers (the one read
    allowed ahead of it, the helper's `spot`; unread, it asks rather than assume), and its worked example asks the set-aside question in the
    required words. The main wallet is offered as "one approval for its limit", no longer
    "approve each trade".
  - An own-wallet duty's short note asks for at least $10, the venue's minimum deposit,
    since its wallet moves nothing smaller onto the venue; a top-up is never under $10.
  - On a short note, Butler asks the owner in chat whether to top up and by how much:
    `bevo-wallet fund` (one card; the duty deposits it on its next run) for its own
    wallet, a step 4 deposit for the main wallet.
  - The refusals a duty can get (`OPTIONS_DUTY_OFF`, `OPTIONS_DUTY_NO_WALLET`,
    `OPTIONS_DUTY_PAUSED`, `OPTIONS_DUTY_CARD_PENDING`, `pocket_empty`, `pocket_pending`),
    and stopping: a delete is refused while its venue account holds money or a position.
  - Limits: "never rank or recommend" is now "never rank or recommend a trade", since
    the wallet recommendation is not one.
  - Needs bevo-server with options duties (Virtual-Protocol/bevo-server#1724) and
    `DUTY_WALLET_OPTIONS_ENABLED=true`; without them every duty trade is refused.

## 2.15.1

- **A duty wallet's Derive row stays on the Platforms tab.** Files `options-account@6`. A duty
  that trades options from its own wallet now has its Derive account as a Platforms row that
  Butler's server writes ("Derive · <duty name>", Virtual-Protocol/bevo-server#1685). The
  account duty removed every Derive row that was not one of the main wallet's subaccounts, so it
  would have deleted that row every 10 minutes. It now skips any row the list marks
  `serverKept`. Step 9 updates a duty on `@5` or older in place. Ships with that server change;
  before it, no row is marked and nothing changes.

## 2.15.0

- **RFQ when the owner asks.** New `references/rfq.md`: on Derive or Paradex, "RFQ", "request
  a quote" or "ask the market makers" files step 5's command with `--order rfq` added and the
  same total bound, never a price flag. The owner hears in one line, before approving, that the
  makers have 20 seconds, the best quote inside the bound is taken, nothing trades otherwise,
  and an RFQ never falls back to the book. After it: a no-maker refusal is never re-filed at a
  looser bound without their yes, and the order book is the other offer. Step 5 points to it;
  `venue.md` no longer says RFQ "is not used yet". Ships with bevo-server#1653; a
  server without it answers "takes no rfq orders here", and the reference offers the book.

## 2.14.0

- **Safeguards the owner can waive, and warnings, in place of hard refusals.** A quote's
  price checks were all refusals. Now:
  - `reasons` (`tradeable: false`) are only what the venue refuses: under its minimum,
    no bid or ask, a close whose fee beats the bid, a Paradex price outside its band, a
    Rysk quote about to die.
  - `safeguards` (`waivable: true`) hold a sell or buy back: the spread giving up over
    20% of the option's value (`spread`), fees over 30% of the premium (`fees`), a Rysk
    put with delta over 0.35 (`exercise`). The butler says the figure in the offer and
    asks if they still want to go ahead; their yes re-quotes with `--waive <ids>`, and the open or buy passes
    `--waive` to bevo-server, which records it on the intent and puts a "Safeguard"
    line on the card (bevo-server `feat/options-safeguard-waive`).
  - `warnings` never stop a trade: spread over 10%, fees over 15%, a premium under $1,
    a best bid or ask smaller than the size, Rysk under 4% a year.
- The spread is measured as the share of the option's value given away, not vol points,
  and skipped under $1 in all. The flat 5-vol-point limit refused almost everything but
  ETH and BTC: every NVDA put (2026-11-16) now quotes, the one-contract $150 put with a
  fee warning. A $1,000 BTC put (2026-11-11) refused when its top bid shrank to 0.01
  under a 0.01538 note now quotes with a part-fill warning.
- Needs bevo-server with `--waive` on `acp options open` and `buy`: an older server
  refuses the flag with nothing filed.

## 2.13.4

- **A short gather is in the owner's wallet on the chain that gathered it, not always
  Base.** 2.12.0 said a deposit's sweep lands on Base and a short one stays in the
  owner's Base wallet. For Derive and Rysk the trade bot gathers onto the chain holding
  the most USDC (Paradex's top-up does use Base), so `venue.md` and `rysk.md` point the
  owner at the chain the refusal names (bevo-server #1482, internal-trading-bot #414).
  Replaces the closed #26.

## 2.13.3

- **A Derive quote's fee is the fee the fill charges, and the owner hears whose it is.**
  Seen live: the quote said "$6.28 premium plus $0.62 fee, $6.90 all in", the card
  said a fee of about $0.65, and the fill charged $0.6548. `quote.py` priced Derive's
  taker fee alone ($0.6234) and left out the Virtuals platform fee ($0.0314, 0.5%),
  which the server sends with the order as Derive's `extra_fee` (Derive's "builder
  fee") and counts on the card. A Derive quote or screen now reads the rate itself,
  `platformFeeRate` from `acp options account --venue derive --json` (0.5% when an older
  server leaves it out), and stops with exit 1 when it cannot: a fee guessed low is
  this bug again. There is no flag for the model to pass or forget; a first cut had one,
  and 3 of 9 eval agents left it off their first quote. The fee is inside `fee_usd`,
  every total and net, the size a budget buys and the fee gate, and is split into
  `venue_fee_usd` and `platform_fee_usd`. Paradex, `chain` and `minimum` read nothing.
  bevo-server charges no platform fee unless `DERIVE_BUILDER_FEE_RATE` is set
  (bevo-server #1656).
- **Every offer and every receipt splits the fee.** Step 3 gives the words: "$0.65 in
  fees: $0.62 to Derive, $0.03 Virtuals platform fee", or at 0 "no Virtuals platform
  fee"; `buying.md` and `selling.md` say the same for the receipt, and step 6 gives the
  fees as the outcome's `summary` splits them, Virtuals named, at 0 too.
  Live-model eval (virtuals-agent `options-fees` on an image built from bf92809, the
  commit production runs; deepseek-v4-1-flash; an ETH call on Derive with $20 at live
  quotes): 2.13.2 at 0.5% quoted $0.69 against a $0.78 fill in 3 of 3 trials and named
  no Virtuals fee in any offer. 2.13.3 passed 8 of 8 (4 at 0.5%, 4 at 0): every buy
  filed, quote fee equal to the fill's, and offer and receipt both splitting it ("$0.78
  in fees ($0.69 to Derive, $0.09 Virtuals platform fee)"; "$0.69 in fees, all Derive's,
  with no Virtuals platform fee"). An earlier cut whose step 6 left out "Virtuals named"
  missed the split in 1 zero-rate receipt.
- `SKILL.md` stays under 12,000 characters by wording cuts with no rule changed: bare
  reference names where the rest of the file already uses them, and a few sentences
  tightened. "One of four things" is gone; the list has five.
- `tests/test_quote_platform_fee.py`: the rate read from the account, an older server's
  0.5%, an unreadable account or a bad rate stopping the quote, the fee in every total,
  parts that add up, a budget buying less, and no read on Paradex, `chain` or `minimum`.

## 2.13.2

- **The Platforms Cash line is spendable.** Files `options-account@5`: a resting order's line
  carries the cash it holds back as its value, and Cash is the account's USDC less that, so
  the owner sees what they can spend while the row still adds up to its worth (bevo-server
  `feat/platforms-resting-orders`). Ships with that server change.

## 2.13.1

- **Paradex money moves through Arbitrum, not Base.** Layerswap lists no Base route to
  or from Paradex any more (mainnet, 2026-11-06), so a Paradex withdrawal could not reach
  Base and every Paradex deposit from Base was refused. Butler's server now moves both
  directions between Paradex and the owner's wallet on Arbitrum through Layerswap
  (bevo-server `feat/paradex-arbitrum-deposit`). `paradex.md` says a deposit goes in from
  Arbitrum (topped up there from Base when short, so it may send a little less than
  asked), and a withdrawal pays to the owner's wallet on Arbitrum and stays there; moving
  it on to Base is a separate trade, offered, never done unasked. `account.md` and the
  README say the same.
- Ships with that server change: before it, Paradex money moves neither way.

## 2.13.0

- **Resting orders show on the Platforms tab.** Files `options-account@4`: each open order
  is its account row's last line, status `Resting`, with its limit, fill and what it holds
  back, refreshed every check (bevo-server `feat/platforms-resting-orders` builds the line
  and hands it to the duty in the account read). Step 9 updates a duty on `@1`, `@2` or `@3`
  in place. Ships with that server change: before it the read carries no line, and the
  duty lists no orders, as before.

## 2.12.0

- **A deposit draws on every chain, on every venue.** Seen in chat: asked for a $7
  Paradex deposit with $2.97 on Base, $11.02 on Arbitrum and $15.65 on Ethereum, the
  agent refused it and offered to bridge to Base first, because `paradex.md` (and
  `rysk.md`) said "From USDC on Base only". Butler's server now has the trade bot gather
  a deposit from the owner's stablecoins (USDC, USDT or USDG) on any chain for Derive,
  Rysk and Paradex alike
  (bevo-server `feat/options-deposit-any-chain`, ITB `feat/swept-deposit-quote`), so
  both references say so and never judge a deposit by Base's balance. Step 4's line
  now covers every venue and says stablecoins, not USDC.
- A deposit moves the amount or nothing: short across every chain it is refused with
  nothing moved, and if what was gathered lands short, nothing is deposited and the USDC
  stays in the owner's Base wallet. `venue.md`, `paradex.md` and `rysk.md` say what to
  tell the owner.
- `venue.md` no longer says the bot skips Ethereum USDC: it gathers from it last, and
  `--from 1` still deposits Ethereum USDC directly when it covers alone.
- Ships after both server changes are live: before them, a deposit Base can't cover is
  still refused.

## 2.11.2

- **An order's status is read, never remembered.** Seen in chat: the owner cancelled a
  resting Paradex order with the app's Cancel hold, and the agent then said it was "still
  resting", while the account showed nothing held. The app's cancel, a fill and an expiry
  all reach the owner, not the agent, so the last thing it had seen was the order resting.
  It now reads `acp options account --venue <venue>` before saying where an order or
  position stands (`references/resting.md`).

## 2.11.1

- **A close waits only on Paradex.** Derive refuses a reduce-only order that rests, and a
  close is always reduce-only, so a Derive sell-back or buy-back closes at once
  (`references/resting.md`).
- **A resting buy says what it holds:** price x size is set aside from placement, said
  before the yes, as a sale's collateral is.

## 2.11.0

- **"Sell cash-secured puts on HYPE" quotes every venue, not just Derive.** Seen in
  chat: the owner named no venue, so step 6 sent the trade to Derive; the agent quoted
  only Derive, never checked Paradex, and quoted Rysk only after the owner asked "this
  is derive and not rysk?". It then called Rysk's "the better rate". The owner was
  never told that Rysk settles physically. An open (a put on any venue; a call or a put
  bought on Derive or Paradex) is now quoted on every venue that offers it, at the
  owner's amount, unless they named a venue. With no amount given, the agent asks for
  one first and says each venue has its own minimum; a made-up amount had hidden Rysk,
  whose HYPE minimum was 50 HYPE ($4,125). A venue whose minimum is above the amount
  is named, with its minimum's figures from the quote. The new
  `references/which-venue.md` gives the lines. A venue that is not `tradeable` gets
  one line with its reason; one that does not list the asset, one line saying so. When
  two venues are on the table, the owner hears settlement, getting out early and
  funding. A venue is never ranked or recommended, and the owner picks before the
  ownership question. A close or withdrawal stays where it is. `rysk.md`, `paradex.md`,
  `selling.md` (no side-by-side APRs across assets or strikes; one asset across venues
  is allowed) and the README follow.
- **No amount named: each venue's minimum, then a question.** In 3 trials of the
  transcript's ask on this release's first draft, every agent quoted at an amount it
  made up ($500 to $1,600, once sizing to the owner's whole balance and then saying
  "Derive is where your money fits"), even after reading the rule to ask first: "give
  me some options" left it nothing true to show without one. Both helpers gain
  `minimum`, which prices nothing and gives the smallest put a venue takes, its
  `min_collateral_usd`, and the same at the day's lowest strike (`rysk.py` reuses the
  search its quote already makes under the minimum). `SKILL.md` step 2: no amount
  from the owner, each venue's `minimum`, then ask it, with no quote, screen or chain
  until they name one. A first draft said only "no quote"; the one trial that got far
  enough ran every `minimum`, then quoted at the minimums themselves and at a made-up
  $2,000. `which-venue.md` has the
  lines and the sentence; `selling.md` says it too, as `buying.md` already did for a
  budget.
- `SKILL.md`'s "Monthly by default" line moves to `buying.md` (`selling.md` already
  has it), and "Say to the owner" is one shorter line, to pay for step 2's sentence
  under the 12,000-character body.
- `SKILL.md` stays under the registry's 12,000-character body: step 6 no longer links
  `paradex.md` and `rysk.md` (`which-venue.md` does), and a line in the idempotency
  section is reworded.

## 2.10.0

- **Resting orders: the owner's own price, on the book.** "Sell it at $41 or better"
  is now an order that waits on Derive's or Paradex's book at their price per contract
  until it fills, they cancel it, or the option expires: `--order gtc` (or `post-only`,
  refused rather than fill at once) with `--min-price` to sell and `--max-price` to buy,
  in place of the total bound. Never on Rysk, and never Butler's idea
  (`references/resting.md`).
- **Its card is placed, not filled.** `approvalOutcome.resting` says so; the server tells
  the owner once on the first fill and once when it ends, so Butler never polls it.
- **`acp options cancel --order <id>`** files a card to take one off the book; until the
  owner approves it the order can still fill, and Butler says so. What had filled stays
  (`references/resting.md`).
- **The lifecycle duty is filed when the order is placed:** `options-lifecycle@11` with
  `ORDER_ID`, which waits for the fill and finishes quietly if nothing fills.

## 2.9.0

- **"Sell a SOL put on Rysk with $5" says what the minimum needs.** Seen in QA: Rysk's
  quote refused $5 with "may be under the minimum" and no figure, so the agent went
  looking for one. It guessed a 10 SOL size, picked strikes itself, trimmed the quotes
  with its own script, and offered a table whose 85 put was "down $52ish" if SOL fell
  25%; the put's own `bad_case` was down $94. Rysk publishes no minimum, so an amount
  under it now asks at each larger size step until a maker prices one, then once at the
  day's lowest strike, and comes back as a quote that is not `tradeable`, with
  `min_size` and the reason `collateral too small: Rysk prices no less than 10 SOL,
  which needs $890 on SOL-27NOV26-89-P and $790 on SOL-27NOV26-79-P, the lowest strike
  that day`. The second clause is left out when no maker prices the lowest strike; in
  an eval without it, 4 of 6 agents multiplied the strike list out themselves. That is
  Derive's reason too, so `SKILL.md`'s row reads both: give the figures, work out no
  others, and stop unless the owner names another strike, expiry or amount. `screen`
  skips the search, which costs one ask per step.
- **The helpers ship as scripts, run where they are installed.** The Derive and
  Paradex helper, Rysk's and the listing were fenced blocks in `references/` that a
  butler retyped into `/tmp` every session: minutes of output, a typo that silently
  changes a quote, and copies left behind. The QA run used a `rysk.py` an earlier
  session had edited; evals found agents saving `rysk_tmp.py`, `rysk_session.py` and
  `opt/rysk/rysk.py` because a file tool cannot write `/tmp`, and one retyping a
  different script. They are now `scripts/quote.py` (was `derive_helper.py`),
  `scripts/rysk.py` and `scripts/options_list.py`, run as
  `python3 ~/skills/options-trading/scripts/<script>.py`. Step 2 says never write, copy
  or edit one, or trim its output, and to stop if one is missing; `rysk.md` says a
  `rysk.py` anywhere else is never run. The references keep each helper's lines and
  fields. On the QA turn, 6 of 6 agents ran the installed script once, wrote nothing,
  and gave both figures, in 33-40s against 50-79s.
- `requires.bins` drops `cat`, which only wrote the heredocs. `SKILL.md` was already at
  the registry's 12,000-character body: a sizes line in step 7 that repeated the
  template and some wording are cut, with no rule changed.
- Tests load the scripts themselves, and check that every script is named in
  `SKILL.md` or a reference (a link install fetches only what is named) and that nothing
  is written to `/tmp`.
- Needs the registry to publish `scripts/**/*.py` (butler-skills `validate.py`); Butler's
  agent already installs them (virtuals-agent#314). Until the registry does, keep
  `skills.json` on 2.8.1: a hub install of 2.9.0 would have no helpers.

## 2.8.1

- **"Sell the 2100 put on Rysk for 13 November" sells that put.** Rysk's quote had no
  way to name a strike or a day: it took the listed expiry nearest the tenor and the
  strike nearest 10% under spot, so 30 October and 13 November could never be quoted
  and a named strike only ever approximated, while `selling.md` says a named strike or
  day is quoted exactly or not offered. `rysk.py quote` now takes `--strike` and
  `--expiry`, as the Derive and Paradex helper does, refused with the strikes or days
  Rysk lists when it has no such put.
- **`rysk.py chain --asset ETH --expiry 2026-11-13`** lists one expiry's put strikes,
  each with its `delta` and `pct_otm`: the answer to "which strikes are there". No
  price, since Rysk only prices on request.
- `rysk.md` says `--tenor weekly` is how to ask for a weekly.
- **A Rysk deposit or withdrawal is never under $2.** Both ride `acp trade` between
  Base and HyperEVM, which refuses a move under $2; `rysk.md` sized a deposit as the
  bare shortfall with no floor, so a small one was filed only to be refused.
- **No Derive `:home` leg under $2.** It is the same `acp trade`, from Ethereum to
  Base; `account.md` now says a smaller arrival stays on Ethereum instead of filing a
  card that is refused after approval.

## 2.8.0

- **A duty that only watches no longer asks for a spending limit.** Seen in QA: a bought
  BTC call's lifecycle duty came with a "Set spending limit" card proposing $50, while
  the butler said it never spends. `options-lifecycle@9` carried the delivery buy for
  assigned puts (`DELIVER_ASSET`), and Butler marks a duty as spending from any `acp`
  money command in its code, reachable or not. Step 7 now files `options-lifecycle@10`,
  which runs no command, with `movesFunds: false`: no pocket and no card, for every
  bought option and every sold put without delivery.
- **Owning the asset after an assigned put is its own template.** When the owner asked
  for it in step 3, step 7 files `options-put-delivery@1` instead (`references/selling.md`):
  the same watch, plus the buy, with its pocket card opening on the collateral rather
  than $50. It never buys for a put missing from the account at the last check before
  expiry.
- **"What can I trade on Rysk" uses the listing, not the Rysk helper.** Seen in QA on
  2.7.3: the agent followed `rysk.md`'s command block, which still showed
  `python3 /tmp/rysk.py inventory`, began writing the 29 KB Rysk helper, and ended the
  turn after 1m41s without an answer; the line saying a listing is `listing.md` sat in
  the prose under it. No command block in `rysk.md`, `rysk-helper.md` or `helper.md`
  shows a whole-venue listing any more (`rysk.py inventory`, `derive_helper.py chain
  --venue paradex`), and `rysk.md` and `rysk-helper.md` say first that a listing is
  `listing.md`.

## 2.7.3

- **"Buy the 2100 put" buys the 2100 put.** Seen in QA: the agent quoted and offered
  `ETH-USD-13NOV26-2200-P`, the helper's 5%-OTM rule, because a quote had no way to name
  a strike; it then filed the 2100 with a `--max-cost` it worked out itself. A buy or
  sell quote takes `--strike`, refused with the listed strikes when the expiry has no
  such strike. `SKILL.md` step 2's sell and buy lines carry `--expiry` and `--strike`, and
  `buying.md` and `selling.md` pass a strike or day the owner named that way and offer no
  quote that differs from it.
- **"What can I trade on Paradex" no longer writes the quote helper.** Seen in QA: the
  answer took about 3.7 minutes, of which the API call was 1 second. The agent read the
  51 KB `helper.md` and wrote its 42 KB script out twice (a file tool that cannot write
  `/tmp`, then a heredoc), about 178 seconds of output. `references/listing.md` is the
  same list from a small script, in one shell command; `SKILL.md` sends a listing there
  and nowhere else.
- **Rysk too.** "What can I sell on Rysk" is `listing.md` with `--venue rysk` (the puts
  Rysk takes, by asset and expiry), not the 29 KB Rysk helper; and "how did my puts end"
  reads `acp options account --venue rysk` first, whose `settled` lists recent
  settlements, writing the helper only for a put in neither list.
- **No venue figure in what a butler reads.** Fees, minimums, size steps, the price
  band, expiry times, withdrawal times and fees, and which assets clear were written
  into the references as measured on 7-9 October, and one was already wrong (Derive
  charges nothing to open a subaccount, not $1). Each now points at the quote, account
  read, card or outcome that gives it live, except Derive's $10 minimum deposit and the
  ~$0.10 Base bridge, kept in `venue.md`; the measurements are in `README.md`, for
  maintainers. `screen` screens what each venue lists now instead of a fixed list, and
  the listing's example answer names no asset.
- **The helper ships as a ready-to-run block.** `helper.md`'s script is one
  `cat > /tmp/derive_helper.py <<'PYEOF'` shell command, as `listing.md`'s is, written
  once and reused, never with a file tool. The copy in QA had dropped the script's
  comments and renamed a variable; told so only in prose, the agent still used a file
  tool or retyped it with lines changed.
- `tests/test_listing.py`, run in CI, fails when `listing.md`'s ticker table differs from
  the helper's.

## 2.7.2

- Files `options-account@3`: a Rysk put is listed on its Platforms row, with no value, the
  premium received and its collateral, and a Paradex row lists its free USDC first as
  `Cash`. Step 9 updates a duty on `@1` or `@2`, or a fork of one, in place, unasked.

## 2.7.1

- Files `options-account@2`: one Platforms row per Derive subaccount (`PRIME`, `RWA`),
  each at its own worth with its cash and positions, replacing the one row that merged
  them. Step 9 updates a duty still on `@1` in place, unasked.
- **The helper names what each ticker is.** `chain` with no `--underlying` now gives each
  underlying a `name` and a `kind` (`crypto`, `stock`, `etf`, `index`, `commodity`) from a
  list in the helper of every underlying Derive and Paradex list today. Neither venue's
  API names a ticker, and Paradex tags its stocks, indices and commodities alike as
  `RWA`. Seen in QA: told to say the ticker alone, the agent guessed instead - MU as
  "e.g. MUFG", SPCX as "an SP/ETF index ticker", CL as a stock. They are Micron, SpaceX
  and WTI crude oil. A ticker the list does not know comes back `null` and is said by
  ticker alone; the list is never filled by searching a ticker (Pyth's CL is
  Colgate-Palmolive).
- **A Paradex option's expiry is the market's, not its name's.** A Paradex name gives only
  the day, and everything read 08:00 UTC into it; a stock, index or commodity option
  expires at its market's close instead (META 20:00 or 21:00 UTC, CL 18:30 or 19:30).
  `references/paradex.md`, `helper.md` and `buying.md` now say so, and step 7 files
  `options-lifecycle@9`, which takes the expiry Paradex states. Butler's server states it
  on the card, the account's positions and the ticker.
- **A day the owner names is quoted on that day.** `quote` and `chain` take
  `--expiry YYYY-MM-DD`, and each `chain` row names its `expiry`. Seen in QA: asked for
  an ETH call "expiring this Friday", the agent read `chain --underlying ETH`, which shows
  only the tenor's one expiry (13 November), and told the owner Paradex had no 30 October
  expiry, though its own listing showed one. "Weekly" aims 9 days out, so a Friday 4 days
  away could not be reached at all.

## 2.7.0

- **Rysk, as a third venue.** Selling a cash-secured put on Rysk is the same procedure as
  on Derive and Paradex with `--venue rysk`: the checks, the
  bad case first, one key, the card, the lifecycle duty. `references/rysk.md` is only
  what differs - puts only, no buy-back, USDC in the owner's HyperEVM wallet, a card good
  for 5 minutes that the server re-quotes against the floor, and **physical
  settlement**: an assigned put delivers the asset, which is never sold unless the owner
  asks. Replaces the separate `rysk` skill (`mamamatcha/butler-skill-rysk`, deprecated),
  so an owner installs one skill for all three venues.
- `references/rysk-helper.md`: Rysk's quote script, now speaking the Derive helper's
  field names (`net_premium_usd`, `fee_usd` from Rysk's `/api/gas`, `min_premium_usd`,
  `bad_case`), so `SKILL.md` steps 3 and 5 read either. Rysk names no stablecoin and a
  skill may carry no address, so the collateral comes from the account read
  (`collateral.address`, passed as `--pay-with`).
- Files `options-lifecycle@8`, which reads exactly as @7 for Derive and Paradex and adds
  `VENUE: rysk`, reporting what Rysk actually paid out.
- `templates/options-lifecycle` 8: Rysk names, no early-close check or delivery buy on
  Rysk, and the outcome from `settled` in `/options/account` rather than from the price,
  since near the strike the maker chooses whether to exercise.
- CI validates `templates/options-account`; it still named `derive-account`, removed in
  2.6.0, so every run since failed.

## 2.6.2

- **What a venue lists comes from the helper.** `chain` with no `--underlying` lists every
  underlying the venue has order-book options on, with its expiries (ISO, UTC), from one
  read of the venue's market list (Derive: its option currencies). Seen in QA: asked
  "what stock options can I trade on Paradex", an agent answered from web docs, wrote
  Paradex's symbols in Derive's form (`META-USD-20261130-650-C`) and named `MU`
  "Mitsubishi UFJ Financial Group". SKILL.md step 2 now names the listing, and names are
  said as listed, never with a company name (no venue gives one). `references/paradex.md`
  notes that Paradex's list includes stocks, indices and commodities.
- Check 4 of "Never file without all four" is the **helper's** quote: in the same test the
  agent filed a buy priced from Paradex's raw mark, with no quote at all.
- To stay under 12,000 characters: the `"title"` line in step 7 is dropped (the JSON there
  already carries one) and step 6's pointer to `references/paradex.md` is shorter.

## 2.6.1

- **Derive's minimum deposit is $10, not $5.** Derive's docs now say a deposit worth less
  than $10 is not credited and goes to its Security Module, and Butler's server refuses
  under $10. `references/venue.md` names $10 alone: the $5.05 bridge floor and the
  "never send under $6" line are gone.

## 2.6.0

- **Paradex, a second venue.** Every command takes `--venue paradex` (bevo-server's options
  rail is venue-neutral: `docs/options-venues.md`). New `references/paradex.md`: names
  (`ETH-USD-27NOV26-2600-C`), the $20-of-underlying minimum, Paradex's retail fee and
  price band, order-book markets only, the account fields (`address`, `otherPositions`),
  funding from Base USDC only, and withdrawing to Base.
- The helper reads Paradex with `--venue paradex` (any command): Paradex's market list
  and summaries, reshaped into Derive's fields so the quote logic, its gates and every
  field are the same; RFQ-only markets are skipped, fees follow Paradex's retail
  schedule (Butler's orders are retail), and a side priced outside the market's price
  band is dropped, since no order can reach it. Derive's output is byte-identical
  (replayed against the same Derive answers through 2.5.0's script and this one).
- SKILL.md: a venue rule (Before you start, 6); the lifecycle duty is `options-lifecycle@7`
  with `VENUE`; step 9 files one `options-account` duty for every venue; one failure row for every
  `OPTIONS_*` refusal, whose reply now carries the server's `hint`; the helper lines drop
  flags that were their defaults, to stay under 12,000 characters.
- `templates/options-lifecycle` 7: `VENUE`, Paradex names, settlement read by instrument.
- **One Platforms duty for every venue.** New `templates/options-account` 1: one duty per
  owner reads bevo-server's `/options/account` once and keeps a row for each venue whose
  account exists (Derive and Paradex), at the venue's own `worthUsd`, with its positions
  listed and the row's name and site from the read. A venue bevo-server adds appears on
  the next check, with nothing refiled. It keeps Derive's deposit-landed note, only for a
  venue with `depositsLandLater`. Step 9 files it whenever an account exists and it is
  missing, unasked, and deletes any `derive-account` duty, which it supersedes. Needs
  bevo-server's `worthUsd` and `depositsLandLater` (bevo-server#1179).
- **`templates/derive-account` removed.** `options-account` supersedes `derive-account@1`,
  so the registry resolves that ref to it; a duty already running it keeps its stored code
  and writes the same Derive row until step 9 replaces it. Its last copy is at `v2.4.0`.
- **Paradex withdrawals.** `acp options withdraw --venue paradex` pays to the owner's
  wallet on Base through Layerswap, usually within a minute, less a few cents; no
  `:home` leg (`references/paradex.md` § Withdrawing).

## 2.5.0

- **Options outside ETH and BTC trade.** Derive splits its markets into risk universes
  (PRIME: ETH, BTC; ALT: SOL, XRP, ADA, ZEC…; MIDCAP: HYPE; RWA: gold), and an account
  trades only its own. Every SOL attempt failed as `Zero liquidity … (11009)` because the
  owner's only account was PRIME. Butler's server now opens the owner's account in the
  option's universe on first use and moves just the USDC a trade needs into it after the
  card is approved (bevo-server: risk-universe funding). The skill files the same commands;
  it does not move funds itself.
- `account.md`: free USDC and positions total every Derive account, `account.accounts`
  lists each, and a new section says what the server moves and when, and what to tell
  the owner (`funding` in the outcome, the card's `Account` line). Withdrawals take the
  total; the server gathers it first.
- `venue.md`: one subaccount per risk universe, and why the wrong one says 11009.
- SKILL.md: step 4 says free USDC spans the accounts and the server moves it; step 6
  relays `funding`; step 5's one-bound line shortened to stay under 12,000 characters.

## 2.4.0

- **Derive on the wallet's Platforms tab.** After a confirmed `acp options deposit`, and
  in step 1 whenever `account.exists`, the skill files the new `derive-account@1` duty
  once, if `duty_list` has none (new step 9; step 4 sends a deposit there once it
  lands, so the watcher is filed in the same turn). That duty keeps one Platforms row at what
  the account is worth, every 10 minutes, and tells the owner when a deposit lands.
  Butler never writes its own Derive watcher and never runs `bevo-platforms set` for
  Derive: the duty owns the row. Butler itself no longer explains `acp options` and
  follows a skill's own steps for a platform row (virtuals-agent#218).
- **Every duty has a `"title"`.** The container refuses a create without one, and step 7's
  JSON had none.
- **A second duty from the same template in one chat** names the earlier ones in
  `"alongside"`, or the container refuses it as a follow-up. A duty from another template,
  like the account watcher beside a per-position one, needs none.
- **The duty templates live here now**, under `templates/`, beside the skill that files
  them: `options-lifecycle` (moved from the deprecated `butler-skill-options-lifecycle`)
  and the new `derive-account`. The hub lists each with a `path` into this repo.
- Step 7 files `options-lifecycle@6` (was `@4`): an option closed early ends the duty
  whenever it was closed (`@5`), and its Duties row shows a status line (`@6`).
- `account.md`: the Platforms row belongs to the watcher duty and catches up within
  about 10 minutes, so a row behind the read is that delay.
- SKILL.md stays under 12,000 characters by dropping lines that say again what is said
  elsewhere: the failure rows "not enough free USDC" (step 4), "close larger than held"
  (the "they hold it" gate and step 2) and "Derive unreachable" (step 1 and
  `account.md`); step 1's field list, the position sign and Look's `summary` / `pnlUsd`
  (all in `account.md`); "buying back can cost more" (step 3's `result_usd`); and the
  withdrawal's route detail in step 8 (`account.md`).

## 2.3.2

- **Sizes are in the asset.** 1 contract is 1 ETH: 0.16 is 0.16 ETH, and Derive's 0.1
  is only its minimum. Owners hear sizes as "0.16 ETH", never "contracts", and the
  agent never converts. Seen live: told "sell 5 of my ETH calls", an agent said
  "five contracts would be 0.5 ETH", while cards and duties count 1 contract as 1 ETH.
- **Derive figures come only from this turn's reads**, never memory: a stored note
  that disagrees with `acp options account` is wrong and gets corrected. The "0.5 ETH"
  came from the agent's own working memory, saved in an earlier session as something
  the owner had "clarified".
- **Positions are relayed, not priced.** `acp options account` now gives each position
  an owner-ready `summary` plus `valueUsd`, `costUsd`, `pnlUsd` and `expiresIn`, with the
  per-unit prices renamed `markPerUnitUsd` and `entryPricePerUnitUsd` (bevo-server and
  virtuals-agent changes that ship with this). `account.md` relays `summary` as written,
  answers "up or down" from `pnlUsd`, and never works out a value, profit or date. Seen
  live: "marked at ~$20.69" for a 0.16 ETH position worth about $3.30. Replays with a
  poisoned memory: account checks right 8 of 8 with the new fields; without `pnlUsd`,
  agents asked "up or down" computed it themselves and one flipped the sign of a whole
  position. On an older server, sizes are said in the asset and `mark` labelled per ETH.
- SKILL.md drops lines `account.md`, step 1 and the failure table already carry, to
  stay under 12,000 characters.

## 2.3.1

- **Selling says the bad case first, with a dollar figure.** The sell quote gains
  `bad_case`: the asset 25% below spot (`price`, `fall_pct`) and `loss_usd`, what the
  note is down at expiry there, premium counted. The skill forbids computing numbers,
  and no field carried a loss, so agents dropped the loss example and led with APR.
  `selling.md`'s four beats now open with the bad case (they used to put it third,
  against SKILL.md); `apr_pct` comes last, if at all.
- **The ownership question stands alone, and a no ends it.** "Happy to own 0.13 ETH at
  $2,200 on 30 October?" is asked on its own after the offer. A no, a "maybe", or a
  yes to the money with a no to the asset ends selling: no other strike, tenor, size
  or asset, since every cash-secured put carries the same promise. Seen in testing:
  told no to owning ETH, an agent offered quarterly ETH puts.
- `screen` is never shown as an APR menu; with more than one tradeable asset, the
  owner names the one they would own.
- **Never file without all four**, a gate in Before you start that every `acp options
  open`, `buy` or `close` must pass, from the owner's own words: they chose it (asset
  and amount, or option and size), they hold it (a close is at most `positions`' size),
  they said yes to the number (loss, ownership, floor or ceiling, with its dollar
  figure), and the quote is fresh (re-quoted after their last answer). Seen in
  testing: told "just buy whatever ETH call looks good", an agent made up a $10 budget
  and quoted the default strike; told "sell 5 of my ETH calls" with 0.16 held, it
  filed 0.16 at a floor it chose, on a 91-second-old quote, never saying 5 was more
  than held.
- Closing asks for the floor or ceiling, with `min_proceeds_usd` / `max_cost_usd` as
  the suggestion, instead of using it unless the owner names one. `buying.md` gains
  "Choosing is theirs" (no picking, no made-up budget, the strike rule said as a
  starting point; the loss figure goes in the question itself) and a size check
  before any close.
- A close that does not fill is "nobody bought at that floor", never "no liquidity",
  and is re-quoted, never re-filed at the same floor. Seen in testing: three
  sell-backs at a $4.05 floor above the bid failed and were reported as zero
  liquidity. `no live bid` on a close says holding to expiry costs nothing.
- Step 5 opens with "run the quote again now, after their last answer", and selling
  quotes the asset the owner named, screening only when they named none. Found by
  replaying the test prompts against this skill: an agent filed from its pre-answer
  quote, and one screened every asset after the owner had said ETH.
- The gate covers `acp options deposit` too, and step 4 funds only with all four met:
  in a replay an agent took "yes to all, go ahead" after the first-time check as
  approval and filed a $307 deposit without asking the ownership question. `selling.md`
  says those yeses are not a yes to a trade, and that a no to owning the asset is not
  followed by an invitation to name another.
- Step 7's `duty_create` example uses placeholders; an agent had taken its real-looking
  `SOL-20261030-160-C` for a holding and tried to close it. The `DELIVER_ASSET` token
  rules moved to `selling.md`; SKILL.md trims repeated limits and funding detail
  (still in `venue.md`) to stay under 12,000 characters.

## 2.3.0

- Routes more check and withdraw asks here, on top of 2.2.1's **Look or withdraw**:
  keywords `derive positions`, `my option positions`, `withdraw from derive`, `withdraw
  my free usdc`, and a description that names checking and withdrawing, so an installed
  skill is picked for them too. "Free USDC" is Derive's `freeForNewPutsUsd`, not wallet
  cash; a look is step 1 and then stop.
- The Derive portfolio comes from `acp options account` and only from it. `bevo-read
  assets` has no Derive section: its `perps` is Hyperliquid and its `cashUsd` the wallet.
  A butler had reported Derive as empty from Hyperliquid's $0 while the account held
  $1.62 free and four options. Step 1 now reads the account first, and the wallet only
  to fund a trade.
- A withdrawal is at most this turn's `freeForNewPutsUsd`, rounded down to the cent; the
  owner hears the up-to-$1 fee before it is filed.
- New `references/account.md`: what each `acp options account` field means, how to answer
  a check, the withdrawal rules, and worked sentences.
- Some wording in steps 4 to 7 is shorter, with the same rules, to keep the body under the
  hub's 12,000-character limit.

## 2.2.1

- A fourth case, **Look or withdraw**: "what's my free USDC in Derive", "list my
  positions", "withdraw my free USDC" are answered from `acp options account` and
  step 8. Derive money is never in `bevo-read assets`, and a withdrawal is `acp
  options withdraw`, never an `acp trade`. Seen live: asked to withdraw, an agent
  without this skill loaded traded Base USDC for Base USDC and called it done, then
  read Hyperliquid's $0 as the Derive balance. Keywords gain `withdraw`, `derive`,
  `options account`, `options positions`, `free usdc`.

## 2.2.0

- Every asset Derive lists options on, not only ETH and BTC. The lifecycle duty is
  `options-lifecycle@4`, which reads Derive's own index for the heads-up, so a trade
  files it with no `TOKEN_ID`. The token pin is filed only with `DELIVER_ASSET`, when
  the owner asked to own the asset after an assigned put.

## 2.1.1

- Funding no longer says "from Base". Butler's trade bot takes deposit USDC from
  whichever chains the owner's wallet holds it on, gathering from several when none
  covers alone, so the skill tells the agent never to judge a deposit by one chain's
  balance and how to answer "can I fund this?". Ethereum USDC stays the `--from 1`
  exception. New failure row for a wallet that cannot cover the deposit.
- Mainnet only: the helper's network flag and every mention of a test venue are gone.
  Butler's server trades Derive mainnet.

## 2.1.0

- **Buying back a sold note** before expiry: `acp options close --instrument --size
  --max-cost`. A close now takes one bound, which names the direction:
  `--min-proceeds` sells back a bought option, `--max-cost` buys back a sold one. The
  helper's new `quote --side buyback --instrument --size [--premium-received <usd>]`
  prices it on the ask and returns `total_cost_usd`, `max_cost_usd` (5% room),
  `frees`, and `result_usd` (premium received less the buy-back cost), with a warning
  when that is a loss. Refused only with no ask or an ask thinner than the size.
- The first-time check for selling no longer says "no early exit": getting out early
  means buying the note back, which can cost more than it brought in.
- After a close either way, the lifecycle duty is deleted, or re-filed for what is
  still open.
- Funding: never under $6 from Base. The server bridges at a fixed 1% slippage and
  refuses a bridge whose guaranteed arrival is under $5.05; the bridge itself costs
  about $0.10.

## 2.0.0

- Renamed from `yield-notes` to `options-trading` (a new skill name, so a major
  version). Keywords cover buying calls and puts and hedging as well as income.
- **Buying**: `acp options buy --instrument --size --max-cost`. The helper's new
  `quote --side buy --product call|put --budget <usd>` (or `--size` for a hedge) sizes
  what the budget buys at the ask plus Derive's fee with 5% room, and returns
  `total_cost_usd`, `max_loss_usd`, `breakeven` and `max_cost_usd` (the `--max-cost`
  bound, never over the budget). Buyer gates: no live ask, ask thinner than the size,
  ask more than 5 vol points over mark ("paying N% over fair value"), fees over 15% of
  the premium, budget under Derive's minimum. The skill says plainly it is not yield
  and gets an explicit yes to losing the whole cost.
- **Closing**: `acp options close --instrument --size --min-proceeds` sells back a
  bought option before expiry. The helper's `quote --side close` prices it on the
  bid (`net_proceeds_usd`, `min_proceeds_usd`, `warnings`). A sold note still cannot
  be closed.
- The lifecycle duty is `options-lifecycle@3` for every trade: `cash_secured_put` as
  before, `long_call` / `long_put` after a confirmed buy (`PREMIUM_USD` =
  `totalCostUsd`, `COLLATERAL_USD` 0). After a confirmed close the skill deletes it.
- Funding: never under about $10 from Base, since the server refuses a bridge whose
  worst-case arrival is under $6.
- `SKILL.md` is restructured around the three intents; the explanation moved to
  `references/selling.md` (formerly `notes.md`) and the new `references/buying.md`.
  Selling behaves as in 1.2.1, and the sell quote is unchanged.

## 1.2.1

- The lifecycle duty is filed with `TOKEN_ID`, the underlying pinned to one token
  (`native:8453` for ETH; the verified Base row from `bevo-read token-search` for
  BTC), which options-lifecycle@2 prices with `/token-stats` and delivers.

## 1.2.0

- Funding is one command: `acp options deposit` bridges the owner's Base USDC
  straight into their own Derive account (Butler's server picks the deposit address;
  the bridge fee comes out of the amount). The separate `acp trade` Base-to-Ethereum
  leg and the "deposit what arrived" step are gone.
- The skill deposits the shortfall plus a small margin for the bridge fee (about 1%,
  at least $1), says so to the owner, and waits on `acp options account` until the
  credit covers the note. `--from 1` only when the owner already holds USDC on
  Ethereum.
- A failed or partial deposit is reported with its reason as given, and the account
  is re-read before any new deposit - never a re-run. Withdrawing is unchanged.

## 1.1.0

- Cash-secured puts only, as the rail offers in v1. The covered-call offer is gone
  from the procedure; Limits says calls come later. The helper still quotes them.
- The fill is read from `bevo-read request <key> --route options`:
  `approvalOutcome` (`filledSize`, `netPremiumUsd`, `collateral`, `instrument`,
  `strike`) once `approvalStatus` is `confirmed`, `approvalFailureReason` when it
  failed. The lifecycle duty is filed from those fields.
- The skill waits for the server's outcome note or checks the request; it never
  re-runs a command to find out. A failed bridge, deposit or withdrawal card is
  reported with its reason as given.
- Never asks the owner about Ethereum gas (Butler's server covers it). Deposits under
  $5 are refused by the server as well as by the skill.
- Withdrawals: about 20 minutes, a fee of up to $1.

## 1.0.0

- Derive v3. The helper reads `api.derive.xyz/v3`: one `public/get_tickers` call per
  expiry instead of a ticker per strike, the slim ticker keys, and the fee terms from
  each instrument. v2 has been dead since 6 Oct 2026.
- Opening is live through Butler's `acp options` rail: `acp options account` to read
  the Derive account, `acp trade` to bridge USDC from Base to Ethereum,
  `acp options deposit`, `acp options open` and `acp options withdraw`, each an
  approval card the owner signs in the app. The helper has no money path left.
- The quote carries the open's bounds: `min_premium_usd` (95% of the net premium,
  rounded down) and `collateral.amount` in the unit `--max-collateral` takes (USDC for
  a put, the asset for a call), plus `collateral.usd`.
- The `options-lifecycle@2` duty is filed only after a confirmed fill, with the fill's
  own size and net premium.
- Removed `spikes/`: v3 has no session key to register, and funding goes through the
  rail.

## 0.1.0

- First prototype. Screens and quotes fully collateralised single-leg notes
  (cash-secured put, covered call) against Derive's public API.
- Quote-time liquidity gating instead of an asset allowlist: a note is offered only
  when the bid is within 5 vol points of mark, fees are under 15% of the premium,
  and the best bid covers the whole note. On a measured day that clears ETH and BTC
  and rejects the other ten listed assets.
- Monthly tenors by default. Weeklies lose ~15% of the premium to fees at $5,000 and
  far more below that, so the fee-drag gate rejects them at retail size.
- Money paths (`open`, `close`, `positions`, `withdraw`) refuse with an explanation
  until spikes A1 and A4 pass.
