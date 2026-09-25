"""Lint, format, minify and query JSON. Standard library only."""
import json
import re

SAFE_INT = 2 ** 53


class Finding:
    def __init__(self, level, line, col, rule, message):
        self.level, self.line, self.col, self.rule, self.message = level, line, col, rule, message

    def __repr__(self):
        return "%s %d:%d [%s] %s" % (self.level, self.line, self.col, self.rule, self.message)


def line_col(text, pos):
    line = text.count("\n", 0, pos) + 1
    col = pos - (text.rfind("\n", 0, pos) + 1) + 1
    return line, col


def hint(text, err):
    """A plain-language suggestion for a json.JSONDecodeError."""
    pos, msg = err.pos, err.msg
    before = text[:pos].rstrip()
    here = text[pos:pos + 2]
    if here in ("//", "/*"):
        return "comments are not allowed in JSON"
    if msg.startswith("Expecting property name") and before.endswith(","):
        return "a trailing comma before this point: JSON does not allow a comma after the last item"
    if msg.startswith("Expecting value") and before.endswith(","):
        return "a trailing comma before this point (or a missing value)"
    if here[:1] == "'" or (msg.startswith("Expecting property name") and here[:1] == "'"):
        return "JSON strings and keys use double quotes, not single quotes"
    if msg.startswith("Expecting property name") and re.match(r"[A-Za-z_]", here[:1] or " "):
        return "keys must be quoted strings"
    if msg.startswith("Expecting ',' delimiter"):
        return "a comma may be missing between items, or a bracket left open"
    if msg.startswith("Expecting ':' delimiter"):
        return "a colon is missing after this key"
    if msg.startswith("Extra data"):
        return "there is more text after the end of the JSON value (two values, or a stray character)"
    if msg.startswith("Invalid control character"):
        return "a raw newline or tab inside a string: write it as \\n or \\t"
    if msg.startswith("Unterminated string"):
        return "a string is missing its closing double quote"
    if msg.startswith("Invalid \\escape") or msg.startswith("Invalid \\u"):
        return "an invalid backslash escape inside a string"
    if msg.startswith("Expecting value") and re.match(r"(undefined|NaN|Infinity|-Infinity|None|True|False)\b", text[pos:]):
        return "that is not a JSON literal (JSON uses true, false and null, and has no NaN or undefined)"
    return None


def lint(text):
    """Returns (findings, parsed value or None). An unparseable document gives one 'error' finding."""
    findings, dupes = [], []
    if text.startswith("﻿"):
        findings.append(Finding("info", 1, 1, "bom", "the file starts with a byte-order mark; some parsers reject it"))
        text = text[1:]

    def pairs(items):
        seen = set()
        for k, _ in items:
            if k in seen:
                dupes.append(k)
            seen.add(k)
        return dict(items)

    def constant(name):
        findings.append(Finding("warn", 0, 0, "constant", "%s is not valid JSON (many parsers reject it)" % name))
        return float(name.replace("Infinity", "inf").replace("NaN", "nan"))

    try:
        value = json.JSONDecoder(object_pairs_hook=pairs, parse_constant=constant).decode(text)
    except json.JSONDecodeError as err:
        line, col = line_col(text, err.pos)
        h = hint(text, err)
        return [Finding("error", line, col, "syntax", err.msg + (" — " + h if h else ""))], None
    except RecursionError:
        return [Finding("error", 1, 1, "depth", "nesting is too deep to parse")], None
    for k in sorted(set(dupes)):
        found = list(re.finditer(r'"%s"\s*:' % re.escape(json.dumps(k)[1:-1]), text))
        m = found[1] if len(found) > 1 else (found[0] if found else None)       # point at the repeat, not the first use
        line, col = line_col(text, m.start()) if m else (1, 1)
        findings.append(Finding("warn", line, col, "duplicate-key", "the key %r appears more than once in one object; parsers keep the last value" % k))
    for m in re.finditer(r'(?<![\w."])-?\d{16,}(?![\w."])', re.sub(r'"(?:[^"\\]|\\.)*"', lambda s: " " * len(s.group(0)), text)):
        if abs(int(m.group(0))) > SAFE_INT:
            line, col = line_col(text, m.start())
            findings.append(Finding("warn", line, col, "big-integer", "%s is beyond 2^53; JavaScript and many other parsers store it as a float and lose digits" % m.group(0)[:24]))
    for f in list(findings):
        if f.rule == "constant":
            m = re.search(r"\b(NaN|-?Infinity)\b", text)
            if m:
                f.line, f.col = line_col(text, m.start())
    return sorted(findings, key=lambda f: (f.line, f.col)), value


def dump(value, indent=2, sort_keys=False):
    return json.dumps(value, indent=indent, sort_keys=sort_keys, ensure_ascii=False) + "\n"


def minify(value, sort_keys=False):
    return json.dumps(value, separators=(",", ":"), sort_keys=sort_keys, ensure_ascii=False) + "\n"


TOKEN = re.compile(r"\.?([^.\[\]]+)|\[(-?\d+)\]")


def get(value, path):
    """Follow a path like a.b[0].c; raises KeyError with a message if a step is missing."""
    pos, cur = 0, value
    path = path.strip()
    if path in ("", "."):
        return value
    while pos < len(path):
        m = TOKEN.match(path, pos)
        if not m or m.end() == pos:
            raise KeyError("cannot read the path at %r" % path[pos:])
        pos = m.end()
        if m.group(2) is not None:
            if not isinstance(cur, list):
                raise KeyError("[%s] used on something that is not a list" % m.group(2))
            i = int(m.group(2))
            if not -len(cur) <= i < len(cur):
                raise KeyError("index %d is out of range (the list has %d items)" % (i, len(cur)))
            cur = cur[i]
        else:
            key = m.group(1)
            if not isinstance(cur, dict) or key not in cur:
                raise KeyError("no key %r here" % key)
            cur = cur[key]
    return cur
