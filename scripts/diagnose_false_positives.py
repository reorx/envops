"""Diagnose which detection rule masks each key in a .env file (values not printed)."""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_loader('envops_mod', loader=None)
mod = importlib.util.module_from_spec(spec)
src = Path(__file__).resolve().parent.parent / 'envops'
code = src.read_text().split("if __name__ == '__main__':")[0]
exec(compile(code, str(src), 'exec'), mod.__dict__)

pairs = mod.parse_env_file(Path(sys.argv[1]))
for key, value in pairs.items():
    if not mod.looks_like_secret(key, value):
        continue
    reasons = []
    if mod.SECRET_VALUE_RE.match(value):
        reasons.append('value-prefix')
    if mod.URL_WITH_PASSWORD_RE.match(value):
        reasons.append('url-password')
    if mod.SECRET_KEY_RE.search(key) and not mod.NONSECRET_KEY_RE.search(key):
        reasons.append('key-name')
    if mod.URL_RE.match(value):
        rest = value.split('://', 1)[1]
        has_userinfo = '@' in rest.split('/', 1)[0]
        path = rest.split('/', 1)[1] if '/' in rest else ''
        if mod.entropy_looks_random(path):
            reasons.append(f'url-path-entropy={mod.shannon_entropy(path):.2f} plen={len(path)} userinfo={has_userinfo}')
    elif mod.entropy_looks_random(value):
        reasons.append(f'entropy={mod.shannon_entropy(value):.2f} len={len(value)}')
    print(f'{key}: {", ".join(reasons) or "?"}')
