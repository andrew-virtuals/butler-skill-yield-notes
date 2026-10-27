"""`references/listing.md`'s script against the quote helpers it stands in for."""
import ast
import pathlib
import re
import unittest

REFS = pathlib.Path(__file__).resolve().parent.parent / "references"


def helper_script():
    return re.search(r"cat > /tmp/derive_helper.py <<'PYEOF'\n(.*?)\nPYEOF\n", (REFS / "helper.md").read_text(), re.S).group(1)


def listing_script():
    return re.search(r"<<'PYEOF'\n(.*?)\nPYEOF\n", (REFS / "listing.md").read_text(), re.S).group(1)


def known(src):
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "KNOWN":
            return ast.literal_eval(node.value)
    raise AssertionError("no KNOWN table")


class ListingTest(unittest.TestCase):
    def test_known_matches_the_helper(self):
        # Neither venue names its tickers: the two lists must say the same thing.
        self.assertEqual(known(listing_script()), known(helper_script()))

    def test_script_compiles(self):
        compile(listing_script(), "options_list.py", "exec")

    def test_one_command_writes_and_runs_it(self):
        block = re.search(r"```sh\n(.*?)\n```", (REFS / "listing.md").read_text(), re.S).group(1)
        self.assertTrue(block.startswith("cat > /tmp/options_list.py <<'PYEOF'\n"))
        self.assertTrue(block.endswith("PYEOF\npython3 /tmp/options_list.py --venue paradex"))


if __name__ == "__main__":
    unittest.main()
