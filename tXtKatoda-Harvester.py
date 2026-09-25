#!/usr/bin/env python3
"""
tXtKatoda HARVESTER — crawl public lists, keep the alive, watch the ecosystem breathe.

What it does:
  1. Pulls the SEED playlists below (edit freely — add countries/categories you like)
  2. Merges + dedupes all streams
  3. Ejects pirate-panel patterns (bare-IP restreams of pay channels, reseller hosts)
  4. Tests every stream in parallel from YOUR connection
  5. Writes a clean grouped .m3u + report + a stable latest.m3u (for apps)
  6. Remembers runs (state file) and tells you what's NEW / DIED / BACK since last time

Usage:
  python3 tXtKatoda-Harvester.py                          # full run
  python3 tXtKatoda-Harvester.py --only "Croatia,Balkan"  # just some sections
  python3 tXtKatoda-Harvester.py --max-per-seed 60        # quick run
  python3 tXtKatoda-Harvester.py --no-test                # merge only, no testing
  python3 tXtKatoda-Harvester.py --discover               # hunt NEW lists on GitHub
Requires: pip install requests
"""
import argparse, concurrent.futures as cf, json, os, re, shutil, sys, time
try:
    import requests
except ImportError:
    sys.exit("Missing dependency: pip install requests")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.3"}

# ---------------- CONFIG: seeds ----------------
# (section, url, keep_regex) — keep_regex=None keeps everything in that list
SEEDS = [
    ("Croatia",        "https://iptv-org.github.io/iptv/countries/hr.m3u", None),
    ("Croatia",        "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8", r'group-title="Croatia"'),
    ("Balkan",         "https://iptv-org.github.io/iptv/countries/rs.m3u", None),
    ("Balkan",         "https://iptv-org.github.io/iptv/countries/ba.m3u", None),
    ("Balkan",         "https://iptv-org.github.io/iptv/countries/si.m3u", None),
    ("Balkan",         "https://iptv-org.github.io/iptv/countries/mk.m3u", None),
    ("Deutschland",    "https://iptv-org.github.io/iptv/countries/de.m3u", None),
    ("Kids & Cartoons","https://iptv-org.github.io/iptv/categories/kids.m3u", r"\((1080p|720p)\)"),
    ("Kids & Cartoons","https://iptv-org.github.io/iptv/categories/animation.m3u", r"\((1080p|720p)\)"),
    ("Movies (FAST)",  "https://iptv-org.github.io/iptv/categories/movies.m3u", r"\((1080p|720p)\)"),
    ("Movies (FAST)",  "https://iptv-org.github.io/iptv/categories/series.m3u", r"\((1080p|720p)\)"),
    ("Music",          "https://iptv-org.github.io/iptv/categories/music.m3u", r"\((1080p|720p)\)"),
    ("World News",     "https://iptv-org.github.io/iptv/categories/news.m3u", r"\((1080p|720p)\)"),
    ("Docs & Science", "https://iptv-org.github.io/iptv/categories/documentary.m3u", r"\((1080p|720p)\)"),
]

# Pirate-pattern filters (learned in the field, updated 2026-09-26)
PANEL      = re.compile(r":\d{4,5}/play/|\.cfd/|auth=testpub|mcquack|iptvhd\.ru|iptvperu|bantel-cdn|mangora1"
                        r"|dash[34]\.antik\.sk"
                        r"|176\.61\.157\.250|138\.121\.15\.230|23\.237\.104\.106|38\.19\.41\.46|38\.75\.136\.137"
                        r"|151\.236\.247\.171|176\.118\.197\.101|88\.212\.15\.19|74\.91\.26\.218|92\.36\.202\.5"
                        r"|213\.91\.179\.28|5\.57\.74\.130|185\.227\.34\.179|151\.80\.18\.177|45\.134\.141\.161", re.I)
PAY_BRANDS = re.compile(r"disney|nickelodeon|nick jr|cartoon network|boomerang|\bHBO\b|cinemax|arena sport"
                        r"|sport klub|\bsky\b|beIN|AXN|cinecanal|\bHOT\b|\bsci[ -]?fi\b", re.I)
BARE_IP    = re.compile(r"https?://\d{1,3}(\.\d{1,3}){3}")

# ---------------- helpers ----------------
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
    n = re.sub(r"\s*[ⒼⓈⓎ]\s*", "", hdr.rsplit(",", 1)[-1])
    return re.sub(r"\s+", " ", n).replace("[Geo-blocked]", "").replace("[Not 24/7]", "").strip()

def dirty_reason(e):
    """None if clean, else the pattern class that caught it."""
    if PANEL.search(e["url"]):
        return "panel/provider host"
    if PAY_BRANDS.search(name_of(e)) and BARE_IP.match(e["url"]):
        return "pay brand on bare IP"
    return None

def is_dirty(e):
    return dirty_reason(e) is not None

def host_of(url):
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1) if m else "?"

def probe(url, timeout):
    try:
        t0 = time.time()
        with requests.get(url, headers={**UA, "Range": "bytes=0-1024"}, timeout=timeout, stream=True) as r:
            chunk = next(r.iter_content(512), b"")
            dt = time.time() - t0
            if r.status_code in (200, 206) and chunk:
                return ("OK" if dt < 4 else "SLOW", dt)
            return ("GEO?" if r.status_code in (401, 403, 404) else "BAD", dt)
    except Exception:
        return ("DEAD", 0)

def test_entry(e, timeout):
    if "youtube.com" in e["url"] or "youtu.be" in e["url"]:
        return e, "YOUTUBE", 0
    s, dt = probe(e["url"], timeout)
    if s in ("DEAD", "GEO?"):
        s2, dt2 = probe(e["url"], timeout * 2)
        if s2 == "OK":
            s, dt = "OK", dt2
    return e, s, dt

# ---------------- GitHub discovery ----------------
DISCOVER_QUERIES = ["iptv m3u playlist", "iptv playlist balkan", "m3u8 hrvatska", "free iptv m3u"]
SEED_REPOS = {"iptv-org/iptv", "Free-TV/IPTV"}   # already covered by seeds

def gh_get(url):
    r = requests.get(url, headers={**UA, "Accept": "application/vnd.github+json"}, timeout=15)
    r.raise_for_status()
    return r.json()

def discover_lists(max_repos, queries):
    """Search GitHub for recently-updated list repos, extract raw .m3u URLs."""
    repos, seen_r = [], set()
    for q in queries:
        try:
            d = gh_get(f"https://api.github.com/search/repositories?q={requests.utils.quote(q)}&sort=updated&per_page={max_repos}")
            for r in d.get("items", []):
                fn = r["full_name"]
                if fn not in seen_r and fn not in SEED_REPOS:
                    seen_r.add(fn); repos.append(r)
            time.sleep(2)  # be polite to the search API
        except Exception as ex:
            print(f"   ⚠ search failed for '{q}': {ex}")
    repos = repos[:max_repos]
    print(f"🔎 Discovery: {len(repos)} candidate repos — scanning for playlist files...")
    found = []
    for r in repos:
        fn, br = r["full_name"], r.get("default_branch", "main")
        try:
            t = gh_get(f"https://api.github.com/repos/{fn}/git/trees/{br}?recursive=1")
        except Exception:
            print(f"   ⚠ tree failed: {fn}"); continue
        files = [x["path"] for x in t.get("tree", [])
                 if x.get("type") == "blob" and re.search(r"\.(m3u8?|txt)$", x["path"], re.I)
                 and x.get("size", 0) and x["size"] < 3_000_000][:3]
        for p in files:
            found.append((fn, f"https://raw.githubusercontent.com/{fn}/{br}/{p}"))
        if files:
            print(f"   📁 {fn}: {len(files)} playlist file(s)")
    return found

def rebuild(e, group):
    hdr = next(l for l in e["block"] if l.startswith("#EXTINF"))
    attrs = hdr[:hdr.rfind(",")]
    attrs = re.sub(r'group-title="[^"]*"', f'group-title="{group}"', attrs)
    if "group-title" not in attrs:
        attrs += f' group-title="{group}"'
    lines = [attrs.rstrip() + "," + name_of(e)]
    lines += [l for l in e["block"] if not l.startswith("#EXTINF")]
    lines.append(e["url"])
    return "\n".join(lines)

# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help='comma sections, e.g. "Croatia,Balkan"')
    ap.add_argument("--max-per-seed", type=int, default=None)
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--timeout", type=int, default=5)
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--state", default=os.path.expanduser("~/.txtkatoda-harvester-state.json"))
    ap.add_argument("--no-test", action="store_true")
    ap.add_argument("--discover", action="store_true", help="hunt new lists on GitHub")
    ap.add_argument("--discover-repos", type=int, default=8)
    ap.add_argument("--discover-query", default=None, help="comma-separated GitHub queries, overrides built-in list")
    ap.add_argument("--discover-test-cap", type=int, default=25, help="max streams tested per discovered list")
    a = ap.parse_args()

    only = set(a.only.split(",")) if a.only else None
    seeds = [s for s in SEEDS if not only or s[0] in only]

    # 1. fetch seeds in parallel
    print(f"⬇  Fetching {len(seeds)} seed lists...")
    def get(seed):
        sec, url, keep = seed
        try:
            txt = requests.get(url, headers=UA, timeout=60).text
            ent = parse_m3u(txt)
            if keep:
                rx = re.compile(keep, re.I)
                ent = [e for e in ent if rx.search("\n".join(e["block"]))]
            return [(sec, e) for e in ent]
        except Exception as ex:
            print(f"   ⚠ seed failed: {url} ({ex})"); return []
    with cf.ThreadPoolExecutor(min(8, len(seeds))) as ex:
        fetched = list(ex.map(get, seeds))

    # 2. merge + dedupe + filter
    seen, pool, dropped = set(), [], 0
    evidence = []   # (source, claimed channel, host, pattern class)
    for seed_results in fetched:
        if a.max_per_seed:
            seed_results = seed_results[:a.max_per_seed]
        for sec, e in seed_results:
            if e["url"] in seen:
                continue
            seen.add(e["url"])
            why = dirty_reason(e)
            if why:
                dropped += 1
                evidence.append((sec, name_of(e), host_of(e["url"]), why))
                continue
            pool.append((sec, e))
    print(f"📋 {len(pool)} unique streams ({dropped} pirate-pattern junk ejected)")

    # 2b. GitHub discovery — find NEW lists, vet them, fold survivors in
    disc_stats = []   # (repo, url, total, dirty, kept)
    if a.discover:
        queries = a.discover_query.split(",") if a.discover_query else DISCOVER_QUERIES
        for repo, raw in discover_lists(a.discover_repos, queries):
            try:
                ent = parse_m3u(requests.get(raw, headers=UA, timeout=20).text)
            except Exception:
                continue
            if len(ent) < 5:
                continue
            dirty_n = sum(1 for e in ent if is_dirty(e))
            if dirty_n / len(ent) > 0.20:
                print(f"   🏴‍☠️ REJECTED (pirate-heavy, {dirty_n}/{len(ent)} dirty): {repo}")
                disc_stats.append((repo, raw, len(ent), dirty_n, 0))
                continue
            kept = 0
            for e in ent[:a.discover_test_cap]:
                why = dirty_reason(e)
                if why:
                    evidence.append((f"github:{repo}", name_of(e), host_of(e["url"]), why))
                    continue
                if e["url"] in seen:
                    continue
                seen.add(e["url"]); e["src"] = raw
                pool.append(("🧪 Discovered", e)); kept += 1
            if kept:
                print(f"   ✅ {repo}: {kept} streams accepted for testing")
            disc_stats.append((repo, raw, len(ent), dirty_n, kept))

    # 3. test
    if a.no_test:
        results = [(sec, e, "OK", 0) for sec, e in pool]
    else:
        print(f"🔬 Testing with {a.workers} workers...")
        results = []
        with cf.ThreadPoolExecutor(a.workers) as ex:
            futs = {ex.submit(test_entry, e, a.timeout): sec for sec, e in pool}
            for i, f in enumerate(cf.as_completed(futs), 1):
                e, s, dt = f.result()
                results.append((futs[f], e, s, dt))
                print(f"\r   {i}/{len(pool)}", end="", flush=True)
        print()

    # 4. state / churn
    today = time.strftime("%Y-%m-%d")
    state = json.load(open(a.state)) if os.path.exists(a.state) else {}
    new, died, back = [], [], []
    for sec, e, s, dt in results:
        u = e["url"]
        if u not in state:
            new.append(name_of(e))
        elif s == "OK" and state[u].get("status") != "OK":
            back.append(name_of(e))
        state[u] = {"name": name_of(e), "section": sec, "first": state.get(u, {}).get("first", today),
                    "status": s, "last_ok": today if s == "OK" else state.get(u, {}).get("last_ok")}
    known = set(state)
    current = {e["url"] for _, e, _, _ in results}
    for u in known - current:
        if state[u].get("status") == "OK":
            died.append(state[u]["name"]); state[u]["status"] = "GONE"
    os.makedirs(os.path.dirname(a.state) or ".", exist_ok=True)
    json.dump(state, open(a.state, "w"), indent=1)

    # 5. outputs
    alive = [(sec, e, s) for sec, e, s, dt in results if s in ("OK", "SLOW")]
    secs = []
    for sec, e, s in alive:
        if sec not in secs: secs.append(sec)
    out_m3u = os.path.join(a.outdir, f"tXtKatoda-MegaPack-{today}.m3u")
    with open(out_m3u, "w", encoding="utf-8") as f:
        f.write(f"#EXTM3U\n# tXtKatoda Harvester run {today} — {len(alive)} alive streams\n")
        for sec in secs:
            group = [(e, s) for sc, e, s in alive if sc == sec]
            f.write(f"\n# ===== {sec.upper()} ({len(group)}) =====\n")
            for e, s in group:
                f.write(rebuild(e, sec) + "\n")

    # stable name for apps — always the newest feed, URL never changes
    stable = os.path.join(a.outdir, "latest.m3u")
    shutil.copyfile(out_m3u, stable)

    print(f"\n{'='*46}\n✅ ALIVE: {len(alive)}   💀 dead/flagged: {len(results)-len(alive)}")
    print(f"🆕 NEW since last run: {len(new)}   ✝️  disappeared: {len(died)}   🔄 back from dead: {len(back)}")
    if new:   print("   new:  " + ", ".join(new[:15])[:180])
    if died:  print("   died: " + ", ".join(died[:15])[:180])
    if a.discover and disc_stats:
        print("\n🧪 DISCOVERY VERDICTS:")
        for repo, raw, total, dirty, kept in disc_stats:
            alive_src = sum(1 for sec, e, s, dt in results if e.get("src") == raw and s in ("OK", "SLOW"))
            verdict = "🏴‍☠️ pirate-heavy" if kept == 0 and dirty else (f"{alive_src}/{kept} alive" if kept else "empty/dead")
            print(f"   {verdict:>16}  {repo}")

    # 5b. evidence report — autopsy of what the filter caught (host-level, no playable URLs)
    ev_path = os.path.join(a.outdir, f"tXtKatoda-evidence-{today}.txt")
    with open(ev_path, "w", encoding="utf-8") as f:
        f.write(f"tXtKatoda evidence report — {today}\nPirate-pattern streams caught and excluded this run: {len(evidence)}\n")
        f.write("Hosts are recorded for documentation; playable URLs intentionally stripped.\n\n")
        by_reason = {}
        for src, nm, host, why in evidence:
            by_reason.setdefault(why, []).append((src, nm, host))
        for why, items in by_reason.items():
            f.write(f"== {why.upper()} ({len(items)}) ==\n")
            hosts = {}
            for src, nm, host in items:
                hosts.setdefault(host, []).append((src, nm))
            for host, lst in sorted(hosts.items(), key=lambda kv: -len(kv[1])):
                claimed = ", ".join(sorted({nm for _, nm in lst})[:6])
                f.write(f"  {host}  x{len(lst)}  claimed: {claimed}  (seen in: {sorted({s for s,_ in lst})[:3]})\n")
            f.write("\n")
    print(f"📄 Evidence:  {ev_path} ({len(evidence)} pirate entries documented)")

    print(f"📄 Playlist: {out_m3u}\n📄 Stable:   {stable}\n📄 State:    {a.state}")
    print("\nTip: run daily (cron/Task Scheduler) and the NEW/DIED lines start telling you the ecosystem's story.")

if __name__ == "__main__":
    main()
