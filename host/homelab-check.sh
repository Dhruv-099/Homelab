#!/usr/bin/env bash
# Daily homelab check: eMudhra advisory exposure, updates, firewall, containers, tunnel.
# Runs as a normal user (no sudo). Output is appended to ~/bin/homelab-check.log.
set -u
LOG="$HOME/bin/homelab-check.log"
HOST=dv-g3b-emudhra.we-have-a-problem.com
bad=0

{
  echo "=== $(date '+%Y-%m-%d %H:%M %Z') ==="

  # 1. Advisory: a TLS verification error means the bad chain is NOT trusted (good).
  out=$(curl -sS -m 15 -o /dev/null "https://$HOST" 2>&1); rc=$?
  if [ "$rc" = 60 ]; then echo "[ok]   curl rejects eMudhra test host"
  elif [ "$rc" = 0 ]; then echo "[FAIL] curl TRUSTS the compromised chain"; bad=1
  else echo "[warn] curl test inconclusive (exit $rc: ${out%%$'\n'*})"; fi
  if command -v node >/dev/null; then
    n=$(node -e "require('https').get('https://$HOST',r=>console.log('TRUSTED')).on('error',e=>console.log('rejected:'+e.code))" 2>&1)
    case "$n" in rejected:EAI_AGAIN*|rejected:ETIMEDOUT*) echo "[warn] node test inconclusive ($n)";;
      rejected:*) echo "[ok]   node rejects ($n)";; *) echo "[FAIL] node TRUSTS the chain"; bad=1;; esac
  fi

  # 2. Pending updates
  up=$(apt list --upgradable 2>/dev/null | tail -n +2 | wc -l)
  echo "[info] apt upgradable packages: $up"
  [ -f /var/run/reboot-required ] && echo "[warn] reboot required"

  # 3. Firewall (no root: check the service and the persistent unit)
  systemctl is-active --quiet ufw && echo "[ok]   ufw active" || { echo "[FAIL] ufw not active"; bad=1; }
  # oneshot unit that reapplies DOCKER-USER rules at boot: only needs to be enabled
  systemctl is-enabled --quiet homelab-lockdown && echo "[ok]   homelab-lockdown enabled" || { echo "[FAIL] homelab-lockdown not enabled"; bad=1; }

  # 4. Containers
  down=$(docker ps -a --filter status=exited --filter status=restarting --format '{{.Names}}' | paste -sd, -)
  [ -z "$down" ] && echo "[ok]   all containers running ($(docker ps -q | wc -l))" || { echo "[FAIL] containers down: $down"; bad=1; }
  unh=$(docker ps --filter health=unhealthy --format '{{.Names}}' | paste -sd, -)
  [ -n "$unh" ] && { echo "[FAIL] unhealthy: $unh"; bad=1; }

  # 5. Tunnel since last restart
  s=$(systemctl show cloudflared -p ActiveEnterTimestamp --value)
  w=$(journalctl -u cloudflared --since "$s" --no-pager 2>/dev/null | grep -E 'WRN|ERR' | grep -vE 'ICMP|ping_group_range|context canceled' | wc -l)
  r=$(journalctl -u cloudflared --since "$s" --no-pager 2>/dev/null | grep -c 'Registered tunnel')
  echo "[info] cloudflared since $s: $w warnings/errors, $r registrations (4 = steady)"
  [ "$r" -gt 8 ] && { echo "[warn] tunnel re-registering"; bad=1; }

  # 6. Disks mounted
  for m in /mnt/storage-931gb /mnt/sdb1; do mountpoint -q "$m" && echo "[ok]   $m mounted" || { echo "[FAIL] $m NOT mounted"; bad=1; }; done

  [ "$bad" = 0 ] && echo "RESULT: OK" || echo "RESULT: ATTENTION NEEDED"
} >> "$LOG" 2>&1
tail -n 25 "$LOG" | sed -n '/^=== /h;/^=== /!H;${x;p}'
exit "$bad"
