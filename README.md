# Homelab Infrastructure-as-Code (IaC)

This repository is the proof of work for a personal homelab built on Docker Compose and Proxmox.

It documents the architecture, services, and infrastructure used in the environment. For design rationale and deeper explanation, see my Medium articles at https://medium.com/@dhruvb2603. If you want to reproduce the stack, follow the separate guide in `REPRODUCIBLE.md`.

---

## Homelab at a glance
- Host: HP EliteDesk 705 running Proxmox VE
- Orchestration: Docker Compose / Portainer
- Networking: Nginx Proxy Manager, Netbird VPN
- Storage: local block storage with on-prem backups

---

## Service inventory

| Area | Service | Folder | Purpose |
| --- | --- | --- | --- |
| Git hosting | Forgejo | `forgejo/` | self-hosted Git, issue tracking, code collaboration |
| File sync | Nextcloud | `nextcloud/` | file sharing, calendar, contacts |
| Media | Jellyfin | `jellyfin/` | media streaming |
| Media management | Radarr/Sonarr/Lidarr/Bazarr/Prowlarr | `arr/` | automated media downloads and organization |
| Downloads & requests | qBittorrent/Jellyseerr/FlareSolverr | `arr/` | torrent client, media requests, Cloudflare challenge solver |
| Music | Navidrome | `navidrome/` | personal music streaming |
| Photos | Immich | `immich-setup/` | photo backup and management |
| Monitoring | Scrutiny | `scrutiny/` | drive health and SMART monitoring |
| Passwords | Vaultwarden | `vaultwarden/` | secrets and password management |
| Reverse proxy | Nginx Proxy Manager | `proxymanager/` | host routing, SSL termination |
| Container UI | Portainer | `portainer/` | container management UI |
| Monitoring | Beszel | `beszel/` | system & container health metrics (hub + host agent, incl. data drives) |
| Updates | Watchtower | `watchtower/` | automated container image updates |
| Alerting | Notifier + inbox | `homelab-notifier/` | Telegram alerts for container/disk health, Watchtower update reports and Scrutiny drive health, queued in SQLite so none are lost |
| File management | FileBrowser Quantum | `filebrowser/` | web-based file browser for the data drives |
| Reading | Kavita | `kavita/` | comic/ebook server |
| Reading | Openbooks | `openbooks/` | Calibre/IRC ebook search and download |
| Wiki *(optional, not deployed)* | Bookstack | `bookstack/` | self-hosted documentation/wiki — replaced by Trilium |
| Notes | Trilium | `trillium/` | hierarchical personal notes |
| Tasks | Vikunja | `vikunja/` | task and to-do management |
| Offline docs | Kiwix | `Kiwix/` | offline ZIM archive server (docs, wikis) |
| PDF tools | BentoPDF | `BentoPDF/` | browser-based PDF utilities |
| Networking | Netbird | — (deployed separately, not tracked) | self-hosted WireGuard-based mesh VPN |
| Networking | WARP | `warp/` | Cloudflare WARP SOCKS5 proxy for outbound traffic |
| Utilities | OmniTools | `OmniTools/` | browser-based collection of everyday dev/file utilities |

---

## Architecture highlights
This repository is organized as a modular homelab stack. Each service has its own directory and compose file so the stack can scale by adding or removing services without changing the whole repo.

- Service definitions live in dedicated folders, making it easy to manage and update one stack at a time.
- Most services share the `homelab` network for internal communication, while external traffic is routed through Nginx Proxy Manager.
- Host-specific paths, credentials, and runtime configuration are moved into `.env` to keep the repository reusable and private.
- Sensitive mounts and secrets are documented in `SECURITY.md` rather than embedded inside compose files.
- Alerts flow through a SQLite queue (`homelab-notifier/data/alerts.db`): the `inbox` container receives webhooks from Watchtower and Scrutiny and only stores them; the `notifier` polls Beszel, enqueues its own alerts, and delivers everything to Telegram with retry. If the notifier or Telegram is down, alerts wait in the queue. The notifier also warns if Scrutiny gets no SMART report for 12h (the Proxmox collector cron may have stopped).
---

## What this repo includes
- Service stacks in dedicated folders
- `.env.example` as a template for all required local variables
- `SECURITY.md` with guidance on secrets handling
- `REPRODUCIBLE.md` with a fully reproducible deployment guide

---

## Intranet services
This homelab is intended to run internal services on the LAN. Internal DNS and proxy configuration are handled with:

- `proxymanager/` — Nginx Proxy Manager
- AdGuard Home service for DNS rewrites

The reproducible guide covers how to wire these services together.

---

## Reproducible setup
If you want to reproduce this stack, see `REPRODUCIBLE.md`.

---

## Backup policy
- Local primary storage
- Daily Duplicati backups
- Encrypted off-site backups

---

Maintained by Dhruv Bobal.
