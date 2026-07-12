"""Diagnose which detection rule masks each key in a .env file (values not printed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import envops as mod

pairs = mod.parse_env_file(Path(sys.argv[1]))
for key, value in pairs.items():
    reasons = []
    url = mod.URL_SPLIT_RE.match(value)
    if url:
        # URL-shaped values are masked per segment by mask_url, never as a whole
        userinfo = url.group('userinfo')
        if userinfo and ':' in userinfo:
            reasons.append('url-password')
        runs = [r for r in mod.ALNUM_RUN_RE.findall(url.group('rest')) if mod.run_looks_random(r)]
        if runs:
            scores = ' '.join(f'{mod.shannon_entropy(r):.2f}/len{len(r)}' for r in runs)
            reasons.append(f'url-run-entropy {scores}')
    elif mod.looks_like_secret(key, value):
        if mod.SECRET_VALUE_RE.match(value):
            reasons.append('value-prefix')
        if mod.SECRET_KEY_RE.search(key) and not mod.NONSECRET_KEY_RE.search(key):
            reasons.append('key-name')
        runs = [r for r in mod.ALNUM_RUN_RE.findall(value) if mod.run_looks_random(r)]
        if runs:
            scores = ' '.join(f'{mod.shannon_entropy(r):.2f}/len{len(r)}' for r in runs)
            reasons.append(f'run-entropy {scores}')
    if reasons:
        print(f'{key}: {", ".join(reasons)}')
