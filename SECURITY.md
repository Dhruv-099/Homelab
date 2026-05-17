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

2. Start the stack with docker-compose:

```bash
docker compose up -d
```

If you want me to further redact or generalize additional files, tell me which ones to prioritize.
