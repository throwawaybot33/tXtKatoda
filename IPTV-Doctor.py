#!/usr/bin/env python3
"""
IPTV DOCTOR — playlist diagnostika i čišćenje
Tests every stream in an .m3u playlist FROM YOUR connection, removes dead links,
flags geo-blocked ones, writes a clean playlist + report.

Usage:
  python3 IPTV-Doctor.py playlist.m3u                  # local file
  python3 IPTV-Doctor.py https://site/list.m3u         # remote URL
  python3 IPTV-Doctor.py list.m3u --workers 32 --timeout 6
Requires: pip install requests
"""
import argparse, concurrent.futures as cf, os, re, sys, time
try:
    import requests
except ImportError:
    sys.exit("Missing dependency: pip install requests")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.3"}

GEO_HOSTS = ("nexttv.ht.hr", "cloudfront.net", "agatin.hr", "getaj.net")  # known geo-restricted CDNs

# ---------- parsing ----------
def parse_m3u(text):
    entries, block = [], []
    for line in text.splitlines():
        line = line.rstrip()
        if not line or line == "#EXTM3U":
            continue
        if line.startswith("#"):
            block.append(line)
        else:
            if any(l.startswith("#EXTINF") for l in block):
                entries.append({"block": block[:], "url": line.strip()})
            block = []
    return entries

def name_of(e):
    hdr = next(l for l in e["block"] if l.startswith("#EXTINF"))
    return re.sub(r"\s+", " ", hdr.rsplit(",", 1)[-1]).strip()

# ---------- testing ----------
def probe(url, timeout):
    try:
        t0 = time.time()
        with requests.get(url, headers={**UA, "Range": "bytes=0-1024"},
                          timeout=timeout, stream=True) as r:
            chunk = next(r.iter_content(512), b"")
            dt = time.time() - t0
            if r.status_code in (200, 206) and chunk:
                return ("OK", dt) if dt < 4 else ("SLOW", dt)
            return ("GEO?" if r.status_code in (401, 403, 404) else f"HTTP{r.status_code}", dt)
    except Exception:
        return ("DEAD", 0)

def test_entry(e, timeout):
    if "youtube.com" in e["url"] or "youtu.be" in e["url"]:
        return e, "YOUTUBE", 0
    status, dt = probe(e["url"], timeout)
    if status in ("DEAD", "GEO?"):          # one retry, longer breath
        status2, dt2 = probe(e["url"], timeout * 2)
        if status2 == "OK":
            status, dt = "OK", dt2
        elif status == "DEAD":
            status = status2 if status2 != "OK" else status
    if status == "GEO?" and any(h in e["url"] for h in GEO_HOSTS):
        status = "GEO-LOCKED"
    return e, status, dt

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser(description="IPTV Doctor — prune dead streams")
    ap.add_argument("source", help=".m3u file path or URL")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--timeout", type=int, default=6)
    ap.add_argument("--outdir", default=None, help="where to write results (default: same folder)")
    a = ap.parse_args()

    if a.source.startswith("http"):
        print(f"⬇  Downloading {a.source}")
        text = requests.get(a.source, headers=UA, timeout=60).text
        base = "remote-playlist"
    else:
        text = open(a.source, encoding="utf-8", errors="replace").read()
        base = os.path.splitext(os.path.basename(a.source))[0]

    entries = parse_m3u(text)
    seen, uniq = set(), []
    for e in entries:                        # dedupe identical URLs
        if e["url"] not in seen:
            seen.add(e["url"]); uniq.append(e)
    print(f"📋 {len(uniq)} unique streams — testing from THIS connection...\n")

    results = []
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(test_entry, e, a.timeout): e for e in uniq}
        done = 0
        for f in cf.as_completed(futs):
            results.append(f.result()); done += 1
            print(f"\r   {done}/{len(uniq)} tested", end="", flush=True)
    print("\n")

    order = {"OK": 0, "SLOW": 1, "GEO-LOCKED": 2, "GEO?": 3, "YOUTUBE": 4}
    results.sort(key=lambda r: order.get(r[1], 5))
    alive   = [(e, s, dt) for e, s, dt in results if s in ("OK", "SLOW")]
    problem = [(e, s, dt) for e, s, dt in results if s not in ("OK", "SLOW")]

    outdir = a.outdir or (os.path.dirname(os.path.abspath(a.source)) if not a.source.startswith("http") else ".")
    clean_path  = os.path.join(outdir, base + "-CLEAN.m3u")
    report_path = os.path.join(outdir, base + "-report.txt")

    with open(clean_path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n# Cleaned by IPTV Doctor — only streams alive from this connection\n")
        for e, s, dt in alive:
            for l in e["block"]:
                f.write(l + "\n")
            f.write(e["url"] + "\n")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"IPTV Doctor report — {time.strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"Source: {a.source}\nAlive: {len(alive)} | Removed/flagged: {len(problem)}\n\n")
        f.write("== ALIVE ==\n")
        for e, s, dt in alive:
            f.write(f"[{s:4}] {dt:4.1f}s  {name_of(e)}\n")
        f.write("\n== REMOVED / FLAGGED ==\n")
        for e, s, dt in problem:
            f.write(f"[{s:9}] {name_of(e)}  ->  {e['url']}\n")

    print(f"✅ ALIVE: {len(alive)}   ❌ removed/flagged: {len(problem)}")
    print(f"📄 Clean playlist: {clean_path}")
    print(f"📄 Report:         {report_path}")
    geo = [e for e, s, _ in problem if s == "GEO-LOCKED"]
    if geo:
        print(f"\n🌍 {len(geo)} geo-locked channels — rerun this script from the right country and they may turn green.")

if __name__ == "__main__":
    main()
