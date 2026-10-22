**Security & Privacy for this repository**

- Never commit real secrets (passwords, tokens, private domain names) into the repository.
- Use the provided `.env.example` as a template. Copy it to `.env` and fill in real secrets locally.
- `.env` is listed in `.gitignore` and will not be committed.
- For production use consider Docker secrets or an external secrets manager instead of `.env` files.
- Do not commit persistent data directories (database files, uploaded media). They are ignored by `.gitignore`.
- Replace host-specific absolute paths (e.g., `/mnt/...`) with env variables when sharing these files.

How to use:

1. Copy `.env.example` to `.env`:

```bash
cp .env.example .env
# Edit .env and add real values
```

2. Link it into each stack and start the services you need — see `REPRODUCIBLE.md`:

```bash
./scripts/link-env.sh
cd <service> && docker compose up -d
```

## Known high-privilege mounts

- **Filebrowser** (FileBrowser Quantum) mounts the two data drives read-write, not the whole host, so a compromised login can't reach `~/.ssh` or the stack `.env` files. Keep it LAN/VPN-only (never expose it through Cloudflare Tunnel) and change the generated admin password at first login. The original File Browser project was archived on 2026-09-01 and gets no security fixes; don't switch back to the `filebrowser/filebrowser` image.
- **Portainer** and **Watchtower** mount `/var/run/docker.sock`, which is effectively root on the host.
- **Scrutiny** runs privileged with `/dev` mounted for S.M.A.R.T. access.
