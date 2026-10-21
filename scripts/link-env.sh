#!/usr/bin/env bash
# Symlink the root .env into every stack folder so `docker compose up -d`
# picks it up (Compose only reads .env from the project directory).
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -f "$repo_root/.env" ]]; then
  echo "No .env at repo root. Run: cp .env.example .env" >&2
  exit 1
fi

for compose in "$repo_root"/*/docker-compose.yml; do
  dir="$(dirname "$compose")"
  target="$dir/.env"
  if [[ -e "$target" && ! -L "$target" ]]; then
    echo "skip: $target is a real file, not overwriting" >&2
    continue
  fi
  ln -sfn ../.env "$target"
  echo "linked: ${dir#"$repo_root"/}/.env -> ../.env"
done
