import re
import json
import time
import requests

# ---------- CONFIG (এইখানে তোমার তথ্য বসাও) ----------
TELEGRAM_BOT_TOKEN = "8841879665:AAH8bUpBqEZ-MTbp9jEzbTIIg9LlHLMEcCc"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"
CHECK_INTERVAL_SECONDS = 60  # কত সেকেন্ড পরপর চেক করবে

APUCASH_URL = "https://apucash.com"
SEEN_IDS_FILE = "seen_ids.json"
# -------------------------------------------------------


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
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    resp = requests.get(APUCASH_URL, headers=headers, timeout=15)
    resp.raise_for_status()

    # HTML এর ভিতর থেকে data-page="app" script ট্যাগের JSON বের করা
    match = re.search(
        r'<script data-page="app" type="application/json">(.*?)</script>',
        resp.text,
        re.DOTALL,
    )
    if not match:
        print("JSON ব্লক পাওয়া যায়নি, সাইট structure পরিবর্তন হয়ে থাকতে পারে।")
        return []

    data = json.loads(match.group(1))
    winners = data.get("props", {}).get("recentWinners", [])
    return winners


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, data=payload, timeout=15)
    if r.status_code != 200:
        print("Telegram পাঠাতে সমস্যা:", r.text)


def format_message(winner):
    return (
        f"🚀 <b>NEW LIVE LEAD</b>\n"
        f"🌐 <b>Website:</b> Apucash\n"
        f"🎯 <b>Offer:</b> {winner.get('source')}\n"
        f"💰 <b>Reward:</b> {winner.get('coins')} coins\n"
        f"👤 <b>User:</b> {winner.get('name')}\n"
        f"⏰ <b>Time:</b> {winner.get('tooltip', {}).get('time')}"
    )


def main():
    print("Apucash bot শুরু হয়েছে...")
    seen_ids = load_seen_ids()

    while True:
        try:
            winners = fetch_recent_winners()
            new_count = 0

            for winner in winners:
                wid = winner.get("id")
                if wid not in seen_ids:
                    message = format_message(winner)
                    send_telegram_message(message)
                    seen_ids.add(wid)
                    new_count += 1
                    time.sleep(1)  # Telegram rate limit এড়াতে

            if new_count:
                save_seen_ids(seen_ids)
                print(f"{new_count} টা নতুন অফার পাঠানো হয়েছে।")
            else:
                print("নতুন কিছু নেই।")

        except Exception as e:
            print("Error:", e)

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
