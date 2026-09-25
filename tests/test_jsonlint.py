import contextlib
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import jsonlint as jl
from jsonlint.__main__ import main

WARN = os.path.join(HERE, "data", "warnings.json")
MESSY = os.path.join(HERE, "data", "messy.json")
GOOD = os.path.join(HERE, "data", "good.json")


def errors(text):
    return [f for f in jl.lint(text)[0] if f.level == "error"]


def rules(text):
    return [(f.level, f.rule) for f in jl.lint(text)[0]]


class Syntax(unittest.TestCase):
    def test_valid(self):
        for text in ('{}', '[]', '"x"', '12', 'null', 'true', '{"a": [1, 2, {"b": null}]}', ' \n[1]\n '):
            self.assertEqual(jl.lint(text)[0], [], text)

    def test_position_is_line_and_column(self):
        f = errors('{\n  "a": 1\n  "b": 2\n}')[0]
        self.assertEqual((f.line, f.col), (3, 3))
        self.assertIn("comma may be missing", f.message)

    def test_hints(self):
        cases = {
            '{"a": 1,}': "trailing comma",
            '[1, 2,]': "trailing comma",
            '{"a": 1, // note\n"b": 2}': "comments are not allowed",
            '{"a": /* x */ 1}': "comments are not allowed",
            "{'a': 1}": "double quotes",
            "{a: 1}": "keys must be quoted",
            '{"a" 1}': "colon is missing",
            '{"a": 1} {"b": 2}': "more text after the end",
            '{"a": "line\nbreak"}': "raw newline",
            '{"a": "unterminated': "closing double quote",
            '{"a": "bad \\q"}': "invalid backslash escape",
            '{"a": undefined}': "not a JSON literal",
            '{"a": None}': "not a JSON literal",
        }
        for text, expected in cases.items():
            msg = errors(text)[0].message.lower() if errors(text) else ""
            self.assertIn(expected.lower(), msg, text)

    def test_empty_input(self):
        self.assertEqual(len(errors("")), 1)
        self.assertEqual(len(errors("   \n")), 1)


class Warnings(unittest.TestCase):
    def test_duplicate_keys_with_position(self):
        findings, _ = jl.lint('{\n  "a": 1,\n  "b": 2,\n  "a": 3\n}')
        self.assertEqual([(f.level, f.rule, f.line) for f in findings], [("warn", "duplicate-key", 4)])
        self.assertEqual(rules('{"a": {"x": 1}, "b": {"x": 2}}'), [])              # the same key in different objects is fine
        self.assertEqual(rules('[{"a": 1}, {"a": 2}]'), [])

    def test_big_integers(self):
        self.assertEqual(rules('{"id": 12345678901234567890}'), [("warn", "big-integer")])
        self.assertEqual(rules('{"id": 9007199254740992}'), [])                     # exactly 2^53 is safe
        self.assertEqual(rules('{"id": 9007199254740993}'), [("warn", "big-integer")])
        self.assertEqual(rules('{"id": "12345678901234567890"}'), [])               # a string is fine
        self.assertEqual(rules('{"id": 1.2345678901234567890}'), [])                # a decimal is a float anyway
        self.assertEqual(rules('[-12345678901234567890]'), [("warn", "big-integer")])

    def test_nan_and_infinity(self):
        self.assertEqual(rules('[NaN]'), [("warn", "constant")])
        self.assertEqual(rules('[Infinity, -Infinity]'), [("warn", "constant"), ("warn", "constant")])
        f = jl.lint('{\n  "x": NaN\n}')[0][0]
        self.assertEqual((f.line, f.col), (2, 8))

    def test_bom(self):
        self.assertEqual(rules('﻿{"a": 1}'), [("info", "bom")])


class Format(unittest.TestCase):
    def test_dump_and_minify(self):
        v = {"b": [1, 2], "a": "é"}
        self.assertEqual(jl.dump(v), '{\n  "b": [\n    1,\n    2\n  ],\n  "a": "é"\n}\n')
        self.assertEqual(jl.dump(v, 4, True), '{\n    "a": "é",\n    "b": [\n        1,\n        2\n    ]\n}\n')
        self.assertEqual(jl.minify(v), '{"b":[1,2],"a":"é"}\n')
        self.assertEqual(jl.minify(v, True), '{"a":"é","b":[1,2]}\n')

    def test_key_order_is_kept(self):
        self.assertEqual(list(jl.lint('{"z": 1, "a": 2}')[1]), ["z", "a"])


class Query(unittest.TestCase):
    DATA = {"items": [{"name": "one", "n": 1}, {"name": "two", "n": 2}], "ok": True, "a.b": 1}

    def test_paths(self):
        g = lambda p: jl.get(self.DATA, p)
        self.assertEqual(g("ok"), True)
        self.assertEqual(g("items[1].name"), "two")
        self.assertEqual(g("items[-1].n"), 2)
        self.assertEqual(g("items"), self.DATA["items"])
        self.assertEqual(g("."), self.DATA)
        self.assertEqual(g(""), self.DATA)

    def test_missing_steps(self):
        for path in ("nope", "items[5]", "ok[0]", "items.name", "items[0].zzz", "ok.x"):
            with self.assertRaises(KeyError):
                jl.get(self.DATA, path)


class Cli(unittest.TestCase):
    def run_cli(self, *argv, stdin=None):
        out, err = io.StringIO(), io.StringIO()
        old = sys.stdin
        try:
            if stdin is not None:
                sys.stdin = io.StringIO(stdin)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(list(argv))
        finally:
            sys.stdin = old
        return code, out.getvalue(), err.getvalue()

    def test_lint_output_and_exit_codes(self):
        code, out, _ = self.run_cli("lint", GOOD)
        self.assertEqual((code, out), (0, "%s: valid\n" % GOOD))
        code, out, _ = self.run_cli("lint", WARN)
        self.assertEqual(code, 0)
        self.assertIn("%s:4:3: warn [duplicate-key]" % WARN, out)
        self.assertIn("%s:3:9: warn [big-integer]" % WARN, out)
        self.assertEqual(self.run_cli("lint", WARN, "--strict")[0], 1)
        code, out, _ = self.run_cli("lint", MESSY)
        self.assertEqual(code, 1)
        self.assertIn("%s:3:20: error [syntax]" % MESSY, out)
        self.assertIn("trailing comma", out)

    def test_fmt_min_get(self):
        self.assertEqual(self.run_cli("fmt", stdin='{"a":[1,2]}')[1], '{\n  "a": [\n    1,\n    2\n  ]\n}\n')
        self.assertEqual(self.run_cli("min", stdin='{ "a" : [ 1 , 2 ] }')[1], '{"a":[1,2]}\n')
        self.assertEqual(self.run_cli("get", "items[1].name", GOOD, "--raw")[1], "two\n")
        self.assertEqual(self.run_cli("get", "items[1].name", GOOD)[1], '"two"\n')
        self.assertEqual(self.run_cli("get", "nope", GOOD)[0], 1)
        code, _, err = self.run_cli("fmt", stdin="{bad")
        self.assertEqual(code, 1)
        self.assertIn("<stdin>:1:2: error", err)

    def test_fmt_check(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.json")
            with open(p, "w") as fh:
                fh.write('{\n  "a": 1\n}\n')
            self.assertEqual(self.run_cli("fmt", p, "--check")[0], 0)
            with open(p, "w") as fh:
                fh.write('{"a":1}')
            self.assertEqual(self.run_cli("fmt", p, "--check")[0], 1)

    def test_missing_file(self):
        code, _, err = self.run_cli("lint", "/no/such.json")
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)


if __name__ == "__main__":
    unittest.main()
