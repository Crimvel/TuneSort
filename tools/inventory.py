#!/usr/bin/env python3
"""Read-only MP3 library inventory. Python 3.8+, stdlib only.

Usage:  python inventory.py "D:\\Musik" [--out inventory.md]
        python inventory.py --selftest
"""
import os, re, sys, struct, collections, tempfile

# ---------- ID3 ----------

TEXT_FRAMES = {  # v2.3/2.4 -> field, plus v2.2 3-char aliases
    "TIT2": "title", "TPE1": "artist", "TALB": "album", "TRCK": "track",
    "TT2": "title", "TP1": "artist", "TAL": "album", "TRK": "track",
}

def _dec(raw):
    if not raw:
        return ""
    enc, body = raw[0], raw[1:]
    codec = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}.get(enc, "latin-1")
    try:
        s = body.decode(codec, "replace")
    except Exception:
        s = body.decode("latin-1", "replace")
    return s.split("\x00")[0].strip()

def _syncsafe(b):
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]

def parse_id3v2(head, body):
    """head = 10 byte tag header, body = tag bytes after it. -> (tags, v22_unparsed)"""
    ver, flags = head[3], head[5]
    tags = {}
    pos = 0
    if flags & 0x40:  # extended header: skip it
        if ver >= 4 and len(body) >= 4:
            pos = _syncsafe(body[:4])
        elif len(body) >= 4:
            pos = 4 + struct.unpack(">I", body[:4])[0]
    if ver == 2:
        while pos + 6 <= len(body):
            fid = body[pos:pos + 3].decode("latin-1", "replace")
            if not fid.strip("\x00"):
                break
            fsize = int.from_bytes(body[pos + 3:pos + 6], "big")
            if fsize <= 0 or pos + 6 + fsize > len(body):
                break
            if fid in TEXT_FRAMES:
                tags[TEXT_FRAMES[fid]] = _dec(body[pos + 6:pos + 6 + fsize])
            pos += 6 + fsize
        return tags, (not tags)
    while pos + 10 <= len(body):
        fid = body[pos:pos + 4].decode("latin-1", "replace")
        if not fid.strip("\x00"):
            break
        sz = body[pos + 4:pos + 8]
        fsize = _syncsafe(sz) if ver >= 4 else struct.unpack(">I", sz)[0]
        if fsize <= 0 or pos + 10 + fsize > len(body):
            break
        if fid in TEXT_FRAMES:
            tags[TEXT_FRAMES[fid]] = _dec(body[pos + 10:pos + 10 + fsize])
        pos += 10 + fsize
    return tags, False

# ---------- MPEG frame ----------

BITRATES = {  # (mpeg_version_id, layer_bits) -> table
    (3, 3): [0,32,64,96,128,160,192,224,256,288,320,352,384,416,448],   # V1 L1
    (3, 2): [0,32,48,56,64,80,96,112,128,160,192,224,256,320,384],      # V1 L2
    (3, 1): [0,32,40,48,56,64,80,96,112,128,160,192,224,256,320],       # V1 L3
    (2, 3): [0,32,48,56,64,80,96,112,128,144,160,176,192,224,256],      # V2 L1
    (2, 1): [0,8,16,24,32,40,48,56,64,80,96,112,128,144,160],           # V2 L2/L3
}
BITRATES[(2, 2)] = BITRATES[(2, 1)]
for _l in (1, 2, 3):
    BITRATES[(0, _l)] = BITRATES[(2, _l)]  # MPEG 2.5 uses V2 tables
SAMPLERATES = {3: [44100,48000,32000], 2: [22050,24000,16000], 0: [11025,12000,8000]}

def parse_frame(buf):
    """Find first plausible MPEG audio frame. -> (bitrate_kbps, samplerate, offset, vid, layer, mono) or None"""
    for i in range(0, max(0, len(buf) - 4)):
        if buf[i] != 0xFF or (buf[i + 1] & 0xE0) != 0xE0:
            continue
        b1, b2, b3 = buf[i + 1], buf[i + 2], buf[i + 3]
        vid, layer = (b1 >> 3) & 3, (b1 >> 1) & 3
        bi, si = (b2 >> 4) & 0xF, (b2 >> 2) & 3
        if vid == 1 or layer == 0 or bi in (0, 15) or si == 3:
            continue
        return (BITRATES[(vid, layer)][bi], SAMPLERATES[vid][si], i, vid, layer, ((b3 >> 6) & 3) == 3)
    return None

def xing_frames(buf, off, vid, mono):
    side = (17 if mono else 32) if vid == 3 else (9 if mono else 17)
    p = off + 4 + side
    if buf[p:p + 4] not in (b"Xing", b"Info"):
        return None
    flags = struct.unpack(">I", buf[p + 4:p + 8])[0]
    if not flags & 1:
        return 0  # VBR flagged, frame count unknown
    return struct.unpack(">I", buf[p + 8:p + 12])[0]

def samples_per_frame(vid, layer):
    if layer == 3:
        return 384
    if layer == 2:
        return 1152
    return 1152 if vid == 3 else 576

# ---------- per-file ----------

def scan_mp3(path, size):
    r = {"id3v2": False, "id3v1": False, "v22_unparsed": False, "tags": {},
         "bitrate": None, "vbr": False, "duration": None}
    with open(path, "rb") as f:
        head = f.read(10)
        audio_off = 0
        if head[:3] == b"ID3":
            r["id3v2"] = True
            tsize = _syncsafe(head[6:10])
            audio_off = 10 + tsize
            body = f.read(min(tsize, 512 * 1024))
            try:
                r["tags"], r["v22_unparsed"] = parse_id3v2(head, body)
            except Exception:
                r["v22_unparsed"] = True
            f.seek(audio_off)
        else:
            f.seek(0)
        buf = f.read(8192)
        if size >= 128:
            f.seek(-128, os.SEEK_END)
            if f.read(3) == b"TAG":
                r["id3v1"] = True
    fr = parse_frame(buf)
    if fr:
        br, sr, off, vid, layer, mono = fr
        r["bitrate"] = br
        nframes = xing_frames(buf, off, vid, mono)
        if nframes is not None:
            r["vbr"] = True
            if nframes:
                r["duration"] = nframes * samples_per_frame(vid, layer) / float(sr)
        if r["duration"] is None:
            audio_bytes = size - audio_off - (128 if r["id3v1"] else 0)
            if audio_bytes > 0:
                r["duration"] = audio_bytes * 8.0 / (br * 1000)
    return r

# ---------- walking / report ----------

JUNK = re.compile(r"^track ?\d+|untitled|^audiotrack|^\d{1,2}$|unknown", re.I)
AUDIO_OTHER = (".flac", ".m4a", ".ogg", ".wma", ".wav")
NORM = re.compile(r"[^a-z0-9]+")

def walk(root, d1names, counts):
    try:
        it = list(os.scandir(root))
    except OSError:
        counts["errors"] += 1
        return
    for e in it:
        try:
            if e.is_dir(follow_symlinks=False):
                if counts["depth"] == 0:
                    d1names.append(e.name)
                    counts["d1"] += 1
                elif counts["depth"] == 1:
                    counts["d2"] += 1
                counts["depth"] += 1
                for x in walk(e.path, d1names, counts):
                    yield x
                counts["depth"] -= 1
            else:
                yield e.path, e.name, e.stat().st_size
        except OSError:
            counts["errors"] += 1

def bucket_bitrate(br, vbr):
    if vbr:
        return "VBR"
    if br is None:
        return "unparseable"
    if br < 128: return "<128"
    if br == 128: return "128"
    if br == 160: return "160"
    if br == 192: return "192"
    if 224 <= br <= 256: return "224-256"
    if br == 320: return "320"
    return "other"

def bucket_dur(d):
    if d is None: return "unknown"
    m = d / 60.0
    if m < 1: return "<1min"
    if m < 3: return "1-3min"
    if m < 6: return "3-6min"
    if m < 10: return "6-10min"
    return ">10min"

def classify_dir(n):
    if re.match(r"^[\[(]?(19|20)\d{2}", n):
        return "year-prefixed"
    if " - " in n:
        return "Artist - Album"
    if not re.search(r"\d{2}", n):
        return "Artist"
    return "other"

def main(root, out):
    exts = collections.Counter()
    ext_size = collections.Counter()
    total_size = 0
    n = 0
    mp3 = dict(total=0, v2=0, v1=0, neither=0, v22=0,
               no_title=0, no_artist=0, no_album=0, no_track=0, junk=0)
    brb, durb = collections.Counter(), collections.Counter()
    keyA, keyB = collections.Counter(), collections.Counter()
    d1names, counts = [], {"errors": 0, "d1": 0, "d2": 0, "depth": 0}

    for path, name, size in walk(root, d1names, counts):
        n += 1
        if n % 1000 == 0:
            sys.stderr.write("... %d files\n" % n)
            sys.stderr.flush()
        ext = os.path.splitext(name)[1].lower()
        exts[ext] += 1
        ext_size[ext] += size
        total_size += size
        if ext != ".mp3":
            continue
        mp3["total"] += 1
        try:
            r = scan_mp3(path, size)
        except Exception:
            counts["errors"] += 1
            brb["unparseable"] += 1
            durb["unknown"] += 1
            continue
        if r["id3v2"]: mp3["v2"] += 1
        if r["id3v1"]: mp3["v1"] += 1
        if not r["id3v2"] and not r["id3v1"]: mp3["neither"] += 1
        if r["v22_unparsed"]: mp3["v22"] += 1
        t = r["tags"]
        for k, c in (("title", "no_title"), ("artist", "no_artist"),
                     ("album", "no_album"), ("track", "no_track")):
            if not t.get(k):
                mp3[c] += 1
        stem = os.path.splitext(name)[0]
        if JUNK.search(t.get("title", "")) or JUNK.search(stem):
            mp3["junk"] += 1
        brb[bucket_bitrate(r["bitrate"], r["vbr"])] += 1
        durb[bucket_dur(r["duration"])] += 1
        if r["duration"] is not None:
            keyA[(size // 1024, int(round(r["duration"])))] += 1
        if t.get("artist") and t.get("title"):
            keyB[(NORM.sub("", t["artist"].lower()), NORM.sub("", t["title"].lower()))] += 1

    def dupes(c):
        g = [v for v in c.values() if v > 1]
        return len(g), sum(g) - len(g)

    L = []
    a = L.append
    pct = lambda x, tot: "%.1f%%" % (100.0 * x / tot) if tot else "n/a"
    a("# MP3 Library Inventory\n")
    a("Root: `%s`  \nFiles scanned: %d  \nTotal size: %.2f GB\n" % (root, n, total_size / 1e9))
    a("## Files by extension\n")
    a("| ext | count | size (GB) |\n|---|---:|---:|")
    for e, c in exts.most_common(40):
        a("| %s | %d | %.2f |" % (e or "(none)", c, ext_size[e] / 1e9))
    a("\n## Non-mp3 audio\n")
    a(", ".join("%s: %d" % (e, exts.get(e, 0)) for e in AUDIO_OTHER) or "none")
    T = mp3["total"]
    a("\n## MP3 tags (%d files)\n" % T)
    a("| metric | count | share |\n|---|---:|---:|")
    for label, k in (("ID3v2 header", "v2"), ("ID3v1 trailer", "v1"), ("neither", "neither"),
                     ("ID3v2.2 unparsed", "v22"), ("missing title", "no_title"),
                     ("missing artist", "no_artist"), ("missing album", "no_album"),
                     ("missing track", "no_track"), ("junk title/filename", "junk")):
        a("| %s | %d | %s |" % (label, mp3[k], pct(mp3[k], T)))
    a("\n## Bitrate\n")
    a("| bucket | count |\n|---|---:|")
    for b in ("<128", "128", "160", "192", "224-256", "320", "other", "VBR", "unparseable"):
        if brb.get(b):
            a("| %s | %d |" % (b, brb[b]))
    a("\n## Duration\n")
    a("| bucket | count |\n|---|---:|")
    for b in ("<1min", "1-3min", "3-6min", "6-10min", ">10min", "unknown"):
        if durb.get(b):
            a("| %s | %d |" % (b, durb[b]))
    a("\n## Folder structure\n")
    a("Dirs at depth 1: %d, at depth 2: %d\n" % (counts["d1"], counts["d2"]))
    kinds = collections.Counter(classify_dir(x) for x in d1names)
    a("| depth-1 name shape | count |\n|---|---:|")
    for k, c in kinds.most_common():
        a("| %s | %d |" % (k, c))
    a("\nSample depth-1 names:\n")
    for x in sorted(d1names)[:30]:
        a("- `%s`" % x)
    ga, sa = dupes(keyA)
    gb, sb = dupes(keyB)
    a("\n## Rough duplicate estimates\n")
    a("- A (size-KB + duration-sec): %d groups, %d surplus files" % (ga, sa))
    a("- B (normalized artist+title): %d groups, %d surplus files" % (gb, sb))
    a("\nErrors: %d" % counts["errors"])
    txt = "\n".join(L) + "\n"
    sys.stdout.write(txt)
    with open(out, "w", encoding="utf-8") as f:
        f.write(txt)
    sys.stderr.write("wrote %s\n" % out)

# ---------- selftest ----------

def _frame_hdr():
    return bytes([0xFF, 0xFB, 0x90, 0x00])  # MPEG1 L3 128kbps 44100 stereo

def selftest():
    d = tempfile.mkdtemp()
    # file 1: ID3v2.3 with TIT2 + TPE1, then CBR frame
    def frame(fid, text):
        b = b"\x00" + text.encode("latin-1")
        return fid + struct.pack(">I", len(b)) + b"\x00\x00" + b
    body = frame(b"TIT2", "Hello Title") + frame(b"TPE1", "Some Artist")
    sz = len(body)
    ss = bytes([(sz >> 21) & 127, (sz >> 14) & 127, (sz >> 7) & 127, sz & 127])
    p1 = os.path.join(d, "a.mp3")
    with open(p1, "wb") as f:
        f.write(b"ID3\x03\x00\x00" + ss + body + _frame_hdr() + b"\x00" * 4000)
    # file 2: audio then ID3v1 only
    p2 = os.path.join(d, "b.mp3")
    v1 = b"TAG" + b"T2".ljust(30, b"\x00") + b"A2".ljust(30, b"\x00") + b"\x00" * 65
    with open(p2, "wb") as f:
        f.write(_frame_hdr() + b"\x00" * 4000 + v1)

    r = scan_mp3(p1, os.path.getsize(p1))
    assert r["id3v2"] and not r["id3v1"], r
    assert r["tags"]["title"] == "Hello Title", r
    assert r["tags"]["artist"] == "Some Artist", r
    assert r["bitrate"] == 128 and not r["vbr"], r
    assert r["duration"] and 0.2 < r["duration"] < 0.3, r
    r2 = scan_mp3(p2, os.path.getsize(p2))
    assert r2["id3v1"] and not r2["id3v2"], r2
    assert r2["bitrate"] == 128, r2
    assert bucket_bitrate(128, False) == "128" and bucket_bitrate(None, True) == "VBR"
    assert JUNK.search("Track 03") and JUNK.search("07") and not JUNK.search("Real Song")
    print("selftest OK")

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--selftest" in args:
        selftest()
    elif not args:
        print(__doc__)
        sys.exit(2)
    else:
        out = "inventory.md"
        if "--out" in args:
            i = args.index("--out")
            out = args[i + 1]
            del args[i:i + 2]
        main(args[0], out)
