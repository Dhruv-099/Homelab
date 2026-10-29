import os, asyncio, html, time, httpx
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI

import alertdb

# --- Configuration ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_API_BASE = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org")
SCRUTINY_URL = os.getenv("SCRUTINY_URL", "http://scrutiny:8080")
DEADMAN_HOURS = float(os.getenv("DEADMAN_HOURS", 12))  # alert if Scrutiny has had no SMART report for this long
BESZEL_URL = os.getenv("BESZEL_URL", "http://beszel:8090")
BESZEL_EMAIL = os.getenv("BESZEL_EMAIL")
BESZEL_PASSWORD = os.getenv("BESZEL_PASSWORD")
BESZEL_CHECK_INTERVAL = int(os.getenv("BESZEL_CHECK_INTERVAL", 21600))  # 6 Hours
DISK_USAGE_THRESHOLD = float(os.getenv("DISK_USAGE_THRESHOLD", 85))  # alert if disk usage exceeds this %
# Send a short summary after every check, even when everything is fine (heartbeat)
SEND_OK_SUMMARY = os.getenv("SEND_OK_SUMMARY", "true").lower() == "true"
ROOT_DISK_LABEL = os.getenv("ROOT_DISK_LABEL", "Root")

# Items already alerted on, so each problem is reported once until it recovers
alerted_containers: set[str] = set()
alerted_disks: set[str] = set()
scrutiny_stale = False

async def telegram_post(message: str):
    # message is HTML; escape any dynamic text with html.escape before passing it in
    # Raises on failure so the delivery loop can keep the alert queued and retry
    url = f"{TELEGRAM_API_BASE}/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        })
        if resp.status_code != 200:
            raise RuntimeError(f"Telegram {resp.status_code}: {resp.text[:200]}")

async def send_telegram(message: str, ttl: int | None = None, source: str = "beszel"):
    # Queue the alert; delivery_loop sends it and retries until Telegram accepts it
    await asyncio.to_thread(alertdb.enqueue, source, message, "", ttl)

def format_age(seconds: int) -> str:
    if seconds < 3600:
        return f"{seconds // 60}m"
    hours, minutes = divmod(seconds // 60, 60)
    return f"{hours}h {minutes}m" if hours < 48 else f"{hours // 24}d"

async def delivery_loop():
    last_purge = 0.0
    while True:
        try:
            await asyncio.to_thread(alertdb.expire_old)
            for row in await asyncio.to_thread(alertdb.due):
                message = row["message"]
                late = int(time.time()) - row["received_at"]
                if late > 120:
                    message += f"\n\n<i>(delayed {format_age(late)})</i>"
                try:
                    await telegram_post(message)
                except Exception as e:
                    # str(e) can be empty for timeouts; never let the bot token reach the DB or logs
                    err = (f"{type(e).__name__}: {e}").replace(str(TELEGRAM_TOKEN), "<token>")
                    await asyncio.to_thread(alertdb.mark_failed, row["id"], err)
                    print(f"Delivery of alert #{row['id']} ({row['source']}) failed, attempt {row['attempts'] + 1}: {err}")
                    break  # Telegram is likely down; retry on the next tick instead of hammering it
                await asyncio.to_thread(alertdb.mark_delivered, row["id"])
                print(f"Delivered alert #{row['id']} ({row['source']})")
            if time.time() - last_purge > 86400:
                await asyncio.to_thread(alertdb.purge)
                last_purge = time.time()
        except Exception as e:
            print(f"Delivery loop error: {e}")
        await asyncio.sleep(15)

async def scrutiny_deadman_loop():
    # The Proxmox cron collector can die silently; warn when Scrutiny stops receiving SMART reports
    global scrutiny_stale
    while True:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{SCRUTINY_URL}/api/summary")
                resp.raise_for_status()
            summary = resp.json().get("data", {}).get("summary", {})
            dates = [datetime.fromisoformat(v["smart"]["collector_date"])
                     for v in summary.values() if (v.get("smart") or {}).get("collector_date")]
            if dates:
                age_h = (datetime.now(timezone.utc) - max(dates)).total_seconds() / 3600
                if age_h > DEADMAN_HOURS and not scrutiny_stale:
                    scrutiny_stale = True
                    await send_telegram(
                        f"<b>Drive Health Alert — no SMART data</b>\n"
                        f"Scrutiny's last report was <code>{age_h:.1f}h</code> ago. "
                        f"The collector cron job on Proxmox may have stopped.",
                        source="scrutiny")
                elif age_h <= DEADMAN_HOURS and scrutiny_stale:
                    scrutiny_stale = False
                    await send_telegram("<b>Drive Health — SMART reports are arriving again</b>", source="scrutiny")
                print(f"Scrutiny dead-man check OK — last report {age_h:.1f}h ago")
        except Exception as e:
            # Scrutiny being down is already covered by Beszel's container check
            print(f"Scrutiny dead-man check error: {e}")
        await asyncio.sleep(1800)

async def get_beszel_token():
    # Beszel accounts can live in either collection depending on how they were created
    async with httpx.AsyncClient() as client:
        for collection in ("_superusers", "users"):
            resp = await client.post(
                f"{BESZEL_URL}/api/collections/{collection}/auth-with-password",
                json={"identity": BESZEL_EMAIL, "password": BESZEL_PASSWORD}
            )
            if resp.status_code == 200:
                return resp.json().get("token")
        resp.raise_for_status()

async def beszel_health_check_loop():
    while True:
        try:
            token = await get_beszel_token()
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient() as client:

                # Container check
                resp = await client.get(
                    f"{BESZEL_URL}/api/collections/containers/records",
                    headers=headers
                )
                resp.raise_for_status()
                containers = resp.json().get("items", [])
                down = {c.get("name") or "unknown" for c in containers
                        if c.get("status") in ["down", "unhealthy", "degraded"]}
                newly_down = down - alerted_containers
                recovered = alerted_containers - down
                if newly_down:
                    names = "\n• ".join(html.escape(n) for n in sorted(newly_down))
                    await send_telegram(f"<b>Homelab Alert — Containers Down:</b>\n• {names}")
                if recovered:
                    names = "\n• ".join(html.escape(n) for n in sorted(recovered))
                    await send_telegram(f"<b>Homelab — Containers Recovered:</b>\n• {names}")
                alerted_containers.clear()
                alerted_containers.update(down)
                if not down:
                    print("Container check OK — all up")

                # Disk check
                resp = await client.get(
                    f"{BESZEL_URL}/api/collections/systems/records",
                    headers=headers
                )
                resp.raise_for_status()
                systems = resp.json().get("items", [])
                disk_lines = []
                for system in systems:
                    name = system.get("name") or "unknown"
                    info = system.get("info", {})
                    # Root disk ("dp") plus any extra drives mounted into the agent ("efs")
                    # Prefix with the system name only when Beszel monitors more than one system
                    prefix = f"{name}/" if len(systems) > 1 else ""
                    disks = {f"{prefix}{ROOT_DISK_LABEL}": info.get("dp", 0)}
                    for drive, pct in (info.get("efs") or {}).items():
                        disks[f"{prefix}{drive}"] = pct
                    for disk, disk_pct in disks.items():
                        disk_lines.append(f"{html.escape(disk)}: <code>{disk_pct:.1f}%</code>")
                        if disk_pct >= DISK_USAGE_THRESHOLD:
                            if disk not in alerted_disks:
                                alerted_disks.add(disk)
                                await send_telegram(
                                    f"<b>Disk Alert — {html.escape(disk)}</b>\n"
                                    f"Usage at <code>{disk_pct:.1f}%</code> — consider cleaning up!"
                                )
                        else:
                            if disk in alerted_disks:
                                alerted_disks.discard(disk)
                                await send_telegram(
                                    f"<b>Disk Recovered — {html.escape(disk)}</b>\n"
                                    f"Usage back to <code>{disk_pct:.1f}%</code>"
                                )
                            print(f"Disk check OK — {disk} at {disk_pct:.1f}%")

                if SEND_OK_SUMMARY:
                    status = "All containers up" if not down else f"{len(down)} container(s) down"
                    await send_telegram(
                        f"<b>Homelab Check</b>\n"
                        f"{status} ({len(containers)} tracked)\n"
                        f"Disks — " + ", ".join(disk_lines),
                        ttl=3600  # a stale "all OK" summary is worse than none
                    )

        except Exception as e:
            print(f"Health Check Error: {e}")
            await send_telegram(f"<b>Notifier Error:</b>\n<code>{html.escape(str(e))}</code>")

        await asyncio.sleep(BESZEL_CHECK_INTERVAL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    alertdb.init()
    tasks = [asyncio.create_task(c()) for c in
             (beszel_health_check_loop, delivery_loop, scrutiny_deadman_loop)]
    yield
    for task in tasks:
        task.cancel()

app = FastAPI(lifespan=lifespan)

# Webhooks (Watchtower, Scrutiny) are received by inbox.py, which writes to the shared alert DB

@app.get("/health")
async def health():
    pending = await asyncio.to_thread(lambda: len(alertdb.due(limit=1000)))
    return {"status": "ok", "pending_alerts": pending}
