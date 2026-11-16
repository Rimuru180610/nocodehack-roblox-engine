"""check_update.py - is a newer NoCodeHack engine on GitHub? Reads one public file (the version number); sends nothing.
  python tools/check_update.py      -> "UPDATE <new> (you have <old>)" or "OK <version>"; offline/any error -> "OK (no check)"."""
import os, urllib.request
from pathlib import Path

URL = os.environ.get('ENGINE_UPDATE_URL', 'https://raw.githubusercontent.com/nocodehack/nocodehack-roblox-engine/main/skills/roblox-engine/engine/VERSION')


def ver(s): return tuple(int(x) for x in s.strip().split('.'))


if __name__ == '__main__':
    mine = (Path(__file__).resolve().parents[1] / 'VERSION')
    mine = mine.read_text().strip() if mine.exists() else '0.0.0'
    try: new = urllib.request.urlopen(URL, timeout=5).read().decode().strip(); ok = ver(new) > ver(mine)
    except Exception: print('OK (no check)'); raise SystemExit
    print(f'UPDATE {new} (you have {mine})' if ok else f'OK {mine}')
