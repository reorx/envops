---
name: envops
description: Safely view, modify, and copy .env files (local or remote over SSH) with secrets masked by default. Use this skill for ANY operation involving .env files or environment-variable files — reading, listing, diffing, copying, setting values, checking a key, syncing env between machines — even if the user just says "look at the .env" or "copy the env to the server". Never read a .env file with cat, Read, grep, or any other tool; always go through envops.
---

# envops — safe .env operations

`envops` masks secret-looking values in all output, so you can inspect env files without leaking credentials into the conversation, logs, or context.

## Install (if `envops` is not on PATH)

```sh
uv tool install envops    # preferred (published on PyPI); or: pipx/pip install envops

# no uv/pip: it's a stdlib-only single file (python3 shebang, needs 3.10+)
curl -fsSL https://raw.githubusercontent.com/reorx/envops/master/envops.py -o ~/.local/bin/envops && chmod +x ~/.local/bin/envops
```

## Hard rules

1. **Never read a .env file directly** — no `cat`, `head`, `grep`, `sed`, and no Read tool. Every leaked value stays in the transcript forever. Use `envops show` (masked) instead.
2. **Never write a .env file directly** — no `echo >>`, no Edit/Write tool. Use `envops set` or `envops copy`; they preserve comments, formatting, and unrelated lines.
3. **`--unsafe` is a last resort.** Before using it, think twice: can `show` (masked), `list-keys`, or `copy` solve the task without exposing the value? Only use `--unsafe` when the raw value is genuinely required (e.g. the user explicitly asks for it, or a value must be passed to another program) and no other way exists. Prefer piping (`envops read-value ... --unsafe | some-command`) over printing to the terminal.
4. **Pass secrets in via stdin**, never as command-line arguments: `pbpaste | envops set ...`, not `echo 'secret' | ...` typed literally.

## Commands

```sh
# view (secrets masked, safe by default)
envops show ./app.env                        # all pairs, masked
envops show ./app.env -k FOO BAR             # only these keys
envops list-keys ./app.env                   # key names only

# copy between files (prints masked diff: + added, ~ updated)
envops copy ./src.env ./dest.env -k FOO BAR  # selected keys
envops copy ./src.env ./dest.env --full      # everything

# write a value (stdin only; updates in place or appends)
pbpaste | envops set ./app.env -k API_SECRET
printf 'true' | envops set ./app.env -k DEBUG

# remote files over SSH — any file arg can be [user@]host:/path
envops show deploy@web1:/app/.env
envops copy ./local.env deploy@web1:/app/.env --full
envops copy deploy@web1:/app/.env ./local.env -k DATABASE_URL

# --unsafe: LAST RESORT, only when masked output cannot solve the task
envops show ./app.env -k FOO --unsafe        # expose specific keys
envops read-value ./app.env -K FOO --unsafe  # raw value (fails without --unsafe)
```

## Notes

- Duplicate keys: last occurrence wins (dotenv semantics). Writes quote values containing spaces/special chars.
- Remote writes are atomic and keep file permissions; remote content never touches the local disk in plaintext.
- A masked value like `sk******ij` keeps first/last 2 chars — usually enough to verify which credential it is without exposing it.
