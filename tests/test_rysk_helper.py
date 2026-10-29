"""`references/rysk-helper.md`'s script: a named strike and day, against a fixed inventory."""
import pathlib
import re
import time
import types
import unittest

REFS = pathlib.Path(__file__).resolve().parent.parent / "references"
DAY = 86400


def helper():
    src = re.search(r"```python\n(.*?)\n```", (REFS / "rysk-helper.md").read_text(), re.S).group(1)
    mod = types.ModuleType("rysk")
    exec(compile(src, "rysk.py", "exec"), mod.__dict__)
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


if __name__ == "__main__":
    unittest.main()
