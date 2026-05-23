# Reproducible Homelab Guide

This document shows how to reproduce the homelab stack from this repository on a compatible Linux host.

> This is the implementation guide. The main `README.md` is a proof-of-work overview of the homelab architecture and services.

---

## Prerequisites

- A Linux host with Docker and Docker Compose v2 installed.
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
docker compose -f nextcloud/docker-compose.yml -f forgejo/docker-compose.yml up -d
```

This is useful when services are separated by directories but you want to start them from the repo root.

### Check service health

```bash
docker compose ps
docker compose logs -f <service>
```

---

## Recommended deployment order

1. `proxymanager` — Nginx Proxy Manager for routing
2. `nextcloud` — storage and collaboration
3. `forgejo` — Git hosting
4. `vaultwarden` — passwords and secrets management
5. `immich-setup` — photo management
6. `arr`, `jellyfin`, `navidrome` — media services
7. `scrutiny` — drive monitoring

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

Use Cloudflare DNS, Nginx Proxy Manager, and Cloudflare Tunnel to expose services securely.

### Step 1: Add a DNS record in Cloudflare

1. Open the Cloudflare dashboard and go to **DNS** → **Add record**.
2. Set:
   - Type: `CNAME`
   - Name: `<subdomain>`
   - Target / Content: `<cloudflared-tunnel-hostname>`
   - Proxy: `ON` (orange cloud)

### Step 2: Add a Proxy Host in Nginx Proxy Manager

1. Open NPM and go to **Proxy Hosts** → **Add Proxy Host**.
2. Configure:
   - Domain Names: `<subdomain.your-domain.com>`
   - Scheme: `http`
   - Forward Hostname: `<container_or_host_ip>`
   - Forward Port: `<service_port>`
   - Websockets: `ON` if the service requires them
3. In the SSL tab:
   - Request a new SSL certificate
   - Choose DNS Challenge
   - Use your Cloudflare API token
   - Enable **Force SSL**
4. Save the proxy host.

### Step 3: Update Cloudflare Tunnel configuration

Edit `/etc/cloudflared/config.yml` and add the new hostname before the catch-all rule under `ingress:`.

```yaml
ingress:
  - hostname: <subdomain.your-domain.com>
    service: http://localhost:<service_port>
    originRequest:
      noTLSVerify: true
    httpHostHeader: <subdomain.your-domain.com>

  - service: http_status:404
```

Then restart Cloudflared:

```bash
sudo systemctl restart cloudflared
```

---

## Security and secrets

- Use `.env` for secrets and do not commit it.
- See `SECURITY.md` for guidance on what belongs in repo files and what should stay private.
- Prefer environment variables or Docker secrets for production.

---

## Notes

- Paths such as `${MEDIA_DIR}` and `${NEXTCLOUD_DATA_DIR}` are configurable in `.env`.
- The repo is structured so each service can be deployed independently.
- If you want a smaller subset, deploy only the folders you need.
