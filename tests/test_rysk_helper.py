"""`scripts/rysk.py`: a named strike and day, and the minimum, against a fixed inventory."""
import pathlib
import time
import types
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "rysk.py"
DAY = 86400


def helper():
    mod = types.ModuleType("rysk")
    exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), mod.__dict__)
    return mod


def put(label, days, strike, delta):
    ts = int(time.time() + days * DAY)
    return {"expiry": label, "expiration_timestamp": ts, "timeToExpiryDays": days,
            "strike": strike, "isPut": True, "delta": -delta, "index": 2350.0, "products": []}


def day(combo):
    return time.strftime("%Y-%m-%d", time.gmtime(combo["expiration_timestamp"]))


class RyskPickTest(unittest.TestCase):
    def setUp(self):
        self.rysk = helper()
        self.combos = [
            put("SOON", 0.5, 2300, 0.45),
            put("WEEK", 9, 2100, 0.11), put("WEEK", 9, 2200, 0.21),
            put("FORT", 16, 2000, 0.09), put("FORT", 16, 2100, 0.15), put("FORT", 16, 56.5, 0.01),
            put("MONTH", 30, 2000, 0.14), put("MONTH", 30, 2100, 0.20),
        ]
        self.fort = day(self.combos[3])

    def pick(self, **kw):
        args = dict(tenor="monthly", otm_pct=10.0, target_delta=None)
        args.update(kw)
        return self.rysk._pick(self.combos, "ETH", **args)

    def test_tenor_alone_is_unchanged(self):
        self.assertEqual(self.pick()["expiry"], "MONTH")
        self.assertEqual(self.pick(tenor="weekly")["expiry"], "WEEK")

    def test_a_named_day_no_tenor_reaches(self):
        c = self.pick(on=self.fort)
        self.assertEqual((c["expiry"], c["strike"]), ("FORT", 2100))

    def test_a_named_strike_on_a_named_day(self):
        c = self.pick(on=self.fort, strike=2000.0)
        self.assertEqual((c["expiry"], c["strike"]), ("FORT", 2000))
        self.assertEqual(self.pick(on=self.fort, strike=56.5)["strike"], 56.5)

    def test_a_named_strike_at_the_tenor_expiry(self):
        self.assertEqual(self.pick(strike=2000.0)["expiry"], "MONTH")

    def test_a_strike_not_listed_names_the_ones_that_are(self):
        with self.assertRaises(self.rysk.RyskError) as e:
            self.pick(on=self.fort, strike=2050.0)
        self.assertEqual(str(e.exception),
                         "Rysk lists no ETH 2050 put on FORT; it lists 56.5, 2000, 2100")

    def test_a_day_not_listed_names_the_ones_that_are(self):
        with self.assertRaises(self.rysk.RyskError) as e:
            self.pick(on="2020-01-01")
        msg = str(e.exception)
        self.assertTrue(msg.startswith("Rysk lists no ETH put expiring on 2020-01-01; it lists "))
        self.assertIn(self.fort, msg)

    def test_a_named_day_inside_the_hour_is_not_offered(self):
        soon = put("NOW", 0.01, 2300, 0.5)
        with self.assertRaises(self.rysk.RyskError):
            self.rysk._pick([soon], "ETH", "monthly", 10.0, None, on=day(soon))

    def test_chain_lists_one_expiry_by_strike(self):
        self.rysk.inventory = lambda: {"ETH": {"combinations": {str(i): c for i, c in enumerate(self.combos)}}}
        rows = self.rysk.chain("eth", on=self.fort)
        self.assertEqual([r["instrument"] for r in rows],
                         ["ETH-FORT-56.5-P", "ETH-FORT-2000-P", "ETH-FORT-2100-P"])
        self.assertNotIn("price", rows[0])


USDC = "0x00000000000000000000000000000000000usdc"


class RyskMinimumTest(unittest.TestCase):
    """A maker that prices nothing under 10 SOL, as Rysk's SOL puts did in QA."""

    def setUp(self):
        self.rysk = helper()
        sol = put("27NOV26", 28, 88, 0.12)
        sol["index"] = 99.75
        sol["products"] = [{"asset": "0xsol", "collateralAsset": USDC, "strikeAsset": "0xusd"}]
        low = dict(sol, strike=79, delta=-0.03)
        self.rysk.inventory = lambda: {"SOL": {"combinations": {"0": sol, "1": low}}}
        self.rysk._tokens["0xsol"] = (999, "USOL", 18)
        self.asked = []
        self.refuse = "{'code': -32603, 'message': 'trade size too small'}"
        self.unpriced = set()

        def call(payload, want_id, tries=3, timeout=25):
            size = int(payload["params"]["quantity"]) / self.rysk.E18
            strike = int(payload["params"]["strike"]) / self.rysk.E8
            self.asked.append(size)
            if size < 10:
                raise self.rysk.RyskError(self.refuse)
            if strike in self.unpriced:
                raise self.rysk.RyskError("no maker answered")
            return {"price": str(16 * 10 ** 17), "quantity": payload["params"]["quantity"]}

        self.rysk._call = call

    def test_under_the_minimum_names_the_least_it_prices(self):
        q = self.rysk.quote("SOL", 5, pay_with=USDC)
        self.assertFalse(q["tradeable"])
        self.assertEqual(q["reasons"], ["collateral too small: Rysk prices no less than 10 SOL, which "
                                        "needs $880 on SOL-27NOV26-88-P and $790 on "
                                        "SOL-27NOV26-79-P, the lowest strike that day"])
        self.assertEqual((q["size"], q["min_size"]), (0.0, 10))
        self.assertEqual(self.asked[-6:], [0.1, 0.5, 1, 5, 10, 10])
        # Nothing to quote a downside or a premium from: none was priced for the owner.
        self.assertNotIn("bad_case", q)
        self.assertNotIn("net_premium_usd", q)

    def test_a_lowest_strike_no_maker_prices_is_left_out(self):
        self.unpriced.add(79.0)
        q = self.rysk.quote("SOL", 5, pay_with=USDC)
        self.assertEqual(q["reasons"], ["collateral too small: Rysk prices no less than 10 SOL, which "
                                        "needs $880 on SOL-27NOV26-88-P"])

    def test_at_the_lowest_strike_it_is_said_once(self):
        q = self.rysk.quote("SOL", 5, pay_with=USDC, strike=79.0)
        self.assertEqual(q["reasons"], ["collateral too small: Rysk prices no less than 10 SOL, which "
                                        "needs $790 on SOL-27NOV26-79-P"])

    def test_screen_does_not_probe(self):
        with self.assertRaises(self.rysk.RyskError) as e:
            self.rysk.quote("SOL", 5, pay_with=USDC, probe=False)
        self.assertIn("would not price $5 of SOL", str(e.exception))
        self.assertTrue(all(s < 0.1 for s in self.asked))

    def test_another_refusal_ends_the_search(self):
        self.refuse = "no maker answered"
        with self.assertRaises(self.rysk.RyskError) as e:
            self.rysk.quote("SOL", 5, pay_with=USDC)
        self.assertIn("would not price", str(e.exception))
        self.assertTrue(all(s < 0.1 for s in self.asked))


if __name__ == "__main__":
    unittest.main()
