"""`scripts/quote.py`: the Virtuals platform fee in every Derive quote, offline."""
import contextlib
import io
import pathlib
import sys
import types
import unittest
from unittest import mock

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "quote.py"

ETH_CALL = "ETH-20261204-1900-C"
INST = {
    "instrument_name": ETH_CALL, "is_active": True,
    "option_details": {"strike": "1900", "expiry": 4_000_000_000, "option_type": "C"},
    "amount_step": "0.01", "minimum_amount": "0.01",
    "base_fee": "0.5", "taker_fee_rate": "0.0003", "mark_price_fee_rate_cap": "0.125",
}
TICKER = {"b": "48", "B": "10", "a": "50", "A": "10", "M": "49", "I": "2000",
          "option_pricing": {"bi": "0.60", "ai": "0.62", "i": "0.61", "d": "0.5"}}


def helper():
    mod = types.ModuleType("quote")
    exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), mod.__dict__)
    mod.active_options = lambda cur, t: [INST]
    mod.tickers_for = lambda cur, expiry: {ETH_CALL: TICKER}
    mod.time = types.SimpleNamespace(time=lambda: 3_990_000_000)
    return mod


def run(h, *argv):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "argv", ["quote.py", *argv]), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            h.main()
            code = 0
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class PlatformFeeTest(unittest.TestCase):
    def setUp(self):
        self.h = helper()

    def quote(self, *argv):
        import json
        code, out, err = run(self.h, "quote", *argv)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_a_derive_quote_needs_the_rate(self):
        code, _, err = run(self.h, "quote", "--side", "close", "--instrument", ETH_CALL, "--size", "1")
        self.assertEqual(code, 2)
        self.assertIn("--platform-fee-rate", err)
        self.assertIn("platformFeeRate", err)

    def test_a_rate_out_of_range_is_refused(self):
        code, _, err = run(self.h, "quote", "--side", "close", "--instrument", ETH_CALL,
                           "--size", "1", "--platform-fee-rate", "0.5")
        self.assertEqual(code, 2)
        self.assertIn("0 to 0.05", err)

    def test_zero_rate_is_derives_fee_alone(self):
        q = self.quote("--side", "close", "--instrument", ETH_CALL, "--size", "1", "--platform-fee-rate", "0")
        # 0.5 + min(0.0003 x 2000, 0.125 x 49) = 1.10
        self.assertEqual((q["fee_usd"], q["venue_fee_usd"], q["platform_fee_usd"]), (1.1, 1.1, 0))
        self.assertEqual(q["net_proceeds_usd"], 46.9)

    def test_the_platform_fee_is_on_the_book_price_and_in_every_total(self):
        close = self.quote("--side", "close", "--instrument", ETH_CALL, "--size", "1",
                           "--platform-fee-rate", "0.005")
        self.assertEqual((close["fee_usd"], close["venue_fee_usd"], close["platform_fee_usd"]), (1.34, 1.1, 0.24))
        self.assertEqual(close["net_proceeds_usd"], 46.66)  # 48 - 1.10 - 0.24

        back = self.quote("--side", "buyback", "--instrument", ETH_CALL, "--size", "1",
                          "--premium-received", "60", "--platform-fee-rate", "0.005")
        self.assertEqual((back["fee_usd"], back["platform_fee_usd"]), (1.35, 0.25))
        self.assertEqual(back["total_cost_usd"], 51.35)  # 50 + 1.10 + 0.25
        self.assertEqual(back["result_usd"], 8.65)

    def test_the_parts_add_up_to_the_fee(self):
        for premium, venue in ((18.22, 0.704), (5.0, 0.6234), (77.6, 0.561685)):
            parts = self.h.fee_fields(venue, self.h.platform_fee(premium))
            self.assertAlmostEqual(parts["venue_fee_usd"] + parts["platform_fee_usd"], parts["fee_usd"], places=9)

    def test_a_budget_buys_less_once_the_platform_fee_is_counted(self):
        args = ("--side", "buy", "--product", "call", "--underlying", "ETH", "--budget", "53.66", "--strike", "1900")
        free = self.quote(*args, "--platform-fee-rate", "0")
        paid = self.quote(*args, "--platform-fee-rate", "0.005")
        self.assertEqual(free["platform_fee_usd"], 0)
        self.assertEqual((free["size"], paid["size"]), (1, 0.99))
        self.assertEqual(paid["total_cost_usd"], round(paid["premium_usd"] + paid["fee_usd"], 2))
        self.assertLessEqual(paid["max_cost_usd"], 53.66)

    def test_paradex_takes_no_platform_fee(self):
        self.h.V.update(self.h.VENUES["paradex"])
        self.h.PLATFORM["rate"] = 0.005
        with mock.patch.object(sys, "argv", ["quote.py", "quote", "--venue", "paradex",
                                             "--side", "close", "--instrument", "X", "--size", "1",
                                             "--platform-fee-rate", "0.005"]):
            with mock.patch.object(self.h, "run_quote", lambda p, a: {"rate": self.h.PLATFORM["rate"]}):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.h.main()
        self.assertIn('"rate": 0', out.getvalue())


if __name__ == "__main__":
    unittest.main()
