"""`scripts/quote.py minimum`: the smallest put on Derive or Paradex, against a fixed chain."""
import pathlib
import time
import types
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "quote.py"


def helper():
    mod = types.ModuleType("quote")
    exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), mod.__dict__)
    return mod


def inst(strike, minimum):
    return {"instrument_name": "HYPE-20261127-%s-P" % strike, "minimum_amount": minimum,
            "amount_step": 1, "option_details": {"strike": strike, "expiry": 0}}


class MinimumTest(unittest.TestCase):
    def setUp(self):
        self.q = helper()
        self.expiry = int(time.time()) + 25 * 86400
        chain = [inst(50, 10), inst(80, 10), inst(82.5, 10)]
        tickers = {i["instrument_name"]: {"I": 88.0} for i in chain}
        self.q.load_chain = lambda *a, **k: (self.expiry, chain, tickers)

    def test_the_rule_strike_and_the_lowest(self):
        m = self.q.build_minimum("hype")
        self.assertEqual((m["instrument"], m["min_size"], m["min_collateral_usd"]),
                         ("HYPE-20261127-80-P", 10, 800))
        self.assertEqual(m["lowest_strike"], {"instrument": "HYPE-20261127-50-P", "strike": 50,
                                              "min_size": 10, "min_collateral_usd": 500})
        self.assertEqual((m["venue"], m["settlement"], m["underlying"]), ("derive", "cash", "HYPE"))
        self.assertNotIn("net_premium_usd", m)
        self.assertNotIn("apr_pct", m)

    def test_a_named_strike(self):
        m = self.q.build_minimum("HYPE", strike=82.5)
        self.assertEqual(m["min_collateral_usd"], 825)

    def test_at_the_lowest_strike_it_is_not_repeated(self):
        self.assertIsNone(self.q.build_minimum("HYPE", strike=50)["lowest_strike"])


if __name__ == "__main__":
    unittest.main()
