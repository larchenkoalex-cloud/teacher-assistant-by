from pathlib import Path
import sys

paths = [Path('.streamlit/secrets.toml'), Path.home() / '.streamlit' / 'secrets.toml']
for p in paths:
    try:
        if not p.exists():
            print(f'NOTFOUND {p}')
            continue
        b = p.read_bytes()
        has_bom = b.startswith(b'\xef\xbb\xbf')
        # decode with utf-8-sig to drop BOM, then write back without BOM
        s = b.decode('utf-8-sig')
        p.write_text(s, encoding='utf-8')
        print(f'FIXED {p} bom_removed={has_bom} len={len(s)}')
    except Exception as e:
        print(f'ERROR {p} {e}')
        sys.exit(1)
print('DONE')
