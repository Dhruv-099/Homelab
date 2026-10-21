import os, asyncio, html, httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request

# --- Configuration ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
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

async def send_telegram(message: str):
    # message is HTML; escape any dynamic text with html.escape before passing it in
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        })
        if resp.status_code != 200:
            print(f"Telegram send failed ({resp.status_code}): {resp.text}")

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
                        f"Disks — " + ", ".join(disk_lines)
                    )

        except Exception as e:
            print(f"Health Check Error: {e}")
            await send_telegram(f"<b>Notifier Error:</b>\n<code>{html.escape(str(e))}</code>")

        await asyncio.sleep(BESZEL_CHECK_INTERVAL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(beszel_health_check_loop())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

@app.post("/watchtower")
async def watchtower_webhook(request: Request):
    raw_body = await request.body()
    print(f"Watchtower raw payload: {raw_body}")
    try:
        data = await request.json()
        report = data.get('report', data.get('message', data.get('body', 'Updates completed.')))
    except Exception:
        report = raw_body.decode('utf-8', errors='replace') or 'Updates completed (empty payload).'
    msg = f"<b>Nightly Update Report</b>\n\n{html.escape(str(report))}"
    await send_telegram(msg)
    return {"status": "ok"}
