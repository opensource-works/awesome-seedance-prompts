#!/usr/bin/env python3
"""
Hydrate the X post URLs in scripts/urls.txt into data/posts.json.

Every field in the dataset comes straight from the public post — we never
invent a prompt, a caption or an author. Posts without a playable video are
dropped, because the whole point of this index is that you can watch the clip.

    python3 scripts/harvest.py            # refresh everything
    python3 scripts/harvest.py --cache    # reuse .cache, only fetch new URLs
"""
import json, os, re, sys, time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, ".cache")
URLS = os.path.join(ROOT, "scripts", "urls.txt")
OUT = os.path.join(ROOT, "data", "posts.json")

API = "https://api.fxtwitter.com/i/status/{}"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"


# --------------------------------------------------------------------------- fetch

def status_id(url):
    m = re.search(r"/status/(\d+)", url)
    return m.group(1) if m else None


def fetch(sid, use_cache=True):
    path = os.path.join(CACHE, f"{sid}.json")
    if use_cache and os.path.exists(path) and os.path.getsize(path) > 200:
        return json.load(open(path))
    for attempt in range(3):
        try:
            req = urllib.request.Request(API.format(sid), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
            if data.get("code") != 200:
                return None
            os.makedirs(CACHE, exist_ok=True)
            json.dump(data["tweet"], open(path, "w"), ensure_ascii=False)
            return data["tweet"]
        except Exception as e:
            if attempt == 2:
                print(f"  ! {sid}: {e}", file=sys.stderr)
            time.sleep(1.5 * (attempt + 1))
    return None


# --------------------------------------------------------------------------- parse

# Ordered: the first rule that matches wins, so the specific ones come first.
CATEGORY_RULES = [
    ("Model Comparisons", r"\b(same prompt on|side by side|blind(ly)? (test|judged)|showdown|destroys|outperform)\b"
                          r"|\bvs\.?\b.*\b(sora|veo|kling|runway|grok|imagine|firefly)\b"
                          r"|\b(sora|veo|kling|runway|grok|firefly)\b.*\bvs\.?\b"),
    ("Launch & Announcements", r"\b(now live|is live|global launch|officially (announced|launched)|has been officially|"
                               r"coming soon|just dropped|just announced|expected to (launch|be released)|"
                               r"unlimited .* on higgsfield|new feature)\b"),
    ("Music & Dance", r"\b(dance|dancing|k-?pop|choreograph|music video|\bmv\b|movement sheet|ballet)\b"),
    ("Anime & Animation", r"\b(anime|manga|sakuga|cartoon|2d animation|animated (scene|feature|film)|pixar|"
                          r"doodle|tom and jerry|stop-?motion)\b"),
    ("Ads, UGC & Product", r"\b(ugc|advert|commercial|product (photo|shot|demo|video)|brand|dtc|unboxing|"
                           r"e-?commerce|tiktok shop|influencer vlog|\bads?\b)\b"),
    ("Action & VFX", r"\b(fight|fighting|action sequence|battle|combat|explosion|vfx|parkour|chase|escape|"
                     r"katana|war\b|supernova|summoning)\b"),
    ("Prompting & Workflow", r"\b(character (reference )?sheet|consistency|workflow|step[- ]by[- ]step|guide|"
                             r"cheat sheet|how to|technique|json prompt|voice id|depth (map|anything)|blender|"
                             r"previs|storyboard|prompt (collection|library|structure))\b"),
    ("Cinematic & Film", r"\b(cinematic|short film|film|movie|scene|one shot|slice-of-life|documentary|trailer)\b"),
]

# Marker forms seen in the wild: "Prompt:", "Prompt ⬇️", a bare "Prompt" line,
# "Here's the prompt 👇:", "提示词：" …
PROMPT_MARKERS = [
    r"here'?s the (?:exact )?prompt\s*[👇⬇️]*\s*[:：]?",
    r"(?:seedance[^\n]{0,24})?(?:production |video[_ ]|image |exact |base |example )?prompt(?:\s*structure)?\s*(?:used)?\s*[:：]",
    r"^\s*(?:seedance\s*[\d.]*\s*)?prompt\s*[⬇️👇]*\s*$",
    r"提示词\s*[:：]",
]
# "Prompt below", "prompts in comments" — the prompt exists but lives in a reply.
IN_THREAD = re.compile(
    r"\bprompts?\s*(?:is|are|in|below|👇|⬇️)?\s*"
    r"(?:below|in (?:the )?(?:first )?comments?|in (?:the )?(?:thread|replies?)|👇|⬇️)\b", re.I)


def extract_prompt(text):
    """Longest plausible prompt body following a prompt marker, else None."""
    best = None
    for pat in PROMPT_MARKERS:
        for m in re.finditer(pat, text, re.I | re.M):
            tail = text[m.end():].strip()
            tail = re.sub(r"\s*https://t\.co/\w+\s*$", "", tail).strip()
            if len(tail) < 80:
                continue
            if best is None or len(tail) > len(best):
                best = tail
    return best


def detect_model(text):
    t = text.lower()
    if re.search(r"seedance\s*2[.·]5|seedance\s*2\.5", t):
        return "Seedance 2.5"
    if re.search(r"seedance\s*2[.·]0|seedance\s*2\b|seedance2", t):
        return "Seedance 2.0"
    return "Seedance"


def categorize(text):
    for name, pat in CATEGORY_RULES:
        if re.search(pat, text, re.I):
            return name
    return "Showcase"


def make_title(text):
    for line in text.split("\n"):
        line = re.sub(r"https?://\S+", "", line).strip()
        line = re.sub(r"\s+", " ", line).strip(" .:-—>")
        if len(line) >= 14:
            return (line[:92].rsplit(" ", 1)[0] + "…") if len(line) > 95 else line
    flat = re.sub(r"\s+", " ", re.sub(r"https?://\S+", "", text)).strip()
    return flat[:92] or "Untitled"


def build(tweet):
    videos = (tweet.get("media") or {}).get("videos") or []
    text = (tweet.get("text") or "").strip()
    if not videos or "seedance" not in text.lower():
        return None
    v = max(videos, key=lambda x: (x.get("width") or 0) * (x.get("height") or 0))
    a = tweet["author"]
    dt = datetime.strptime(tweet["created_at"], "%a %b %d %H:%M:%S %z %Y").astimezone(timezone.utc)
    prompt = extract_prompt(text)
    return {
        "id": tweet["id"],
        "url": f"https://x.com/{a['screen_name']}/status/{tweet['id']}",
        "title": make_title(text),
        "text": text,
        "prompt": prompt,
        "prompt_in_thread": bool(not prompt and IN_THREAD.search(text)),
        "model": detect_model(text),
        "category": categorize(text),
        "date": dt.strftime("%Y-%m-%d"),
        "author": {
            "name": a["name"],
            "handle": a["screen_name"],
            "url": f"https://x.com/{a['screen_name']}",
            "avatar": a.get("avatar_url"),
        },
        "video": {
            "url": v["url"],
            "thumbnail": v.get("thumbnail_url"),
            "width": v.get("width"),
            "height": v.get("height"),
            "duration": round(v.get("duration") or 0, 2),
            # X publishes several encodes of the same clip; keeping them lets
            # scripts/mirror.py pick a sane one instead of re-encoding.
            "formats": [f for f in (v.get("formats") or []) if f.get("container") == "mp4"],
        },
        "stats": {
            "views": tweet.get("views") or 0,
            "likes": tweet.get("likes") or 0,
            "retweets": tweet.get("retweets") or 0,
        },
    }


# --------------------------------------------------------------------------- main

def main():
    use_cache = "--cache" in sys.argv
    urls = [l.strip() for l in open(URLS) if l.strip() and not l.startswith("#")]
    ids = list(dict.fromkeys(filter(None, (status_id(u) for u in urls))))
    print(f"hydrating {len(ids)} posts (cache={'on' if use_cache else 'off'})")

    with ThreadPoolExecutor(max_workers=6) as ex:
        tweets = list(ex.map(lambda s: fetch(s, use_cache), ids))

    posts = [p for p in (build(t) for t in tweets if t) if p]
    posts.sort(key=lambda p: -p["stats"]["views"])

    # Manual overrides let a human fix a bad auto-title or category without
    # hand-editing generated data. See scripts/overrides.json.
    ov_path = os.path.join(ROOT, "scripts", "overrides.json")
    if os.path.exists(ov_path):
        ov = json.load(open(ov_path))
        for p in posts:
            p.update(ov.get(p["id"], {}))

    json.dump(posts, open(OUT, "w"), indent=2, ensure_ascii=False)
    dropped = len(ids) - len(posts)
    with_prompt = sum(1 for p in posts if p["prompt"])
    print(f"wrote {len(posts)} posts to data/posts.json "
          f"({with_prompt} with an inline prompt, {dropped} dropped: no video or not Seedance)")


if __name__ == "__main__":
    main()
