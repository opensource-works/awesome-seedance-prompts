# Contributing

The fastest way to help is to add posts we missed.

## Add a post

1. Find a post on X that shows a **Seedance-generated video**.
2. Add its URL on its own line in [`scripts/urls.txt`](scripts/urls.txt).
3. Open a pull request. That's it — you don't need to run anything locally.

A post gets included automatically if it has a playable video attached and mentions
Seedance. Everything else — the caption, the prompt, the author's name and handle,
the view count — is pulled from the post itself. If the exact prompt is in a public
reply by the same source account, it can be preserved with a source link as described below.

## What belongs here

- Real Seedance output: clips someone actually generated and posted.
- Prompts, workflows and technique breakdowns.
- Honest failure cases and model comparisons. A post does not have to be flattering.

## What doesn't

- Reposts of someone else's generation without credit.
- Videos that aren't Seedance.
- Pure engagement bait with no clip and no prompt.

## Fixing a title, category or reply prompt

Titles and categories are guessed from the post text, so some land wrong. Correct them in
[`scripts/overrides.json`](scripts/overrides.json), keyed by post id:

```json
"2075074872351572216": {
  "title": "Tom and Jerry recreated as photoreal animals in 4K",
  "category": "Anime & Animation"
}
```

The accepted fields are `title`, `category`, `prompt`, `prompt_source_urls` and
`prompt_in_thread`. A reply prompt must be copied verbatim, list every public X post/reply
used as its source, and set `prompt_in_thread` to `false`. Author names and stats are never
overridden.

## Regenerating everything

```bash
python3 scripts/harvest.py          # scripts/urls.txt -> data/posts.json
python3 scripts/mirror.py           # copy clips to R2 + render animated previews
python3 scripts/build.py            # data/posts.json  -> docs/ + both READMEs
```

`harvest.py --cache` reuses `.cache/` and only fetches URLs it hasn't seen, which is
much faster while you're iterating. It needs no API key or login.

`mirror.py` is the only step that needs credentials (`R2_ACCOUNT`, `R2_KEY_ID`,
`R2_SECRET`) and `ffmpeg` on your PATH. You can skip it — `build.py` falls back to
X's own URLs for anything not in `data/mirror.json`. CI runs it for you on merge,
so a PR that only adds a URL doesn't need to touch R2 at all.

Why the mirror exists: X rotates its `video.twimg.com` URLs, which would silently
break playback across the whole gallery. The mirror keeps the largest encode X
publishes at 1080p or below — its file, not a re-encode — plus a 3-second silent
WebP loop, because GitHub strips `<video>` and an animated image is the only way
to show motion in a README.

Please don't hand-edit `data/posts.json`, `docs/index.html` or the READMEs — they are
generated, and your changes will be overwritten on the next build.

## If it's your post

Everything here is credited and links back to you. If you'd still rather not be listed,
or something is wrong, [open an issue](https://github.com/opensource-works/awesome-seedance-prompts/issues/new)
and it comes down — no questions asked.
