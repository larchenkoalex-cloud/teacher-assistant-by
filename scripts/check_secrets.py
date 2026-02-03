import tomllib
from pathlib import Path
import os
p = Path('.streamlit/secrets.toml')
if not p.exists():
    print('file_missing')
    raise SystemExit(0)
# read with utf-8-sig to strip BOM if present
s = p.read_text(encoding='utf-8-sig')
try:
    d = tomllib.loads(s)
except Exception as e:
    print('toml_error', e)
    raise SystemExit(0)
v = d.get('OPENROUTER_API_KEY')
print('present' if v else 'missing', len(v) if v else 0)
print('env_present', bool(os.getenv('OPENROUTER_API_KEY')))
