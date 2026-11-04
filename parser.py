import os, re, sys
import requests
from bs4 import BeautifulSoup
from cities import CITIES

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

CHANNELS = ["lpr1_treugolnik", "kupolrussia", "den_v_kadre"]

SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

COORD_RE = re.compile(r'(\d{1,2}[.,]\d{3,8})[\s,;]+([1-3]\d[.,]\d{3,8})')

KIND_RULES = [
    ("дрон", ["бпла", "беспилотник", "дрон", "герань", "ланцет", "fpv",
              "мавик", "орлан", "камикадзе", "шахед", "разведывательн"]),
    ("ракета", ["ракета", "ракет", "кинжал", "калибр", "искандер",
                "с-300", "с-400", "баллист", "крылат"]),
    ("событие", ["взрыв", "прилёт", "прилет", "детонация", "пожар", "обстрел"]),
]

def classify(text):
    low = text.lower()
    for kind, words in KIND_RULES:
        if any(w in low for w in words):
            return kind
    return "событие"

def extract_coords(text):
    for m in COORD_RE.finditer(text):
        try:
            lat = float(m.group(1).replace(",", "."))
            lon = float(m.group(2).replace(",", "."))
        except ValueError:
            continue
        if 40 <= lat <= 60 and 20 <= lon <= 45:
            return lat, lon
    return None, None

def extract_place(text):
    low = text.lower()
    best = None
    for name, (lat, lon) in CITIES.items():
        if name.lower() in low:
            if best is None or len(name) > len(best[0]):
                best = (name, lat, lon)
    return best

def parse_post(text):
    kind = classify(text)
    lat, lon = extract_coords(text)
    place = None
    conf = 0.3
    if lat is not None:
        conf = 0.9
    else:
        p = extract_place(text)
        if p:
            place, lat, lon = p
            conf = 0.5
    return {"kind": kind, "lat": lat, "lon": lon, "place": place, "confidence": conf}

def fetch_channel(channel):
    try:
        r = requests.get(f"https://t.me/s/{channel}", timeout=25,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
    except Exception as e:
        print(f"fetch failed {channel}: {e}", file=sys.stderr)
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for msg in soup.select(".tgme_widget_message"):
        pid = msg.get("data-post", "").split("/")[-1]
        if not pid.isdigit():
            continue
        tel = msg.select_one(".tgme_widget_message_date time")
        if not tel:
            continue
        tt = msg.select_one(".tgme_widget_message_text")
        text = tt.get_text(" ", strip=True) if tt else ""
        if len(text) < 5:
            continue
        out.append({"channel": channel, "post_id": int(pid),
                    "ts": tel["datetime"], "text": text})
    return out

def main():
    rows = []
    for ch in CHANNELS:
        posts = fetch_channel(ch)
        print(f"{ch}: {len(posts)} posts")
        for p in posts:
            parsed = parse_post(p["text"])
            rows.append({
                "channel": p["channel"],
                "post_id": p["post_id"],
                "ts": p["ts"],
                "text": p["text"][:2000],
                **parsed,
            })
    if not rows:
        return
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/events",
        headers={**SB_HEADERS, "Prefer": "resolution=ignore-duplicates,return=minimal"},
        json=rows,
    )
    print("insert:", r.status_code)
    if r.status_code not in (200, 201, 204):
        print(r.text, file=sys.stderr)

if __name__ == "__main__":
    import json
    rows = []
    for ch in CHANNELS:
        posts = fetch_channel(ch)
        print(f"{ch}: {len(posts)} posts")
        for p in posts:
            parsed = parse_post(p["text"])
            rows.append({
                "channel": p["channel"],
                "post_id": p["post_id"],
                "ts": p["ts"],
                "text": p["text"][:2000],
                **parsed,
            })
    
    # Сохраняем в файл data.json
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print("data.json saved")

    # В Supabase тоже попробуем отправить, но если упадет - не страшно
    if rows:
        try:
            r = requests.post(
                f"{SUPABASE_URL}/rest/v1/events",
                headers={**SB_HEADERS, "Prefer": "resolution=ignore-duplicates,return=minimal"},
                json=rows,
            )
            print("insert:", r.status_code)
        except Exception as e:
            print("Supabase error:", e)
