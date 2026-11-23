"""Quote helpers: a poor price warns, a very poor one is a safeguard the owner may
waive, and only the venue's own limits refuse outright."""
import pathlib
import time
import types
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"


def helper(name):
    mod = types.ModuleType(name)
    path = SCRIPTS / ("%s.py" % name)
    exec(compile(path.read_text(), str(path), "exec"), mod.__dict__)
    return mod


def inst(name, strike, minimum, step):
    return {"instrument_name": name, "minimum_amount": minimum, "amount_step": step,
            "base_fee": "0.5", "taker_fee_rate": "0.0003", "mark_price_fee_rate_cap": "0.125",
            "option_details": {"strike": strike, "expiry": 0, "option_type": "P"}}


def ticker(index, bid, bid_sz, ask, ask_sz, mark):
    return {"I": index, "b": bid, "B": bid_sz, "a": ask, "A": ask_sz, "M": mark,
            "option_pricing": {"bi": 0.7, "ai": 0.8, "i": 0.75, "d": -0.2}}


NVDA_150 = (inst("NVDA-20261125-150-P", 150, 1, 1), ticker(161.16, 2.74, 14, 3.84, 36, 3.26))


class DeriveQuoteTest(unittest.TestCase):
    def setUp(self):
        self.q = helper("quote")
        self.expiry = int(time.time()) + 30 * 86400

    def chain(self, i, t):
        self.q.load_chain = lambda *a, **k: (self.expiry, [i], {i["instrument_name"]: t})

    def test_a_bid_thinner_than_the_note_only_warns(self):
        # BTC, 2026-11-11: the best bid fell to 0.01 under a 0.01538 note at the same price.
        self.chain(inst("BTC-20261225-65000-P", 65000, 0.01, 0.00001),
                   ticker(73609, 999, 0.01, 1100, 2, 1034))
        q = self.q.build_quote("cash_secured_put", "BTC", 1000, strike=65000)
        self.assertTrue(q["tradeable"])
        self.assertEqual((q["reasons"], q["safeguards"]), ([], []))
        self.assertIn("the best bid is only 0.01 contracts and this note is 0.01538 - "
                      "it may fill part-way", q["warnings"])

    def test_one_nvda_contract_warns_on_fees_and_leaves_a_small_spread_alone(self):
        # NVDA, 2026-11-16: 16% of the value is only $0.52 on one contract; fees are 20%.
        self.chain(*NVDA_150)
        q = self.q.build_quote("cash_secured_put", "NVDA", 296, strike=150)
        self.assertTrue(q["tradeable"])
        self.assertEqual(q["safeguards"], [])
        self.assertEqual(q["warnings"], ["fees are 20% of the premium: a bigger ticket or a "
                                         "longer tenor keeps more of it"])

    def test_a_spread_between_the_two_figures_warns(self):
        # ZEC, 2026-11-11: the 27 Nov $900 put gave up 17% of its value.
        self.chain(inst("ZEC-20261127-900-P", 900, 1, 0.1), ticker(975.1, 47.6, 42.1, 70, 5, 57.2))
        q = self.q.build_quote("cash_secured_put", "ZEC", 1000, strike=900)
        self.assertTrue(q["tradeable"])
        self.assertEqual(q["warnings"], ["the market is wide: selling here hands over 17% of the "
                                         "option's value ($10.56)"])

    def test_a_spread_past_the_safeguard_holds_until_waived(self):
        self.chain(inst("ZEC-20261204-800-P", 800, 1, 0.1), ticker(975, 72, 40, 110, 5, 100))
        q = self.q.build_quote("cash_secured_put", "ZEC", 800, strike=800)
        self.assertFalse(q["tradeable"])
        self.assertTrue(q["waivable"])
        self.assertEqual(q["reasons"], [])
        self.assertEqual(q["safeguards"], [{
            "id": "spread", "waived": False,
            "text": "the market is wide: selling here hands over 28% of the option's value "
                    "($28.00) (safeguard: 20%)"}])
        self.assertNotIn("waive", q)

        q = self.q.build_quote("cash_secured_put", "ZEC", 800, strike=800, waived=("spread",))
        self.assertTrue(q["tradeable"])
        self.assertFalse(q["waivable"])
        self.assertTrue(q["safeguards"][0]["waived"])
        self.assertEqual(q["waive"], "spread")

    def test_fees_past_the_safeguard_hold_until_waived(self):
        # The NVDA $140 put: one contract bids $0.87 and the base fee alone is $0.50.
        self.chain(inst("NVDA-20261125-140-P", 140, 1, 1), ticker(161.16, 0.87, 4, 1.78, 32, 1.31))
        q = self.q.build_quote("cash_secured_put", "NVDA", 140, strike=140)
        self.assertEqual([s["id"] for s in q["safeguards"]], ["fees"])
        self.assertTrue(q["waivable"])
        self.assertIn("the premium is only $0.87", q["warnings"])
        q = self.q.build_quote("cash_secured_put", "NVDA", 140, strike=140, waived=("fees", "spread"))
        self.assertTrue(q["tradeable"])
        self.assertEqual(q["waive"], "fees")

    def test_the_venue_minimum_and_no_bid_refuse_and_cannot_be_waived(self):
        self.chain(*NVDA_150)
        q = self.q.build_quote("cash_secured_put", "NVDA", 100, strike=150, waived=("spread", "fees"))
        self.assertFalse(q["tradeable"])
        self.assertFalse(q["waivable"])
        self.assertTrue(q["reasons"][0].startswith("collateral too small"))
        self.chain(inst("NVDA-20261125-200-P", 200, 1, 1), ticker(161.16, 0, 0, 0, 0, 39.15))
        q = self.q.build_quote("cash_secured_put", "NVDA", 400, strike=200, waived=("spread",))
        self.assertFalse(q["tradeable"])
        self.assertFalse(q["waivable"])
        self.assertTrue(q["reasons"][0].startswith("no live bid"))

    def test_a_buyer_hears_the_spread_too(self):
        self.chain(*NVDA_150)
        q = self.q.build_buy_quote("put", "NVDA", budget_usd=50, strike=150)
        self.assertTrue(q["tradeable"])
        self.assertIn("the market is wide: you would be paying 18% over fair value ($6.96)", q["warnings"])

    def test_the_command_line_names_only_known_safeguards(self):
        self.assertEqual(self.q.safeguard_list("Spread,fees"), ("spread", "fees"))
        with self.assertRaises(Exception):
            self.q.safeguard_list("depth")


class RyskExerciseTest(unittest.TestCase):
    def setUp(self):
        self.rysk = helper("rysk")
        usdc = "0x00000000000000000000000000000000000usdc"
        self.usdc = usdc
        sol = {"expiry": "27NOV26", "expiration_timestamp": int(time.time() + 28 * 86400),
               "timeToExpiryDays": 28, "strike": 95, "isPut": True, "delta": -0.48, "index": 99.75,
               "products": [{"asset": "0xsol", "collateralAsset": usdc, "strikeAsset": "0xusd"}]}
        self.rysk.inventory = lambda: {"SOL": {"combinations": {"0": sol}}}
        self.rysk._tokens["0xsol"] = (999, "USOL", 18)
        self.rysk._fee = lambda *a, **k: 0.5
        self.rysk._call = lambda payload, want_id, tries=3, timeout=25: {
            "price": str(4 * 10 ** 18), "quantity": payload["params"]["quantity"],
            "validUntil": int(time.time()) + 120}

    def test_a_likely_exercise_holds_until_waived(self):
        q = self.rysk.quote("SOL", 950, pay_with=self.usdc, strike=95.0)
        self.assertFalse(q["tradeable"])
        self.assertTrue(q["waivable"])
        self.assertEqual(q["safeguards"][0]["id"], "exercise")
        q = self.rysk.quote("SOL", 950, pay_with=self.usdc, strike=95.0, waived=("exercise",))
        self.assertTrue(q["tradeable"])
        self.assertEqual(q["waive"], "exercise")


def minimum_inst(strike, minimum):
    return {"instrument_name": "HYPE-20261127-%s-P" % strike, "minimum_amount": minimum,
            "amount_step": 1, "option_details": {"strike": strike, "expiry": 0}}


class MinimumTest(unittest.TestCase):
    """`quote.py minimum`: the smallest put on Derive or Paradex, against a fixed chain."""

    def setUp(self):
        self.q = helper("quote")
        self.expiry = int(time.time()) + 25 * 86400
        chain = [minimum_inst(50, 10), minimum_inst(80, 10), minimum_inst(82.5, 10)]
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
