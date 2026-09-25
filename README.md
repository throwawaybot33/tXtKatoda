# tXtKatoda 📺📟

Self-updating, legally-clean personal media toolkit.
It crawls public GitHub-hosted channel lists, ejects pirate-pattern streams,
tests what is actually alive, tracks daily churn, and keeps a fresh list ready.

Named after two retired friends: the cathode-ray tube and a certain text service's page system.

---

## 📥 Installation & first use (the 10-minute path)

You need two things: **a player app** on your TV + **a playlist** this repo provides.

### Step 1 — pick a player app (Android TV / Google TV)

| App | Cost | Pick it if |
|---|---|---|
| **Televizo** | free | you want it working in 2 minutes |
| **TiviMate** | free / ~€10 yr | you want the cable-box feel (guide grid, favorites, recording) |
| **Sparkle TV** | free / cheap | you want timeshift / pause-live |

Install from the **Play Store on the TV** (no sideload needed).

### Step 2 — add the playlist (two ways)

**A. URL (recommended — auto-updates):**
in the app: *Add playlist → M3U URL* → paste one of these:

```
https://raw.githubusercontent.com/throwawaybot33/tXtKatoda/main/playlists/IPTV-Croatia-verified.m3u
https://raw.githubusercontent.com/throwawaybot33/tXtKatoda/main/playlists/IPTV-World-Starter-verified.m3u
```

**B. USB stick:** download any `.m3u` from `playlists/` → copy to USB → *Add playlist → local file*.

### Step 3 (optional) — program guide (EPG)

*Settings → EPG URL* → paste:

```
https://epgshare01.online/epgshare01/epg_ripper_HR1.xml.gz
```

Done. Zap, favorite, hide what you don't like.

---

## 📡 The self-updating feed (after the Action runs once)

Point your player at this URL — it never changes, content refreshes daily:

```
https://raw.githubusercontent.com/throwawaybot33/tXtKatoda/main/feed/latest.m3u
```

(`feed/latest.m3u` = always the newest tested harvest. Dated files next to it are just history.)

---

## 🌍 Two editions of the feed (read once)

| Edition | Made by | Contains | Use when |
|---|---|---|---|
| **Home edition** | Harvester/Doctor run on *your* Croatian connection | everything incl. geo-locked HR streams | you're in Croatia |
| **Cloud edition** | the GitHub Action (runs outside Croatia) | everything *except* geo-locked HR streams | you're traveling |

Same code — the tester simply keeps what it can reach from where it runs.
Geo-locked streams (HRT HD, RTL official CDN) only answer Croatian IPs.

---

## Components

| File | What it does |
|---|---|
| `tXtKatoda-Harvester.py` | Crawls seed lists → dedupe → pirate-filter → stream-test → dated clean `.m3u` + stable `latest.m3u` + churn report (NEW/DIED/BACK) + evidence report. `--discover` hunts new lists on GitHub via the API. |
| `IPTV-Doctor.py` | Cleans any single playlist from *your* connection: prunes dead, flags geo-locked, writes clean file + report. |
| `playlists/` | Verified starter packs (Croatia, World). |
| `.github/workflows/daily-harvest.yml` | Free cloud pipeline: runs the Harvester every day, commits a fresh feed to `feed/`. |

## Quick start (power users)

```bash
pip install requests
python3 tXtKatoda-Harvester.py                          # full harvest
python3 tXtKatoda-Harvester.py --discover               # hunt new lists
python3 tXtKatoda-Harvester.py --only "Croatia,Balkan" --max-per-seed 60
python3 IPTV-Doctor.py my-list.m3u                      # clean any playlist
```

## Legal design (deliberate, not optional)

- Sources are publicly available free streams only (iptv-org, Free-TV, official broadcaster CDNs, FAST channels).
- Pirate-pattern streams (bare-IP restream panels, reseller hosts, pay brands on bare IPs) are **auto-ejected** and documented host-level in dated evidence reports.
- Personal use. If a rightsholder asks you to remove a stream, remove it.

## Roadmap

- [x] Harvester (crawl, filter, test, churn, evidence)
- [x] Discovery mode (GitHub API)
- [x] Daily cloud feed (Actions cron)
- [ ] tXtKatoda APK — fork of an open-source Android TV player, branded, this feed baked in
