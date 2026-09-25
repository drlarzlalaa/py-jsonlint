# jsonlint

Lint, format, minify and query JSON. Standard library only, Python 3.9+. Everything runs locally.

```
$ python -m jsonlint lint messy.json warnings.json good.json
messy.json:3:20: error [syntax] Illegal trailing comma before end of array
warnings.json:2:3: warn [duplicate-key] the key 'name' appears more than once in one object; parsers keep the last value
warnings.json:3:9: warn [big-integer] 12345678901234567890 is beyond 2^53; JavaScript and many other parsers store it as a float and lose digits
warnings.json:5:12: warn [constant] NaN is not valid JSON (many parsers reject it)
good.json: valid

$ python -m jsonlint get "items[1].name" good.json --raw
two
```

(The exact wording of a syntax error comes from Python's parser, and newer Python versions say more; jsonlint adds a plain-language hint where the built-in message is terse, such as "comments are not allowed in JSON" or "JSON strings and keys use double quotes".)

## Commands

| Command | What it does |
| --- | --- |
| `lint FILE [FILE ...]` | Errors with **line and column** and a hint, and warnings for things valid JSON parsers disagree about. Exit 1 on errors (or warnings with `--strict`). |
| `fmt [FILE] [--indent 2] [--sort-keys] [--check]` | Pretty-print (keeps key order and non-ASCII characters). `--check` prints nothing and exits 1 if the file would change: for CI. |
| `min [FILE] [--sort-keys]` | Remove all optional whitespace. |
| `get PATH [FILE] [--raw]` | Print the value at a path like `items[0].name` (negative indexes work: `items[-1]`). `--raw` prints strings without quotes. |

With no file, or `-`, input is read from standard input.

## What lint reports

| Rule | Level | Meaning |
| --- | --- | --- |
| `syntax` | error | not valid JSON, with the position and a hint: trailing comma, comments, single quotes, unquoted keys, missing comma or colon, extra text after the value, raw newline in a string, unterminated string, bad escape, `undefined`/`None`/`NaN` literals |
| `duplicate-key` | warn | the same key twice in one object (Python and most parsers keep the last one silently); points at the repeat |
| `big-integer` | warn | a whole number beyond 2⁵³, which JavaScript and many other parsers turn into a float and lose digits (put such ids in strings) |
| `constant` | warn | `NaN`, `Infinity` or `-Infinity`, which Python accepts but the JSON standard does not |
| `bom` | info | a byte-order mark at the start |

## What it does not do

- It checks syntax and the pitfalls above, not structure: there is no schema validation (see [py-jsonldcheck](https://github.com/drlarzlalaa/py-jsonldcheck) for schema.org JSON-LD).
- `get` paths are simple: dots, `[n]` indexes, no wildcards, filters or keys that contain a dot.
- The line and column of a duplicate key are found by searching the text, so if the same key appears in several nested objects it points at the second textual occurrence, which may be in a different object.

## Tests

```
python -m unittest discover -s tests -v
```

MIT licence.
