import os, asyncio, httpx
from fastapi import FastAPI, Request

# --- Configuration ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BESZEL_URL = os.getenv("BESZEL_URL", "http://192.168.1.4:8232")
BESZEL_EMAIL = os.getenv("BESZEL_EMAIL")
BESZEL_PASSWORD = os.getenv("BESZEL_PASSWORD")
BESZEL_CHECK_INTERVAL = 21600  # 6 Hours

app = FastAPI()

async def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        })

@app.post("/watchtower")
async def watchtower_webhook(request: Request):
    raw_body = await request.body()
    print(f"Watchtower raw payload: {raw_body}")
    try:
        data = await request.json()
        report = data.get('report', data.get('message', data.get('body', 'Updates completed.')))
    except Exception:
        report = raw_body.decode('utf-8', errors='replace') or 'Updates completed (empty payload).'
    msg = f" *Nightly Update Report*\n\n{report}"
    await send_telegram(msg)
    return {"status": "ok"}

async def get_beszel_token():
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BESZEL_URL}/api/collections/_superusers/auth-with-password",
            json={"identity": BESZEL_EMAIL, "password": BESZEL_PASSWORD}
        )
        resp.raise_for_status()
        return resp.json().get("token")

DISK_USAGE_THRESHOLD = 85  # alert if disk usage exceeds this %

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
                containers = resp.json().get("items", [])
                down = [c.get("name") for c in containers
                        if c.get("status") in ["down", "unhealthy", "degraded"]]
                if down:
                    names = "\n• ".join(down)
                    await send_telegram(f"*Homelab Alert — Containers Down:*\n• {names}")
                else:
                    print("Container check OK — all up")

                # Disk check 
                resp = await client.get(
                    f"{BESZEL_URL}/api/collections/systems/records",
                    headers=headers
                )
                systems = resp.json().get("items", [])
                for system in systems:
                    name = system.get("name")
                    info = system.get("info", {})
                    disk_pct = info.get("dp", 0)
                    if disk_pct >= DISK_USAGE_THRESHOLD:
                        await send_telegram(
                            f"*Disk Alert — {name}*\n"
                            f"Usage at `{disk_pct:.1f}%` — consider cleaning up!"
                        )
                    else:
                        print(f"Disk check OK — {name} at {disk_pct:.1f}%")

        except Exception as e:
            print(f"Health Check Error: {e}")
            await send_telegram(f"*Notifier Error:*\n`{str(e)}`")

        await asyncio.sleep(BESZEL_CHECK_INTERVAL)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(beszel_health_check_loop())