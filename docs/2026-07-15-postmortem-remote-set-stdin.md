# Postmortem: remote `set` intermittently writes empty values (stdin drained by ssh)

- **Date discovered**: 2026-07-15, during a production deployment (campus_watch / beiwangconnect rollout)
- **Affected**: `envops set <host>:<path> -k KEY` — the remote-file variant only
- **Impact**: piped values were silently replaced with empty strings, non-deterministically
- **Fixed in**: `_ssh()` stdin isolation + `cmd_set()` read-order change, with a deterministic regression test

## Symptom

While provisioning a remote `.env` file, four consecutive `set` calls behaved inconsistently:

```sh
printf '571196'  | envops set host:/app/.env -k BW_TENANT_ID    # wrote ""   ✗
printf '山西...' | envops set host:/app/.env -k BW_USERNAME     # "no changes" (read "", old was "") ✗
printf '山西...' | envops set host:/app/.env -k BW_PASSWORD     # wrote correctly ✓
printf 'https…'  | envops set host:/app/.env -k API_BASE_URL    # wrote ""   ✗
```

Same command shape, same session, different outcomes. No errors, exit code 0 —
the failures announced themselves as `updated KEY=""`.

## Root cause

`cmd_set` read stdin **after** validating the target file:

```python
def cmd_set(args):
    path = resolve_path(args.file)
    require_file(path)          # remote path → _ssh('test -f …')  ← runs first
    value = sys.stdin.read()    # ← by now the pipe may be empty
```

and `_ssh` did not manage the child's stdin:

```python
def _ssh(self, command, **kwargs):
    return subprocess.run(['ssh', self.host, command],
                          capture_output=True, text=True, **kwargs)
```

`capture_output=True` only wires up stdout/stderr. **The ssh child inherits the
parent's stdin — the very pipe holding the caller's value.** ssh's job is to
forward local stdin to the remote command; whatever the remote side doesn't
consume is discarded when the session closes. So the preliminary
`ssh 'test -f …'` could drain `571196` out of the pipe and throw it away before
`cmd_set` ever called `sys.stdin.read()`.

### Why it was intermittent

`test -f` returns in milliseconds. Whether ssh's event loop happens to poll
local stdin before the session closes is a scheduling race:

- ssh reads the pipe first → value forwarded to `test -f` (which ignores it),
  discarded → `cmd_set` reads EOF → writes `""`.
- remote exits first → ssh never touches stdin → value survives → correct write.

A few bytes sitting in a pipe buffer, gambling on milliseconds of ssh's poll
loop. This is why two of four calls succeeded — and why the bug survived until
a production deployment: races that *usually* lose look like reliable code.

### Why `copy` and local `set` were immune

- **local `set`**: no ssh child at all; nothing competes for stdin.
- **remote `copy`**: the source is read locally; the destination write calls
  `_ssh(script, input=content)` — `subprocess.run(input=…)` creates a fresh
  pipe for the child instead of inheriting the parent's stdin.

The workaround during the incident was exactly this: build the file locally
with `set`, then `copy --full` to the remote.

## The fix

Two independent layers, both in `envops.py`:

1. **`_ssh` detaches from the caller's stdin** unless input is explicit
   (`input=` and `stdin=` are mutually exclusive in `subprocess.run`, hence
   the guard):

   ```python
   if 'input' not in kwargs:
       kwargs.setdefault('stdin', subprocess.DEVNULL)
   ```

   This fixes the whole class: `is_file`, `read_text`, and any future
   `RemoteFile` helper can no longer eat the caller's pipe.

2. **`cmd_set` reads stdin first**, before `resolve_path`/`require_file` —
   claim the data that belongs to you before doing anything that might spawn
   a child process.

(`ssh -n` would also detach stdin but was rejected: it must not apply to
`write_text`, which feeds content through stdin. The kwargs guard is exact.)

## Why the test suite missed it — and the testing fix

`tests/test_envops.py` already had `test_set_remote_key_from_stdin`, and it
passed. The fake `ssh` shim ran the command via `exec sh -c "$*"`; commands
like `test -f` simply never read stdin, so the shim — unlike real ssh — never
drained the pipe. **The test double was missing the one behavior that caused
the bug.**

The shim now emulates real ssh faithfully: after running the command it drains
whatever is left on stdin (`cat > /dev/null`), exactly like a real ssh session
discarding unconsumed forwarded input. With that one change the existing test
went deterministically red on the old code — no race, no flakiness — and green
after the fix. As a guard against hangs, the remote-test runner defaults
`stdin=''` (an immediately-closed pipe) rather than `None`, so the drain can
never block on pytest's own stdin/tty.

## Lessons

- **Inherited stdin is part of your subprocess contract.** Any child that
  might read stdin (ssh, git, ffmpeg…) must get `stdin=DEVNULL` unless it is
  deliberately being fed. `capture_output=True` handles only the other two
  streams and quietly leaves this hole. This applies to every subprocess this
  codebase will ever spawn, not just ssh.
- **Read your stdin before forking.** If a command's contract is "value comes
  from stdin", consuming it should be the first thing the command does.
- **A test double must model the failure-relevant behavior of the real
  dependency, not just its happy path.** The fake ssh executed commands
  correctly but didn't reproduce ssh's stdin forwarding — precisely the
  behavior under test. When a bug ships despite existing coverage, fix the
  double first and watch the old test fail on the old code.
- **Intermittent + silent is the worst failure shape.** The write reported
  success (`updated KEY=""`), and masking hid the emptiness from casual
  reading (`****** ` vs `""` differ only subtly). The masked-diff output of
  `copy` is what exposed the truth — value-comparing output paths are worth
  keeping honest.
