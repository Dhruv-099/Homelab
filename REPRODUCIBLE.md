# Reproducible Homelab Guide

This document shows how to reproduce the homelab stack from this repository on a compatible Linux host.

> This is the implementation guide. The main `README.md` is a proof-of-work overview of the homelab architecture and services.

---

## Prerequisites

- A Linux host with Docker and Docker Compose v2 installed (see [Host setup](#host-setup) for the non-Docker pieces).
- Git access to this repository.
- A local `.env` file created from `.env.example`.
- Optional but recommended: Portainer for visual management.

### Software
- Docker Engine
- Docker Compose v2 or Docker Compose plugin
- Git
- Optional: `docker compose` command or Portainer

---

## Clone the repository

```bash
git clone https://example.com/your/homelab.git
cd homelab
```

Replace the clone URL with your repository location.

---

## Configure environment variables

Copy the example env file and set local values.

```bash
cp .env.example .env
```

Edit `.env` and provide values for:

- service passwords
- admin tokens
- trusted domains
- data directory paths
- media directories

> Do not commit `.env` to version control. It is ignored by `.gitignore`.

### Link `.env` into each stack

Docker Compose only reads `.env` from the folder it runs in, so a single root `.env` is not picked up by `cd nextcloud && docker compose up -d`. Symlink it into every stack folder:

```bash
./scripts/link-env.sh
```

Re-run it after adding a new service folder. The symlinks are gitignored.

---

## Create the shared network

Every stack joins an external `homelab` Docker network. Create it once before starting anything:

```bash
docker network create homelab
```

---

## Launching services

Each service folder contains a `docker-compose.yml` file. Use one of these approaches.

### Option A: Bring up a specific stack

```bash
cd nextcloud
docker compose up -d
```

Use the same pattern for other services:
- `cd forgejo && docker compose up -d`
- `cd proxymanager && docker compose up -d`
- `cd scrutiny && docker compose up -d`

### Option B: Launch multiple stacks together

```bash
for d in nextcloud forgejo; do (cd "$d" && docker compose up -d); done
```

Run each stack from its own folder. Avoid merging several files with `docker compose -f a.yml -f b.yml`: that creates one combined project and resolves every relative path (`./data`, `./config`) against the first file's folder.

### Check service health

```bash
docker compose ps
docker compose logs -f <service>
```

---

## Recommended deployment order

1. `proxymanager` — Nginx Proxy Manager for routing
2. `portainer` — container management UI (see the first-run note below)
3. `vaultwarden` — passwords and secrets management
4. `nextcloud` — storage and collaboration
5. `forgejo` — Git hosting
6. `immich-setup` — photo management
7. `arr` — *arr suite, qBittorrent, Jellyseerr, FlareSolverr (creates `arr_network`)
8. `warp` — Cloudflare WARP proxy; must come after `arr` because it joins `arr_network`
9. `jellyfin`, `navidrome`, `kavita`, `openbooks` — media services
10. `beszel` — system and container metrics
11. `homelab-notifier` — Telegram alerts; build with `docker compose up -d --build`
12. `watchtower` — after the notifier, since it posts update reports to it
13. `scrutiny` — drive monitoring
14. `vikunja`, `trillium`, `filebrowser` — tasks, notes, file management
    - `bookstack` is optional and not deployed in the live homelab (Trilium covers notes/docs). Deploy it the same way if you want a wiki.
15. `Kiwix`, `BentoPDF`, `OmniTools` — optional standalone utilities
16. Netbird — mesh VPN, deployed separately (not tracked in this repo; see NetBird docs)

### Portainer first run

- The UI is HTTPS-only: open `https://<host>:9443` and accept the self-signed certificate.
- Create the admin user within about 5 minutes of the first start. Otherwise Portainer locks setup for security and shows a timeout page; fix it with `docker restart portainer` and try again.

---

## Host setup

Everything below lives on the host, outside Docker, so the compose files alone do not recreate it. Reference copies are in [`host/`](host/). Written for Ubuntu Server 26.04 LTS (upgraded in place from 24.04) with a normal user at uid/gid 1000.

### Packages

- Docker Engine from Docker's apt repo (`docker-ce`, `docker-compose-plugin`), plus `ntfs-3g`, `ufw`, `cloudflared`, `netbird` and `nodejs` (used by the check script).
- Third-party repos are deb822 files in [`host/apt/`](host/apt/). Copy them to `/etc/apt/sources.list.d/` and install each signing key at the `Signed-By` path inside the file.
- `do-release-upgrade` renames third-party `.list` files to `*.list.disabled` and does not migrate them. After a release upgrade, re-add the `.sources` files and run `apt update`, or these packages silently stop updating.

### Data drives

[`host/fstab.example`](host/fstab.example) mounts the ext4 data drive at `/mnt/storage-931gb` and the NTFS media drive at `/mnt/sdb1` (ntfs-3g, `uid=1000`, so only uid 1000 can write). Both use `nofail`, so a missing drive does not block boot; the compose files refuse to start containers when a data drive is not mounted.

### Firewall

Two layers, because Docker-published ports bypass ufw's `INPUT` rules:

1. **ufw** (default deny incoming) allows only SSH (22), DNS (53/55) and NPM admin (82) from the LAN (`192.168.1.0/24`), the VPN (`100.95.0.0/16`) and Docker networks (`172.16.0.0/12`).
2. **`homelab-lockdown.service`** ([`host/systemd/`](host/systemd/homelab-lockdown.service)) rewrites `DOCKER-USER` at every boot so published container ports accept only the LAN, the VPN and Docker bridges, and drop everything arriving on the physical NIC (`ens18`; change it if your interface differs).

```bash
sudo cp host/systemd/homelab-lockdown.service /etc/systemd/system/
sudo systemctl enable --now homelab-lockdown
sudo iptables -S DOCKER-USER   # verify: ends with "-i ens18 -j DROP"
```

Re-check `DOCKER-USER` after any Docker or kernel upgrade.

### Cloudflare Tunnel service

`cloudflared` runs as a systemd service with the tunnel credentials in `/etc/cloudflared/`. A drop-in ([`host/systemd/cloudflared-override.conf`](host/systemd/cloudflared-override.conf), installed as `/etc/systemd/system/cloudflared.service.d/override.conf`) raises the start timeout and starts it after Docker, so NPM is up before the first request arrives. Without the ordering, requests right after boot fail with "connection reset" on port 80.

### NetBird and AdGuard Home

NetBird (mesh VPN, `100.95.0.0/16`) and AdGuard Home (`/opt/AdGuardHome`, its own systemd unit) are installed on the host. AdGuard listens on the NetBird address and the LAN.

### Daily check

[`host/homelab-check.sh`](host/homelab-check.sh) runs from cron without sudo and logs to `~/bin/homelab-check.log`. It checks pending updates, ufw, `homelab-lockdown`, container and tunnel health, and that both data drives are mounted.

```bash
mkdir -p ~/bin && cp host/homelab-check.sh ~/bin/ && chmod +x ~/bin/homelab-check.sh
(crontab -l 2>/dev/null; echo '15 8 * * * /home/dhruv/bin/homelab-check.sh >/dev/null 2>&1') | crontab -
```

---

## Intranet services

This repository is built with internal services in mind. Use Nginx Proxy Manager and AdGuard Home to make the stack accessible on your LAN.

### Nginx Proxy Manager (NPM)

1. Deploy the `proxymanager` stack.
2. Open NPM at `http://<host>:81`.
3. Add a Proxy Host:
   - Domain Names: `service.local.example`
   - Scheme: `http`
   - Forward Hostname: `container_name` or host IP
   - Forward Port: service port (for example `80` or `3000`)
   - Enable Websockets if needed.
4. Optionally use SSL with a self-signed certificate for LAN-only traffic.

### AdGuard Home DNS rewrites

Add DNS rewrites so internal hostnames resolve to local IPs.

Example mappings:

- `nextcloud.local.example` → `192.168.1.10`
- `forgejo.local.example` → `192.168.1.11`
- `vaultwarden.local.example` → `192.168.1.12`

Make sure your LAN clients use AdGuard Home as their DNS resolver.

---

## Cloudflare / public access

Public traffic flows **Cloudflare → Cloudflare Tunnel → Nginx Proxy Manager (port 80) → container**. Cloudflare terminates TLS at its edge, so the NPM proxy hosts use plain HTTP and need no certificates.

### Step 1: Add a Proxy Host in Nginx Proxy Manager

1. Open NPM and go to **Proxy Hosts** → **Add Proxy Host**.
2. Configure:
   - Domain Names: `<subdomain.your-domain.com>`
   - Scheme: `http`
   - Forward Hostname: the **container name** (NPM shares the `homelab` network), e.g. `jellyfin`
   - Forward Port: the **container's internal port**, not the host port (e.g. Kavita is `5000`, not `5001`)
   - Websockets: `ON`, Block Common Exploits: `ON`
3. Leave the SSL tab empty and save.

### Step 2: Publish the hostname on the tunnel

**Dashboard-managed tunnel** (the tunnel's config lives in Cloudflare; this is what the live homelab uses):

1. Open Cloudflare **Zero Trust** → **Networks** → **Tunnels** → your tunnel → **Public Hostname** → **Add a public hostname**.
2. Set the subdomain and domain, Type `HTTP`, URL `localhost:80`.
3. Save. Cloudflare creates the DNS record automatically.

In this mode `/etc/cloudflared/config.yml` ingress rules are **ignored**; only the dashboard list counts, and any other hostname gets a Cloudflare 404. `cloudflared tunnel route dns` creates the DNS record but not the public hostname, so it is not enough on its own.

**Locally-managed tunnel** (alternative): add the hostname to `/etc/cloudflared/config.yml` before the catch-all, route DNS, and restart:

```yaml
ingress:
  - hostname: <subdomain.your-domain.com>
    service: http://localhost:80
  - service: http_status:404
```

```bash
cloudflared tunnel route dns <tunnel-name> <subdomain.your-domain.com>
sudo systemctl restart cloudflared
```

### What to expose

Expose user-facing apps only. Keep admin tools (Portainer, the *arr apps, qBittorrent, Filebrowser, Scrutiny, Beszel, the NPM admin UI) LAN-only and reach them remotely through the VPN (Netbird).

---

## Security and secrets

- Use `.env` for secrets and do not commit it.
- See `SECURITY.md` for guidance on what belongs in repo files and what should stay private.
- Prefer environment variables or Docker secrets for production.

---

## Notes

- Paths such as `${MEDIA_DIR}`, `${NEXTCLOUD_DATA_DIR}` and `${KAVITA_BOOKS_DIR}` are configurable in `.env`.
- The repo is structured so each service can be deployed independently.
- If you want a smaller subset, deploy only the folders you need.
- **Root-owned folders:** Docker creates missing bind-mount folders as `root`. Images that run as a non-root user (e.g. Jellyseerr, Vikunja) then crash with `EACCES`/`permission denied`. Fix it once with
  `docker run --rm -v <host-folder>:/c alpine chown 1000:1000 /c` (use your `PUID:PGID`) and restart the container.
- **Beszel agent:** add the host in Beszel (**Add System**, port `45876`), copy the public key and token into `BESZEL_AGENT_KEY` / `BESZEL_AGENT_TOKEN`, then `cd beszel && docker compose up -d`. Extra data drives are configured with the `*_DRIVE_*` variables.
