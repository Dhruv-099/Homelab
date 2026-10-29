# CLAUDE.md — ~/Homelab

Agent/LLM notes for this repo: a Docker Compose homelab where each service lives in its own folder with its own `docker-compose.yml`. Secrets live in the shared root `.env` (never commit it, never print it into chat — `.env.example` is the safe template). Most stacks join the external `homelab` Docker network; create it with `docker network create homelab` if missing. Some compose files add a dedicated internal network (e.g. `arr/` uses `arr_network`).

---

## 1. Mirroring GitHub repos into Forgejo

Forgejo serves `https://git.example.com` from `forgejo/docker-compose.yml`:
- HTTP API on host port **3000** (`http://localhost:3000/api/v1`)
- SSH on host port **222**
- Admin user: **`Dhruv-099`**
- Repo data lives on the storage drive (`FORGEJO_DATA_DIR=/mnt/storage-931gb/forgejo`); Postgres in the `forgejo_db` container.

### Credentials
- `~/.config/mirror.env` (mode 600) holds:
  - `FJ_TOKEN` — Forgejo access token, admin scope (`write:repository`, `write:organization`, `read:user`)
  - `GH_TOKEN` — GitHub classic PAT with `repo` scope (needed for private repos and starred list)
- Source it with `set -a; . ~/.config/mirror.env; set +a`. Never echo the values. Rotate in place with `sed -i 's/^GH_TOKEN=.*/GH_TOKEN=<new>/' ~/.config/mirror.env` (401s mean expired/revoked).

### How mirrors are created
Everything goes through `POST /api/v1/repos/migrate` with a JSON body:

```json
{
  "clone_addr": "https://github.com/<owner>/<repo>.git",
  "repo_name": "<repo_name>",
  "repo_owner": "Dhruv-099 | starred",
  "service": "git",
  "mirror": true,
  "mirror_interval": "8h0m0s",
  "private": true,
  "auth_username": "Dhruv-099",
  "auth_password": "<GH_TOKEN>"
}
```

Two classes of mirror:
1. **Own repos** → owner `Dhruv-099`, `private` copies the GitHub flag. Requires `auth_username`/`auth_password` with the PAT.
2. **Starred repos** → the **`starred` org**. Name = GitHub `full_name` with `/` → `-`, trailing `-` stripped, truncated to 90 chars (Forgejo rejects longer). Always public; no auth needed.

### Hard-won gotchas (from doing this for real)
- **Migration is synchronous** — the API call doesn't return until the clone finishes. Big repos (pytorch-sized) need `timeout`/curl `-m` up to **900–1800 s**. Parallelize with at most 2–3 workers via `ThreadPoolExecutor`; more just stacks timeouts.
- **`service: "github"` breaks for private repos** during migrate. Use `service: "git"` + `auth_username`/`auth_password` instead.
- **Private mirrors whose periodic sync fails** (log shows `Password for` / `SyncMirrors ... failed`): Forgejo didn't persist the credentials. Fix by embedding the PAT in the bare repo's remote, inside the container:
  ```
  docker exec -e T="$GH_TOKEN" forgejo sh -c \
    'git --git-dir=/data/git/repositories/<owner>/<name>.git config remote.origin.url \
     "https://Dhruv-099:${T}@github.com/<owner>/<repo>.git"'
  ```
- **Stuck rows:** a repo stuck mid-migration shows `status=1` with no row in the `mirror` table. Delete it via `DELETE /api/v1/repos/<owner>/<name>` and re-migrate. GitHub 404s (deleted/renamed star) will never converge — delete those rows for good.
- **409** on migrate = repo already exists; treat as skip, not error.

### Operations
- Force a sync now: `POST /api/v1/repos/<owner>/<repo>/mirror-sync`
- Health check (mirror count vs stuck rows) via the DB:
  ```
  docker exec forgejo_db psql -U forgejo -d forgejo -t -A -F' ' -c \
    "select u.lower_name, count(*) filter (where exists(select 1 from mirror m where m.repo_id=r.id)) ok, \
     count(*) filter (where r.status=1 and not exists(select 1 from mirror m where m.repo_id=r.id)) stuck, \
     count(*) total from repository r join \"user\" u on u.id=r.owner_id \
     where u.lower_name in ('dhruv-099','starred') group by 1;"
  ```
- Errors to watch for: `docker logs forgejo | grep -i 'SyncMirrors\|Password for'`

### Reverse direction (Forgejo → local disk backup)
`~/bin/forgejo-mirror.sh` clones/updates bare mirrors of **all Forgejo repos + everything starred on Forgejo** into `~/forgejo-mirror/<owner>/<repo>.git` (`git clone --mirror` over SSH port 222; re-running does `git remote update --prune`). It reads `FORGEJO_API` (default `http://localhost:3000/api/v1`) and needs a **`FORGEJO_TOKEN`** env var — bridge it from mirror.env:
```
set -a; . ~/.config/mirror.env; FORGEJO_TOKEN=$FJ_TOKEN; set +a; ~/bin/forgejo-mirror.sh
```

---

## 2. Navidrome pipeline

Navidrome (`navidrome/docker-compose.yml`, port **4533**) is the music streamer. It never talks to the download stack directly — the connection is purely a **shared filesystem path** on the media drive:

```
Prowlarr (9696)  ──indexers──▶  Lidarr (8686)  ──downloads──▶  qBittorrent (8090)
      arr_network   adds artists         /data/Downloads (torrents land here)
                                          │  Lidarr imports + renames
                                          ▼
              /mnt/sdb1/Media/Music   ◀── Lidarr root folder is /data/Music
                        ▲
                        │ read-only bind mount (NAVIDROME_MUSIC_DIR)
              Navidrome /music → scans every 1h (ND_SCANSCHEDULE)
```

Key wiring facts:
- `MEDIA_DIR=/mnt/sdb1/Media` is bind-mounted at **`/data`** inside radarr, sonarr, **lidarr**, bazarr, and qbittorrent. Music must therefore be imported to **`/data/Music`** = host `/mnt/sdb1/Media/Music`.
- Navidrome mounts that same Music folder at **`/music`, read-only** (`NAVIDROME_MUSIC_DIR`). App state lives in `navidrome/data/` (SQLite `navidrome.db`); nothing is stored in the library folder.
- Network topology: Lidarr/qBittorrent/Prowlarr sit on **both** `homelab` and `arr_network`; **Navidrome is only on `homelab`** — it does not and should not join `arr_network`.
- Music publish delay is at most the hourly scan plus the built-in file watcher, which picks up new folders within seconds. Lidarr's import is the only writer to `/data/Music` besides manual copies.
- Manual scan if ever needed: `docker exec navidrome /app/navidrome scan` (logs: `docker logs navidrome --since 5m | grep -i scanner`).

### Current pipeline state (details in `navidrome/REFERENCE.txt`)
- Library contains exactly one deliberately-legal test album: **Nine Inch Nails – Ghosts I-IV** (36 tracks, MP3 320, Creative Commons — free to share). The search/import test went: 15 releases found, 8 with 0 seeders, grabbed the 320 kbps copy with 28 seeders, Lidarr imported 36 tracks, Navidrome auto-detected them.
- **Admin account `Dhruv099` was created 2026-10-30** (first login = admin; playlists now import normally). Next step in that area is enabling ListenBrainz scrobbling in settings.
- **Lidarr (8686):** root folder `/data/Music`; quality profiles are Any / Standard (lossy 192+ kbps) / Lossless (FLAC) — lossless is explicitly NOT required, 320 kbps is the chosen bar. Metadata profile: Standard. "Rename tracks" is ON; layout is `<Artist>/<Album> (<Year>)/CD NN/<Artist> - <Album> - NN - <Track title>.mp3` (doubled numbers come from the track titles themselves).
- **Prowlarr (9696):** 9 indexers configured but only **1337x, Knaben, and The Pirate Bay** sync to Lidarr as music sources; the rest are TV/movie sites. 1337x has health warnings, so effectively 2 music indexers.
- **Deliberate non-goals** (decided in the working session, don't set these up casually): no bulk YouTube→audio tools (Downtify/zotify/Tubifarry's YouTube part), no Octo-Fiesta (Subsonic proxy that pulls from Deezer/Qobuz — ToS/DRM issues), no Soulseek/Usenet until a VPN + gluetun decision is made (qBittorrent currently uses the host's real IP; the `warp` container is proxy-only and nothing P2P routes through it). Discovery plan, in order: ListenBrainz scrobbling → Aurral (request layer on Lidarr; needs Last.fm API key + MusicBrainz email) → AudioMuse-AI later once the library is bigger.
- Live TODO list (as of 2026-10-30): ~~create admin user~~ (done), ~~fix/remove 1337x~~ (done), set up ListenBrainz, pick a client (Feishin/Substreamer), decide on Aurral, decide VPN+gluetun before any Soulseek. See section 8 of `REFERENCE.txt` for the full list and section 3A for open questions to discuss.

---

## Anything else in this repo

- Pointers for humans: `README.md` (architecture + service inventory), `REPRODUCIBLE.md` (full redeploy guide), `SECURITY.md` (secrets/mounts policy).
- `Homelab/.env` is a symlink target for every service folder: `scripts/link-env.sh` creates per-folder `.env` symlinks like `forgejo/.env → ../.env`.
- `~/bin/homelab-check.sh` runs daily at 08:15 (user crontab) and writes `~/bin/homelab-check.log` — a host/drive/container audit.
- Alerting chain: Watchtower + Scrutiny webhooks → `homelab-notifier/inbox` (SQLite queue) → notifier → Telegram. If Telegram is down, alerts queue instead of dropping.
