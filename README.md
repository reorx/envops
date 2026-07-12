# envops

A single-file CLI to inspect and manipulate `.env` files, designed to be safe by default: values that look like secrets are **masked** in all output unless you explicitly ask otherwise.

Built with Python stdlib only, runs via [uv](https://docs.astral.sh/uv/).

## Install

```sh
git clone <this-repo> && cd envops
ln -s "$PWD/envops" ~/bin/envops   # or anywhere on your PATH
```

Requires `uv` on PATH (the script uses a `#!/usr/bin/env -S uv run` shebang).

## Usage

### show — print key-value pairs (secrets masked)

```sh
envops show ./test.env
```

```
FOO=hello
API_SECRET=sk******ij
DATABASE_URL=po******pp
DEBUG=true
```

Show only certain keys; add `--unsafe` to expose masked values — use with caution and compromise in mind:

```sh
envops show ./test.env -k FOO BAR
envops show ./test.env -k API_SECRET --unsafe
```

### list-keys — list keys only

```sh
envops list-keys ./test.env
```

### copy — copy pairs from source to dest

Specify keys with `-k`, or `--full` to copy every pair. Changes made to the dest file are printed (masked):

```sh
envops copy ./test.env /path/to/dest.env -k FOO BAR
envops copy ./test.env /path/to/dest.env --full
```

```
+ BAR="quoted value"
~ FOO=hello (was old_foo)
updated /path/to/dest.env: 2 change(s)
```

`+` means the key was added, `~` means its value was updated. Keys already equal in dest are left untouched. Unrelated lines, comments, and formatting in dest are preserved; the dest file is created if it doesn't exist.

### set — set a key's value from stdin

```sh
echo value | envops set ./test.env -k FOO
pbpaste | envops set ./test.env -k API_SECRET
```

One trailing newline is stripped from stdin. Existing keys are updated in place; new keys are appended.

### read-value — print a key's raw value

Only use this when the other commands cannot solve the problem, as it exposes the value. `--unsafe` is required; without it the command fails:

```sh
envops read-value ./test.env -K FOO --unsafe
```

## Secret detection

A value is masked when any of these match — except pure-numeric values (timeouts, sizes, retry counts like `AUTH_TOKEN_EXPIRE=604800`), which are never treated as secrets:

- **Key name** contains `SECRET`, `TOKEN`, `PASSWORD`, `API_KEY`, `ACCESS_KEY`, `PRIVATE`, `CREDENTIAL`, `AUTH`, `SALT`, `SIGNING`, `DSN`, ... (case-insensitive) — unless the key's last word marks plain config (`URL`, `URI`, `ENDPOINT`, `HOST`, `PORT`, `DOMAIN`, `PATH`, `NAME`, `TELEMETRY`, ...), so `BETTER_AUTH_URL` is not treated as a secret by its name alone
- **Value prefix** matches known credential formats: `sk-`, `ghp_`, `glpat-`, `xoxb-`, `AKIA...`, JWT (`eyJ...`), etc.
- **Random-looking token run**: the value contains an unbroken alphanumeric run of ≥20 chars that mixes letters and digits with Shannon entropy ≥3.5

The entropy check works on alphanumeric *runs*, so structured values — hostnames (`oss-cn-beijing.aliyuncs.com`), bucket names (`myapp-demo-snapshot`), db names — are cut into short segments by `-` `.` `_` `/` and pass in the clear.

**URL-shaped values** (`<scheme>://...`, any scheme word) are masked *per segment* instead of as a whole, so the recognizable parts stay readable:

- the userinfo password is always masked — weak passwords are still passwords
- random-looking runs in the path/query are masked (webhook tokens, etc.)
- scheme, username, host, and port stay in the clear

```
NEO4J_URL=neo4j://neo4j:12******cc@102.10.101.125:7687
SLACK_WEBHOOK=https://hooks.slack.com/services/T01ABCDEFGH/B02JKLMNOPQ/x9******ty
```

Masked form keeps the first and last 2 characters (`sk******ij`) so you can tell credentials apart without leaking them.

## Env file handling

- Supports `export KEY=value`, single/double quotes, inline `#` comments on unquoted values
- Duplicate keys: last occurrence wins (dotenv semantics)
- On write, values containing spaces or special characters are double-quoted with escaping
- Writes preserve comments, blank lines, and unrelated lines byte-for-byte

## Development

```sh
uv run pytest
```

Tests invoke the CLI as a subprocess and assert on real command behavior.
