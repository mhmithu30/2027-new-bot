import os
import re
import json
import time
import threading
import requests
import socketio

# ---------- CONFIG ----------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
CHECK_INTERVAL_SECONDS = 60

APUCASH_URL = "https://apucash.com"
SEEN_IDS_FILE = "seen_ids.json"
PAIDCASH_SOCKET_URL = "https://servers.faucetify.io"

JJREWARD_URL = "https://www.jjreward.com/api/getWithdrawAndCompletedOffers"
JJREWARD_COOKIE = os.environ.get("JJREWARD_COOKIE")
JJREWARD_SEEN_FILE = "jjreward_seen_ids.json"
# -----------------------------


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    r = requests.post(url, data=payload, timeout=15)
    if r.status_code != 200:
        print("Telegram error:", r.text)


# ---------------- APUCASH (polling) ----------------
def load_seen_ids():
    try:
        with open(SEEN_IDS_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_seen_ids(seen_ids):
    with open(SEEN_IDS_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_recent_winners():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(APUCASH_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    match = re.search(
        r'<script data-page="app" type="application/json">(.*?)</script>',
        resp.text,
        re.DOTALL,
    )
    if not match:
        return []
    data = json.loads(match.group(1))
    return data.get("props", {}).get("recentWinners", [])


def format_apucash_message(winner):
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> Apucash\n"
        f"🎯 <b>Offer:</b> {winner.get('source')}\n"
        f"💰 <b>Reward:</b> {winner.get('coins')} coins\n"
        f"👤 <b>User:</b> {winner.get('name')}\n"
        f"⏰ <b>Time:</b> {winner.get('tooltip', {}).get('time')}"
    )


def run_apucash():
    print("Apucash bot শুরু হয়েছে...")
    seen_ids = load_seen_ids()
    while True:
        try:
            winners = fetch_recent_winners()
            new_count = 0
            for winner in winners:
                wid = winner.get("id")
                if wid in seen_ids:
                    continue

                seen_ids.add(wid)  # আগে চেক করা হয়ে গেছে, দ্বিতীয়বার আর দেখাবে না

                source = (winner.get("source") or "").lower()
                coins = winner.get("coins") or 0

                if "cpx research" in source or "theoremreach" in source:
                    continue
                if coins < 500:
                    continue

                send_telegram_message(format_apucash_message(winner))
                new_count += 1
                time.sleep(1)
            if new_count:
                save_seen_ids(seen_ids)
                print(f"Apucash: {new_count} টা নতুন অফার পাঠানো হয়েছে।")
        except Exception as e:
            print("Apucash Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- JJREWARD (polling with cookie) ----------------
def load_jjreward_seen():
    try:
        with open(JJREWARD_SEEN_FILE, "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_jjreward_seen(seen_ids):
    with open(JJREWARD_SEEN_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_jjreward_offers():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cookie": JJREWARD_COOKIE,
        "X-Requested-With": "XMLHttpRequest",
    }
    resp = requests.get(JJREWARD_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("completedOffers", [])


def format_jjreward_message(offer):
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> JJReward\n"
        f"🎯 <b>Offer:</b> {offer.get('offer_name')}\n"
        f"🧱 <b>Network:</b> {offer.get('partners')}\n"
        f"💰 <b>Reward:</b> {offer.get('reward')} JJ"
    )


def run_jjreward():
    print("JJReward bot শুরু হয়েছে...")
    seen_ids = load_jjreward_seen()
    while True:
        try:
            offers = fetch_jjreward_offers()
            new_count = 0
            for offer in offers:
                oid = offer.get("id")
                if oid in seen_ids:
                    continue
                seen_ids.add(oid)

                source = (offer.get("partners") or "").lower()
                reward = offer.get("reward") or 0

                if "cpx research" in source or "theoremreach" in source:
                    continue
                if reward < 500:
                    continue

                send_telegram_message(format_jjreward_message(offer))
                new_count += 1
                time.sleep(1)
            if new_count:
                save_jjreward_seen(seen_ids)
                print(f"JJReward: {new_count} টা নতুন অফার পাঠানো হয়েছে।")
        except Exception as e:
            print("JJReward Error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- PAIDCASH (socket.io live) ----------------
sio = socketio.Client()


@sio.event
def connect():
    print("PaidCash socket connected")


@sio.event
def disconnect():
    print("PaidCash disconnected, reconnecting...")


@sio.on("activityFeed")
def on_activity(data):
    if data.get("feedType") != "earn":
        return

    wall = (data.get("wall") or "").lower()
    coins = data.get("coins") or 0

    if "cpx research" in wall or "theoremreach" in wall:
        return
    if coins < 500:
        return

    if True:
        msg = (
            f"🚀 <b>NEW LIVE LEAD</b>\n"
            f"🌐 <b>Website:</b> PaidCash\n"
            f"🎯 <b>Offer:</b> {data.get('offername')}\n"
            f"🧱 <b>Network:</b> {data.get('wall')}\n"
            f"💰 <b>Reward:</b> {data.get('coins')} coins\n"
            f"👤 <b>User:</b> {data.get('username')}"
        )
        send_telegram_message(msg)
        print("PaidCash: Sent -", data.get("offername"))


def run_paidcash():
    while True:
        try:
            sio.connect(PAIDCASH_SOCKET_URL, transports=["websocket"])
            sio.wait()
        except Exception as e:
            print("PaidCash Error:", e)
            time.sleep(5)


# ---------------- MAIN ----------------
if __name__ == "__main__":
    t1 = threading.Thread(target=run_apucash, daemon=True)
    t1.start()

    t2 = threading.Thread(target=run_jjreward, daemon=True)
    t2.start()

    run_paidcash()  # main thread এ চলবে
