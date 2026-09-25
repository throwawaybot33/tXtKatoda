# tXtKatoda 📺📟

Self-updating, legally-clean personal media toolkit.
It crawls public GitHub-hosted channel lists, ejects pirate-pattern streams,
tests what is actually alive, tracks daily churn, and keeps a fresh list ready.

Named after two retired friends: the cathode-ray tube and a certain text service's page system.

## Components

| File | What it does |
|---|---|
| `tXtKatoda-Harvester.py` | Crawls seed lists → dedupe → pirate-filter → stream-test → dated clean `.m3u` + churn report (NEW/DIED/BACK) + evidence report. `--discover` hunts new lists on GitHub via the API. |
| `IPTV-Doctor.py` | Cleans any single playlist from *your* connection: prunes dead, flags geo-locked, writes clean file + report. |
| `playlists/` | Verified starter packs (Croatia, World). |
| `.github/workflows/daily-harvest.yml` | Free cloud pipeline: runs the Harvester every day and commits a fresh feed to `feed/`. |

## Quick start

```bash
pip install requests

# clean an existing playlist using YOUR connection (geo-correct)
python3 IPTV-Doctor.py playlists/IPTV-Croatia-verified.m3u

# full harvest of all seeds
python3 tXtKatoda-Harvester.py

# hunt for new lists on GitHub
python3 tXtKatoda-Harvester.py --discover --discover-repos 12

# only some sections, quick run
python3 tXtKatoda-Harvester.py --only "Croatia,Balkan" --max-per-seed 60
```

## The cloud pipeline

The GitHub Action runs the Harvester daily at 04:17 UTC and commits the
result to `feed/`. After the first run, your self-updating feed URL is:

```
https://raw.githubusercontent.com/<owner>/tXtKatoda/main/feed/tXtKatoda-MegaPack-<YYYY-MM-DD>.m3u
```

**Geo note:** GitHub runners are not in Croatia, so the cloud feed is the
*internationally-clean* edition. Run the Harvester at home for the Croatia-complete
edition (geo-locked official streams only test green from a Croatian IP).

## Legal design (deliberate, not optional)

- Sources are publicly available free streams only (iptv-org, Free-TV, official broadcaster CDNs, FAST channels).
- Pirate-pattern streams (bare-IP restream panels, known reseller hosts, pay brands on bare IPs)
  are **auto-ejected** and documented host-level (no playable URLs) in dated evidence reports.
- Personal use. If a rightsholder asks you to remove a stream, remove it.

## Roadmap

- [x] Harvester (crawl, filter, test, churn, evidence)
- [x] Discovery mode (GitHub API)
- [x] Daily cloud feed (Actions cron)
- [ ] tXtKatoda APK — fork of an open-source Android TV player, branded, this feed baked in
