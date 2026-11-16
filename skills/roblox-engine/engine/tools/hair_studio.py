"""hair_studio.py - hairs the public endpoint refuses (HTTP 401) via Roblox Studio (logged in), no cookies touched.
1) Run tools/hair_batch.luau in Studio (MCP execute_luau, Edit) with IDS set; save its returned JSON to a file.
2) python tools/hair_studio.py collect <json> [--mark-ms N]
   Studio downloaded each mesh/texture into its content cache (%LOCALAPPDATA%/Roblox/rbx-storage files + rbx-storage.db rows);
   entries are matched to ids by the per-id time window from the Luau JSON -> assets/hair/<id>_<slug>/ mesh.obj, tex.png, meta.json.
Also refreshes placement meta (exact Studio CFrames) for hairs already fetched by hair_fetch.py."""
import json, os, re, sqlite3, shutil, struct, sys, tempfile
from pathlib import Path

E = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hair_fetch import mesh_to_obj, OUT
from env_paths import roblox_logs_dir, roblox_storage_dirs

SIGS = {b'version ': 'mesh', b'\xabKTX 20': 'ktx', b'\x89PNG': 'png'}
BC = {131: 'bc1', 132: 'bc1', 133: 'bc1', 134: 'bc1', 135: 'bc2', 136: 'bc2', 137: 'bc3', 138: 'bc3', 145: 'bc7', 146: 'bc7'}


def _storage_roots():
    roots = [r for r in roblox_storage_dirs() if (r / 'rbx-storage').exists() or (r / 'rbx-storage.db').exists()]
    if not roots:
        raise SystemExit('Roblox Studio cache (rbx-storage / rbx-storage.db) not found - run on the PC with Roblox Studio or set ROBLOX_DIR')
    return roots


def studio_logs():
    logs_dir = roblox_logs_dir()
    logs_ = list(logs_dir.glob('*Studio*')) if logs_dir and logs_dir.exists() else []
    if not logs_:
        raise SystemExit(f'no Roblox Studio logs found (checked {logs_dir or "LOCALAPPDATA/Roblox/logs"}) - open Studio and run the batch first, or set ROBLOX_LOGS_DIR')
    return logs_


def payload(b):
    """RBXH cache record -> (kind, body) by locating the body signature after the header."""
    for sig, kind in SIGS.items():
        i = b.find(sig, 0, 256)
        if i >= 0: return kind, b[i:]
    return None, None


_HEADS = {}


def _heads():
    """First 600 bytes of every cache file (RBXH header with the source URL), read once per run."""
    if not _HEADS:
        for root in _storage_roots():
            for f in (root / 'rbx-storage').glob('*/*'):
                try:
                    with open(f, 'rb') as h: _HEADS[f] = h.read(600)
                except OSError: pass
    return _HEADS


def entries(t0, t1):
    """All cache payloads written in [t0, t1] ms: big ones are files, small ones live inline in the sqlite db."""
    got = []
    urls = set()   # cache HIT: Studio only touches a small header row (URL); the body sits in an older file that starts with the same URL
    tmp = Path(tempfile.mkdtemp())
    try:
        for idx, root in enumerate(_storage_roots()):
            for f in (root / 'rbx-storage').glob('*/*'):
                if t0 <= f.stat().st_mtime * 1000 <= t1:
                    k, body = payload(f.read_bytes())
                    if k: got.append((k, body))
            if not (root / 'rbx-storage.db').exists():
                continue
            for ext in ('', '-wal', '-shm'):   # copy: Studio holds the live db open
                p = root / f'rbx-storage.db{ext}'
                if p.exists(): shutil.copy(p, tmp / f'db_{idx}{ext}')
            c = sqlite3.connect(tmp / f'db_{idx}')
            for content, in c.execute('select content from files where atime between ? and ? and content is not null', (t0, t1)):
                k, body = payload(content)
                if k: got.append((k, body))
                elif content[:4] == b'RBXH':
                    n = int.from_bytes(content[8:12], 'little'); urls.add(content[12:12 + n])
            c.close()
        if urls:
            for f, head in _heads().items():
                if any(u in head for u in urls) and not t0 <= f.stat().st_mtime * 1000 <= t1:
                    k, body = payload(f.read_bytes())
                    if k: got.append((k, body))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return got


def cache_entries(t0, t1):
    """(mtime_ms, kind, body) of every content-cache payload written/read in [t0, t1]."""
    got = []
    tmp = Path(tempfile.mkdtemp())
    try:
        for idx, root in enumerate(_storage_roots()):
            for f in (root / 'rbx-storage').glob('*/*'):
                t = f.stat().st_mtime * 1000
                if t0 <= t <= t1:
                    k, body = payload(f.read_bytes())
                    if k: got.append((t, k, body))
            if not (root / 'rbx-storage.db').exists():
                continue
            for ext in ('', '-wal', '-shm'):
                p = root / f'rbx-storage.db{ext}'
                if p.exists(): shutil.copy(p, tmp / f'db_{idx}{ext}')
            c = sqlite3.connect(tmp / f'db_{idx}')
            for t, content in c.execute('select atime, content from files where atime between ? and ? and content is not null', (t0, t1)):
                k, body = payload(content)
                if k: got.append((t, k, body))
            c.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return got


def ktx2_png(b, path):
    """KTX2 (zstd supercompressed BCn, as Roblox ships textures) -> PNG of mip level 0."""
    import zstandard, texture2ddecoder as td
    from PIL import Image
    vk, _, w, h = struct.unpack('<IIII', b[12:28]); sc = struct.unpack('<I', b[44:48])[0]
    off, ln, uln = struct.unpack('<QQQ', b[80:104])
    data = b[off:off + ln]
    if sc == 2: data = zstandard.ZstdDecompressor().decompress(data, max_output_size=uln or w * h * 4)
    if vk in BC: rgba = getattr(td, 'decode_' + BC[vk])(data, w, h); mode = 'BGRA'
    elif vk in (37, 43): rgba = data; mode = 'RGBA'
    else: raise RuntimeError(f'ktx vkFormat {vk} not handled')
    Image.frombuffer('RGBA', (w, h), rgba, 'raw', mode, 0, 1).save(path)
    return w, h


def log_rows():
    """HAIRJSON lines printed by hair_batch.luau, from the newest Studio log (last row per id wins)."""
    logs_ = studio_logs()
    lg = max(logs_, key=lambda p: p.stat().st_mtime)
    rows = {}
    for ln in lg.read_text(encoding='utf-8', errors='replace').splitlines():
        i = ln.find('HAIRJSON ')
        if i >= 0: r = json.loads(ln[i + 9:]); rows[r['id']] = r
    return list(rows.values())


def collect(js, pad=400):
    rows = log_rows() if js == 'log' else json.loads(Path(js).read_text(encoding='utf-8'))
    done = {d.name.split('_', 1)[0] for d in OUT.glob('*_*') if (d / 'mesh.obj').exists() and (d / 'meta.json').exists() and 'att' in (d / 'meta.json').read_text()}
    if js == 'log': rows = [r for r in rows if r['id'] not in done]
    for r in rows:
        if r.get('err'): print('SKIP', r['id'], r['err'][:80]); continue
        slug = re.sub(r'[^a-z0-9]+', '_', (r.get('name') or r['id']).lower()).strip('_')[:40]
        old = sorted(OUT.glob(f"{r['id']}_*"))
        d = old[0] if old else OUT / f"{r['id']}_{slug}"; d.mkdir(parents=True, exist_ok=True)
        meta = json.loads((d / 'meta.json').read_text()) if (d / 'meta.json').exists() else {}
        meta.update({k: v for k, v in r.items() if k not in ('t0', 't1')}); meta['source'] = meta.get('source', 'studio')
        meshes, texs = [], []
        for k, body in entries(r['t0'] - pad, r['t1'] + pad):
            (meshes if k == 'mesh' else texs).append((k, body))
        if not (d / 'mesh.obj').exists():
            want = (meta['verts'], meta['tris']) if meta.get('verts') else None   # manifest shape: the window also holds OTHER hairs' meshes
            ok = None
            for _, body in sorted(meshes, key=lambda x: -len(x[1])):
                try: vt = mesh_to_obj(body, d / 'mesh.obj')
                except Exception: continue
                if want is None or tuple(vt) == tuple(want): ok = vt; break
            if not ok:
                (d / 'mesh.obj').unlink(missing_ok=True)   # left for scan_cache (whole cache, matched by shape)
                print('NOMESH', r['id'], slug, 'candidates', len(meshes)); (d / 'meta.json').write_text(json.dumps(meta, indent=1)); continue
            meta['verts'], meta['tris'] = ok
        if not (d / 'tex.png').exists() and texs:
            k, body = texs[0]
            if k == 'png': (d / 'tex.png').write_bytes(body)
            else: ktx2_png(body, d / 'tex.png')
        (d / 'meta.json').write_text(json.dumps(meta, indent=1))
        print('HAIR', r['id'], d.name, r.get('kind'), 'verts', meta.get('verts'), 'att', bool(meta.get('att')), 'tex', (d / 'tex.png').exists())



def tex_sig(img):
    """16x16 RGB thumbnail (base64, 1 KB) of a hair texture: ships in the manifest to recognise the texture in Studio's cache."""
    import base64, numpy as np
    from PIL import Image
    im = img if hasattr(img, 'convert') else Image.open(img)
    return base64.b64encode(np.asarray(im.convert('RGB').resize((16, 16), Image.BILINEAR), dtype=np.uint8).tobytes()).decode()


def _all_payloads():
    """Every payload in Studio's content cache (files + inline sqlite rows), whatever its age."""
    got = []
    tmp = Path(tempfile.mkdtemp())
    try:
        for idx, root in enumerate(_storage_roots()):
            for f in (root / 'rbx-storage').glob('*/*'):
                try: k, b = payload(f.read_bytes())
                except OSError: continue
                if k: got.append((k, b))
            if not (root / 'rbx-storage.db').exists():
                continue
            for ext in ('', '-wal', '-shm'):
                p = root / f'rbx-storage.db{ext}'
                if p.exists(): shutil.copy(p, tmp / f'db_{idx}{ext}')
            c = sqlite3.connect(tmp / f'db_{idx}')
            try:
                for content, in c.execute('select content from files where content is not null'):
                    k, b = payload(content)
                    if k: got.append((k, b))
            finally:
                c.close()
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return got, tmp


def scan_cache(dirs, max_diff=0.03):
    """Hair folders (seeded meta with verts/tris/tex_sig) -> mesh.obj by exact verts/tris, tex.png by nearest tex_sig.
    The time-window collect misses hairs Studio already had cached (a cache hit writes nothing new; 14/49 on 2026-11-13,
    trace/20261114-hair-cache-scan.md); this scans the WHOLE cache, so it also works on a second run."""
    import base64, io, numpy as np
    from PIL import Image
    want_m, want_t = {}, {}
    for d in dirs:
        m = json.loads((d / 'meta.json').read_text(encoding='utf-8'))
        if not (d / 'mesh.obj').exists() and m.get('verts'): want_m.setdefault((m['verts'], m['tris']), []).append(d)
        if m.get('tex_sig'):   # missing, or a wrong texture from the time-window collect -> find the right one
            s = np.frombuffer(base64.b64decode(m['tex_sig']), dtype=np.uint8).astype(np.float32).reshape(16, 16, 3) / 255
            size = tuple(m['tex_size']) if m.get('tex_size') else None
            if not (d / 'tex.png').exists(): want_t[d] = (s, size)
            else:
                im = Image.open(d / 'tex.png')
                if (size and im.size != size) or np.abs(np.asarray(im.convert('RGB').resize((16, 16), Image.BILINEAR), dtype=np.float32) / 255 - s).mean() > max_diff:
                    want_t[d] = (s, size)
    if not want_m and not want_t: return 0, 0
    got, tmp = _all_payloads(); nm = nt = 0
    try:
        for k, body in got:
            if k != 'mesh' or not want_m: continue
            o = tmp / 'm.obj'
            try: vt = mesh_to_obj(body, o)
            except Exception: continue
            for d in want_m.pop(tuple(vt), []): shutil.copy(o, d / 'mesh.obj'); nm += 1
        if want_t:
            cand = []
            for i, (k, body) in enumerate(got):
                if k not in ('ktx', 'png'): continue
                try:
                    if k == 'png': im = Image.open(io.BytesIO(body))
                    else: ktx2_png(body, tmp / 't.png'); im = Image.open(tmp / 't.png')
                    im.load(); cand.append((np.asarray(im.convert('RGB').resize((16, 16), Image.BILINEAR), dtype=np.float32) / 255, k, body, im.size))
                except Exception: continue
            for d, (s, size) in want_t.items():
                if not cand: break
                diff = np.array([np.abs(c[0] - s).mean() for c in cand])
                ok = [i for i in range(len(cand)) if diff[i] <= max_diff]
                if not ok: print('NOTEX', d.name, f'best {diff.min():.3f}'); continue
                # the cache holds low-res copies of the same picture: exact original size first, else the largest close match
                same = [i for i in ok if size and cand[i][3] == size]
                i = min(same, key=lambda i: diff[i]) if same else max(ok, key=lambda i: (cand[i][3][0] * cand[i][3][1], -diff[i]))
                if size and cand[i][3] != size: print('TEX size', d.name, cand[i][3], 'wanted', size)
                _, k, body, _ = cand[i]
                if k == 'png': (d / 'tex.png').write_bytes(body)
                else: ktx2_png(body, d / 'tex.png')
                nt += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for (v, tr), ds in want_m.items():
        for d in ds: print('NOMESH (cache scan)', d.name, 'verts', v, 'tris', tr)
    print(f'cache scan: {nm} meshes, {nt} textures')
    return nm, nt

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'collect': collect(a[1])
