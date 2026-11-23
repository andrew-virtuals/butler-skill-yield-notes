# Changelog

## 1

- **First version.** Works one Derive order (open, buy or close) from the duty's own
  wallet, hands-free: an RFQ at the mark, then post-only at a target that walks from the
  mark toward the book over `WORK_MINUTES`, re-asking the makers each `STEP_MINUTES`,
  never past `WORST_PRICE`; at the deadline one RFQ and one immediate-or-cancel at
  `WORST_PRICE`, then a receipt against `FILL_NOW_PRICE`. Deposits its own wallet's USDC
  on Derive before it starts.
- **Live (2026-11-20).** A close sold back on the book at the deadline; a buy
  rested post-only, re-priced and asked the makers with no card. From those runs: a
  resting order sits on Derive's tick (`TICK_SIZE`) and moves only by more than 1.5
  ticks; a fast index move (0.3% within 5 minutes, not 30) keeps only the resting order
  off the book, never the makers or the book; new settings are a new order, with keys
  of their own (`<order>`); the receipt prices each fill before fees (a maker's or the
  book's gross, a resting fill at its limit), never from Derive's entry price, which
  carries the fee.
- **Quicker, and never dearer than the book.** A maker's quote is taken at once when it
  saves `TAKE_SAVING` (half) of the gap between the book and the mark, so an order whose
  maker was there from the start fills in its first minute and not hours into the
  ladder; `1` keeps the ladder alone. An RFQ's bound is never past the book's own price,
  at the deadline too, where a maker inside `WORST_PRICE` but dearer than the book used
  to be taken. A book that reaches the target is offered to the makers to beat first.
- **The makers' last quote is remembered.** The rail's refusal names the best quote; the
  duty asks again (3 minutes apart at the soonest) once the mark has moved enough for
  it to fit, and no longer only at each step.
- **Up to three commands a minute.** A cancel, the makers and a new resting order go in
  one run (none begun after 40 seconds), so a step takes the order off the book for
  seconds, not two minutes, and the deadline's three tries take one minute.
- **Fewer settings.** `STEP_MINUTES` defaults to an eighth of `WORK_MINUTES` (1 to 30),
  `FILL_NOW_PRICE` to `WORST_PRICE`. The receipt adds the saving in all and where each
  fill came from (a maker's quote, the resting order, the book), and says "about" when
  the rail's cent-rounded gross cannot price a small fill exactly.
- **What it holds is watched by `options-lifecycle@12`.** That duty now reads every
  Butler wallet's own options account, so this one finishes on its receipt.
- **Every choice is made after fees.** A resting fill pays Derive's maker fee, about $0.02
  on 0.1 ETH and no base fee (Derive's public fills, 2026-11-23); a maker's quote or the
  book pays the taker fee, $0.55 there. So the RFQ's line and the test for taking the book
  add that difference to the target: on a small order the duty rests rather than pay it,
  and a book inside the target by less than it gets a resting order a tick off it instead.
  The deadline still takes a maker or the book at `WORST_PRICE`, and a close, which cannot
  rest, compares prices alone. `MAKER_FEE_RATE` comes from the quote. The receipt adds the
  saving in all with fees counted each way. Placing, moving and cancelling an order cost
  nothing (measured live: three placed and cancelled, USDC unchanged).
- **Nothing is left resting.** Only the running duty can cancel an order resting from its
  wallet (the rail refuses a chat cancel with `--wallet`), so `STOP: true` ends an order
  early: it cancels what rests and sends the receipt. It no longer finishes with a
  remainder under the venue's minimum still on the book, and it cancels any order in its
  account that is not the one it works, on any option, before it does anything else.
