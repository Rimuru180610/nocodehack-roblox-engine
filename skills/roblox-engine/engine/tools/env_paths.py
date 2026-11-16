"""env_paths.py - cross-platform path discovery for Blender, Google Cloud SDK, and Roblox Studio."""
import os
import shutil
import sys
from pathlib import Path

DEFAULT_BLENDER = 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'


def find_blender():
    env = os.environ.get('BLENDER', '').strip()
    if env:
        return env
    home = Path.home()
    candidates = []
    if sys.platform == 'win32':
        lad = Path(os.environ.get('LOCALAPPDATA', home / 'AppData' / 'Local'))
        candidates += [
            Path(DEFAULT_BLENDER),
            lad / 'Programs' / 'Blender Foundation' / 'Blender 5.2' / 'blender.exe',
        ]
    elif sys.platform == 'darwin':
        candidates += [
            Path('/Applications/Blender.app/Contents/MacOS/Blender'),
            home / 'Applications' / 'Blender.app' / 'Contents/MacOS/Blender',
        ]
    else:
        candidates += [
            home / '.local' / 'bin' / 'blender',
            Path('/usr/local/bin/blender'),
            Path('/usr/bin/blender'),
            Path('/snap/bin/blender'),
            *sorted(Path('/opt').glob('blender*/blender'), reverse=True),
            *sorted((home / '.local').glob('blender*/blender'), reverse=True),
        ]
    for p in candidates:
        if p.exists():
            return str(p)
    found = shutil.which('blender')
    return found or DEFAULT_BLENDER


def find_gcloud(tool='gcloud'):
    env = os.environ.get(tool.upper(), '').strip()
    if env:
        return env
    found = shutil.which(tool)
    if found:
        return found
    home = Path.home()
    if sys.platform == 'win32':
        lad = Path(os.environ.get('LOCALAPPDATA', home / 'AppData' / 'Local'))
        return str(lad / 'Google' / 'Cloud SDK' / 'google-cloud-sdk' / 'bin' / f'{tool}.cmd')
    for p in (home / 'google-cloud-sdk' / 'bin' / tool, Path('/opt/homebrew/bin') / tool, Path('/usr/local/bin') / tool):
        if p.exists():
            return str(p)
    return tool


def roblox_root():
    env = os.environ.get('ROBLOX_DIR', '').strip()
    if env:
        return Path(env)
    lad = os.environ.get('LOCALAPPDATA', '').strip()
    if lad:
        return Path(lad) / 'Roblox'
    home = Path.home()
    if sys.platform == 'darwin':
        for p in (
            home / 'Library' / 'Roblox',
            home / 'Library' / 'Caches' / 'com.roblox.RobloxStudio',
            home / 'Library' / 'Caches' / 'Roblox',
        ):
            if p.exists():
                return p
        return home / 'Library' / 'Roblox'
    for p in (
        home / '.local' / 'share' / 'Roblox',
        home / '.var' / 'app' / 'org.vinegarhq.Sober' / 'data' / 'sober',
    ):
        if p.exists():
            return p
    return None


def roblox_logs_dir():
    env = os.environ.get('ROBLOX_LOGS_DIR', '').strip()
    if env:
        return Path(env)
    if sys.platform == 'darwin':
        mac_logs = Path.home() / 'Library' / 'Logs' / 'Roblox'
        if mac_logs.exists():
            return mac_logs
    root = roblox_root()
    return (root / 'logs') if root else None


def roblox_storage_dirs():
    """Candidate directories holding rbx-storage/ and rbx-storage.db."""
    env = os.environ.get('ROBLOX_CACHE_DIR', '').strip()
    out = []
    if env:
        out.append(Path(env))
    root = roblox_root()
    if root and root not in out:
        out.append(root)
    if sys.platform == 'darwin':
        home = Path.home()
        for p in (
            home / 'Library' / 'Caches' / 'com.roblox.RobloxStudio',
            home / 'Library' / 'Caches' / 'Roblox',
            home / 'Library' / 'Roblox',
            Path('/private/tmp/roblox'),
        ):
            if p not in out:
                out.append(p)
        tmp = os.environ.get('TMPDIR', '').strip()
        if tmp and Path(tmp) / 'Roblox' not in out:
            out.append(Path(tmp) / 'Roblox')
    existing = [p for p in out if p.exists()]
    return existing or out
