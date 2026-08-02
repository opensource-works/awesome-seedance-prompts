# Contributing

The fastest way to help is to add posts we missed.

## Add a post

1. Find a post on X that shows a **Seedance-generated video**.
2. Add its URL on its own line in [`scripts/urls.txt`](scripts/urls.txt).
3. Open a pull request. That's it — you don't need to run anything locally.

A post gets included automatically if it has a playable video attached and mentions
Seedance. Everything else — the caption, the prompt, the author's name and handle,
the view count — is pulled from the post itself.

## What belongs here

- Real Seedance output: clips someone actually generated and posted.
- Prompts, workflows and technique breakdowns.
- Honest failure cases and model comparisons. A post does not have to be flattering.

## What doesn't

- Reposts of someone else's generation without credit.
- Videos that aren't Seedance.
- Pure engagement bait with no clip and no prompt.

## Fixing a title or category

Titles and categories are guessed from the post text, so some land wrong. Correct them in
[`scripts/overrides.json`](scripts/overrides.json), keyed by post id:

```json
"2075074872351572216": {
  "title": "Tom and Jerry recreated as photoreal animals in 4K",
  "category": "Anime & Animation"
}
```

Only `title` and `category` may be overridden. Prompts, author names and stats must stay
exactly as posted — if those look wrong, the fix is a bug report, not an override.

## Regenerating everything

```bash
python3 scripts/harvest.py          # scripts/urls.txt -> data/posts.json
python3 scripts/build.py            # data/posts.json  -> docs/ + both READMEs
```

`harvest.py --cache` reuses `.cache/` and only fetches URLs it hasn't seen, which is
much faster while you're iterating. No API key or login is needed.

Please don't hand-edit `data/posts.json`, `docs/index.html` or the READMEs — they are
generated, and your changes will be overwritten on the next build.

## If it's your post

Everything here is credited and links back to you. If you'd still rather not be listed,
or something is wrong, [open an issue](https://github.com/opensource-works/awesome-seedance-prompts/issues/new)
and it comes down — no questions asked.
