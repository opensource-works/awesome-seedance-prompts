#!/usr/bin/env python3
"""
Mirror every indexed clip to R2 so playback never depends on a twimg URL that
X may rotate, and build a short animated preview plus a sharp static poster
frame for each one.

For each post we take the largest variant X publishes whose SHORT side is
1080px or below — X's own encode, not a re-encode of it — plus a 3-second
silent WebP loop that the README can show inline (GitHub strips <video>, but
<img> survives), plus a single static WebP poster frame (up to 1280px wide,
never upscaled) for a sharp still image everywhere else.

    R2_ACCOUNT=... R2_KEY_ID=... R2_SECRET=... python3 scripts/mirror.py
    python3 scripts/mirror.py --dry-run       # report what's missing, upload nothing
    python3 scripts/mirror.py --force <post_id[,post_id...]>  # rebuild just these posts
    python3 scripts/mirror.py --force all                     # rebuild every post

Writes data/mirror.json: {post_id: {"mp4": url, "webp": url, "poster": url,
"width": w, "height": h}}. Objects already in the bucket are skipped (unless
named via --force-mp4), so re-runs are cheap.
"""
import json, os, re, subprocess, sys, tempfile
import concurrent.futures as cf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

BUCKET = os.environ.get("R2_BUCKET", "seadanse")
PUBLIC = os.environ.get("R2_PUBLIC_BASE", "https://pub-21846f909b8042c98ed40eb94282ba92.r2.dev")
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
MAX_HEIGHT = 1080  # cap applies to the SHORT side (min(width, height)), not raw height
DRY = "--dry-run" in sys.argv


def _force_arg():
    """Parse --force <post_id[,post_id...]|all> from argv. Returns the raw
    value (resolved against the post list in main(), since 'all' needs it)
    or None if the flag wasn't passed. A forced post has its mp4, preview
    and poster all rebuilt: the derived artifacts are cut from the mirrored
    mp4, so a post that just changed variant would otherwise keep a preview
    and a poster rendered from the old, smaller encode."""
    if "--force" not in sys.argv:
        return None
    i = sys.argv.index("--force")
    if i + 1 >= len(sys.argv):
        raise SystemExit("--force requires a value: a comma-separated "
                          "list of post ids, or 'all'")
    return sys.argv[i + 1]


FORCE = _force_arg()


def media_id(url):
    m = re.search(r"/(?:amplify_video|ext_tw_video|tweet_video)/(\d+)/", url)
    return m.group(1) if m else None


def pick_variant(video):
    """Largest mp4 variant whose short side is at or below MAX_HEIGHT, as
    published by X. The cap applies to min(width, height) rather than raw
    height so portrait clips (e.g. 1080x1920) aren't rejected outright and
    dropped to the smallest available variant — a 1920x1080 landscape clip
    and a 1080x1920 portrait clip both pass (short side 1080 either way);
    a 3840x2160 4K clip is still rejected (short side 2160)."""
    out = []
    for f in video.get("formats") or []:
        m = re.search(r"/(\d+)x(\d+)/", f.get("url", ""))
        if f.get("container") == "mp4" and m:
            out.append((int(m.group(1)), int(m.group(2)), f["url"]))
    if not out:
        return video["url"], video.get("width"), video.get("height")
    out.sort(key=lambda x: x[0] * x[1])
    ok = [v for v in out if min(v[0], v[1]) <= MAX_HEIGHT] or out[:1]
    w, h, url = ok[-1]
    return url, w, h


def run(cmd):
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode:
        raise RuntimeError(cmd[0] + ": " + p.stderr.decode()[-400:])


def make_preview(src, dst, duration):
    """3s silent 480px loop, starting a little in to skip fades and slates."""
    start = 2 if duration > 8 else 0
    run([FFMPEG, "-y", "-v", "error", "-ss", str(start), "-t", "3", "-i", src,
         "-vf", "fps=10,scale=480:-2:flags=lanczos", "-an",
         "-c:v", "libwebp_anim", "-lossless", "0", "-q:v", "62",
         "-compression_level", "5", "-loop", "0", dst])


def make_poster(src, dst, duration):
    """Single sharp still frame, WebP, at the same start offset make_preview()
    uses — so the poster is the animation's first frame and the two never
    disagree. Scaled to at most 1280px wide, never upscaled past the source
    width."""
    start = 2 if duration > 8 else 0
    run([FFMPEG, "-y", "-v", "error", "-ss", str(start), "-i", src,
         "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2:flags=lanczos",
         "-c:v", "libwebp", "-quality", "78", dst])


def main():
    posts = json.load(open(os.path.join(ROOT, "data", "posts.json")))

    # r2.py reads R2_ACCOUNT/R2_KEY_ID/R2_SECRET at import time and ls() hits
    # the network, so a dry run must not require either — it only needs to
    # report what's missing, and with no credentials that just means "assume
    # nothing is mirrored yet."
    have_creds = all(os.environ.get(k) for k in ("R2_ACCOUNT", "R2_KEY_ID", "R2_SECRET"))
    if have_creds:
        import r2
        existing = set(r2.ls(BUCKET))
        print(f"bucket {BUCKET}: {len(existing)} objects already there")
    elif DRY:
        existing = set()
        print("no R2 credentials in the environment — treating the bucket as "
              "empty for this dry run")
    else:
        raise SystemExit("R2_ACCOUNT / R2_KEY_ID / R2_SECRET must be set to mirror "
                          "(use --dry-run to preview without needing them)")

    if FORCE == "all":
        forced = {p["id"] for p in posts}
    elif FORCE:
        forced = {x.strip() for x in FORCE.split(",") if x.strip()}
    else:
        forced = set()
    if forced:
        print(f"forcing a full rebuild for {len(forced)} post(s): {', '.join(sorted(forced))}")

    manifest, todo = {}, []
    for p in posts:
        src_url, w, h = pick_variant(p["video"])
        mid = media_id(src_url) or p["id"]
        base = f"{p['author']['handle']}_{mid}"
        mp4, webp, poster = f"{base}.mp4", f"{base}.webp", f"{base}.poster.webp"
        manifest[p["id"]] = {"mp4": f"{PUBLIC}/{mp4}", "webp": f"{PUBLIC}/{webp}",
                             "poster": f"{PUBLIC}/{poster}", "width": w, "height": h}
        need = [k for k in (mp4, webp, poster)
                if k not in existing or p["id"] in forced]
        if need:
            todo.append((p, src_url, mp4, webp, poster, need))

    print(f"{len(posts)} posts | {len(todo)} need work | {len(posts)-len(todo)} already mirrored")
    if DRY or not todo:
        json.dump(manifest, open(os.path.join(ROOT, "data", "mirror.json"), "w"),
                  indent=2, ensure_ascii=False)
        print("dry run — nothing uploaded" if DRY else "nothing to do")
        return

    done, failed = [], []

    def handle(item):
        p, src_url, mp4, webp, poster, need = item
        tag = f"@{p['author']['handle']}"
        with tempfile.TemporaryDirectory() as tmp:
            local = os.path.join(tmp, "v.mp4")
            run(["curl", "-sL", "--max-time", "600", "-o", local, src_url])
            n = os.path.getsize(local)
            if n < 10000:
                raise RuntimeError(f"download too small ({n}B)")
            if mp4 in need:
                r2.put(BUCKET, mp4, open(local, "rb").read(), "video/mp4")
            if webp in need:
                prev = os.path.join(tmp, "p.webp")
                make_preview(local, prev, p["video"]["duration"])
                r2.put(BUCKET, webp, open(prev, "rb").read(), "image/webp")
            if poster in need:
                pst = os.path.join(tmp, "poster.webp")
                make_poster(local, pst, p["video"]["duration"])
                r2.put(BUCKET, poster, open(pst, "rb").read(), "image/webp")
            return tag, n

    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(handle, it): it for it in todo}
        for i, f in enumerate(cf.as_completed(futs), 1):
            it = futs[f]
            try:
                tag, n = f.result()
                done.append(n)
                print(f"  [{i}/{len(todo)}] {tag} {n/1e6:.1f} MB")
            except Exception as e:
                failed.append((it[0]["author"]["handle"], str(e)[:120]))
                print(f"  [{i}/{len(todo)}] FAIL @{it[0]['author']['handle']}: {str(e)[:120]}")

    json.dump(manifest, open(os.path.join(ROOT, "data", "mirror.json"), "w"),
              indent=2, ensure_ascii=False)
    print(f"\nmirrored {len(done)} clips, {sum(done)/1e6:.0f} MB")
    if failed:
        print(f"{len(failed)} failed:")
        for h, e in failed:
            print(f"  @{h}: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
