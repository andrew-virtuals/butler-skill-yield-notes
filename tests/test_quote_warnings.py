"""`scripts/quote.py quote`: a poor price warns, and only the venue's own limits refuse."""
import pathlib
import time
import types
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "quote.py"


def helper():
    mod = types.ModuleType("quote")
    exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), mod.__dict__)
    return mod


def inst(name, strike, minimum, step):
    return {"instrument_name": name, "minimum_amount": minimum, "amount_step": step,
            "base_fee": "0.5", "taker_fee_rate": "0.0003", "mark_price_fee_rate_cap": "0.125",
            "option_details": {"strike": strike, "expiry": 0, "option_type": "P"}}


def ticker(index, bid, bid_sz, ask, ask_sz, mark, bid_iv, ask_iv, mark_iv):
    return {"I": index, "b": bid, "B": bid_sz, "a": ask, "A": ask_sz, "M": mark,
            "option_pricing": {"bi": bid_iv, "ai": ask_iv, "i": mark_iv, "d": -0.2}}


class WarningsTest(unittest.TestCase):
    def setUp(self):
        self.q = helper()
        self.expiry = int(time.time()) + 44 * 86400

    def chain(self, i, t):
        self.q.load_chain = lambda *a, **k: (self.expiry, [i], {i["instrument_name"]: t})

    def test_a_bid_thinner_than_the_note_warns(self):
        # BTC on 2026-11-11: the best bid fell to 0.01 under a 0.01538 note.
        self.chain(inst("BTC-20261225-65000-P", 65000, 0.01, 0.00001),
                   ticker(73609, 999, 0.01, 1100, 2, 1034, 0.4191, 0.44, 0.4243))
        q = self.q.build_quote("cash_secured_put", "BTC", 1000, strike=65000)
        self.assertTrue(q["tradeable"])
        self.assertEqual(q["reasons"], [])
        self.assertIn("the best bid is only 0.01 contracts and this note is 0.01538 - "
                      "it may fill part-way", q["warnings"])

    def test_a_wide_market_and_heavy_fees_warn(self):
        # NVDA on 2026-11-16: 6.3 vol points wide, fees 20% of a one-contract premium.
        self.chain(inst("NVDA-20261125-150-P", 150, 1, 1),
                   ticker(161.16, 2.74, 14, 3.84, 36, 3.26, 0.6922, 0.8226, 0.7554))
        q = self.q.build_quote("cash_secured_put", "NVDA", 296, strike=150)
        self.assertTrue(q["tradeable"])
        self.assertEqual(len(q["warnings"]), 2)
        self.assertTrue(q["warnings"][0].startswith("the market is 6.3 vol points wide"))
        self.assertTrue(q["warnings"][1].startswith("fees are 20% of the premium"))

    def test_under_the_venue_minimum_still_refuses(self):
        self.chain(inst("NVDA-20261125-150-P", 150, 1, 1),
                   ticker(161.16, 2.74, 14, 3.84, 36, 3.26, 0.6922, 0.8226, 0.7554))
        q = self.q.build_quote("cash_secured_put", "NVDA", 100, strike=150)
        self.assertFalse(q["tradeable"])
        self.assertTrue(q["reasons"][0].startswith("collateral too small"))

    def test_no_bid_still_refuses(self):
        self.chain(inst("NVDA-20261125-200-P", 200, 1, 1),
                   ticker(161.16, 0, 0, 0, 0, 39.15, 0, 0, 0.777))
        q = self.q.build_quote("cash_secured_put", "NVDA", 400, strike=200)
        self.assertFalse(q["tradeable"])
        self.assertTrue(q["reasons"][0].startswith("no live bid"))

    def test_a_wide_ask_warns_a_buyer(self):
        self.chain(inst("NVDA-20261125-150-P", 150, 1, 1),
                   ticker(161.16, 2.74, 14, 3.84, 36, 3.26, 0.6922, 0.8226, 0.7554))
        q = self.q.build_buy_quote("put", "NVDA", budget_usd=50, strike=150)
        self.assertTrue(q["tradeable"])
        self.assertTrue(any(w.startswith("the market is 6.7 vol points wide against the buyer")
                            for w in q["warnings"]))


if __name__ == "__main__":
    unittest.main()
