import argparse
import json
import sys

from . import dump, get, lint, minify


def read(path):
    if path in (None, "-"):
        return sys.stdin.read()
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jsonlint", description="Lint, format, minify and query JSON.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lint", help="check a file: errors with line and column, duplicate keys, huge integers")
    p.add_argument("files", nargs="+")
    p.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    p = sub.add_parser("fmt", help="pretty-print (exit 1 if invalid; with --check, if not already formatted)")
    p.add_argument("file", nargs="?")
    p.add_argument("--indent", type=int, default=2)
    p.add_argument("--sort-keys", action="store_true")
    p.add_argument("--check", action="store_true", help="print nothing; exit 1 if the file would change")
    p = sub.add_parser("min", help="remove all optional whitespace")
    p.add_argument("file", nargs="?")
    p.add_argument("--sort-keys", action="store_true")
    p = sub.add_parser("get", help="print the value at a path such as items[0].name")
    p.add_argument("path")
    p.add_argument("file", nargs="?")
    p.add_argument("--raw", action="store_true", help="print strings without quotes")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "lint":
            bad = warned = 0
            for f in args.files:
                text = read(f)
                findings, _ = lint(text)
                for x in findings:
                    print("%s:%d:%d: %s [%s] %s" % (f, x.line, x.col, x.level, x.rule, x.message))
                bad += any(x.level == "error" for x in findings)
                warned += any(x.level == "warn" for x in findings)
                if not findings:
                    print("%s: valid" % f)
            return 1 if bad or (args.strict and warned) else 0
        text = read(args.file)
        findings, value = lint(text)
        errors = [x for x in findings if x.level == "error"]
        if errors:
            print("%s:%d:%d: error %s" % (args.file or "<stdin>", errors[0].line, errors[0].col, errors[0].message), file=sys.stderr)
            return 1
        if args.cmd == "fmt":
            out = dump(value, args.indent, args.sort_keys)
            if args.check:
                return 0 if out == text.lstrip("﻿") else 1
            sys.stdout.write(out)
        elif args.cmd == "min":
            sys.stdout.write(minify(value, args.sort_keys))
        else:
            try:
                found = get(value, args.path)
            except KeyError as exc:
                print("jsonlint: %s" % exc.args[0], file=sys.stderr)
                return 1
            print(found if args.raw and isinstance(found, str) else json.dumps(found, indent=2, ensure_ascii=False))
        return 0
    except OSError as exc:
        print("jsonlint: cannot read %s: %s" % (exc.filename, exc.strerror), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
