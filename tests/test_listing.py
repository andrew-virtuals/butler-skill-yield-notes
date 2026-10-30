"""`scripts/options_list.py` against the quote helper it stands in for."""
import ast
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def known(name):
    for node in ast.parse((SCRIPTS / name).read_text()).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "KNOWN":
            return ast.literal_eval(node.value)
    raise AssertionError("no KNOWN table")


class ListingTest(unittest.TestCase):
    def test_known_matches_the_helper(self):
        # Neither venue names its tickers: the two lists must say the same thing.
        self.assertEqual(known("options_list.py"), known("quote.py"))

    def test_scripts_compile(self):
        for path in SCRIPTS.glob("*.py"):
            compile(path.read_text(), str(path), "exec")


class InstalledTest(unittest.TestCase):
    """The skill runs its scripts where they are installed, and never writes one."""

    def text(self):
        return {p.relative_to(ROOT).as_posix(): p.read_text()
                for p in [ROOT / "SKILL.md", *sorted((ROOT / "references").glob("*.md"))]}

    def test_every_script_is_named_and_every_name_ships(self):
        named = set()
        for body in self.text().values():
            named |= set(re.findall(r"scripts/([a-z_]+\.py)", body))
        self.assertEqual(named, {p.name for p in SCRIPTS.glob("*.py")})

    def test_nothing_is_written_to_tmp(self):
        for rel, body in self.text().items():
            self.assertNotIn("/tmp/", body, rel)
            self.assertNotIn("PYEOF", body, rel)


if __name__ == "__main__":
    unittest.main()
