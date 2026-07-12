"""Check DB_URL structure without printing the value."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import envops as mod

value = mod.parse_env_file(Path(sys.argv[1]))[sys.argv[2]]
rest = value.split('://', 1)[1]
authority = rest.split('/', 1)[0]
userinfo = authority.rsplit('@', 1)[0] if '@' in authority else ''
path = rest.split('/', 1)[1] if '/' in rest else ''
print(f'scheme={value.split("://",1)[0]}')
print(f'userinfo: present={bool(userinfo)} has_colon_password={":" in userinfo} len={len(userinfo)}')
print(f'path: len={len(path)} has_digit={any(c.isdigit() for c in path)} charset={"".join(sorted(set(c if c.isalnum() else c for c in path if not c.isalnum())))!r}')
