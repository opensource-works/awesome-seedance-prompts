# Uploading clips for inline GitHub players

GitHub renders a **bare** `https://github.com/user-attachments/assets/<uuid>` URL —
alone on its own line — as a real video player with sound and controls. That is the
only markup that works: wrap the same URL in `<video>` or in a link and it renders as
plain text.

Those URLs are only issued by uploading through the browser. There is no REST API and
`gh` cannot do it, so this one step is manual. Everything around it is scripted.

## 1. Stage the files

```bash
python3 scripts/prepare_uploads.py /mnt/c/Users/<you>/Desktop/seedance-uploads
```

You get `001_handle.mp4` … `064_handle.mp4` plus `index.json`. The numbers are how the
uploaded URLs get mapped back to posts, so **don't rename or reorder them**.

Each file is the largest encode X publishes at 1080p or below that still fits under
GitHub's 100 MB attachment cap; anything larger drops to the next variant down
automatically.

## 2. Upload them

1. Open a new issue on the repo — it is just being used as an upload surface:
   <https://github.com/opensource-works/awesome-seedance-prompts/issues/new>
2. Drag files into the comment box **in numeric order**, about 8–10 at a time.
3. Wait for every `Uploading…` placeholder in that batch to turn into a URL before
   dragging the next batch. Uploading out of order or copying early is what breaks the
   mapping.
4. When all 64 are done, submit the issue (title it something like
   `Video attachments — do not close`). Submitting isn't strictly required for the URLs
   to work, but it keeps a record of what was uploaded and when.

## 3. Feed the URLs back

Copy the whole comment body into a file and run:

```bash
python3 scripts/ingest_uploads.py pasted.txt
python3 scripts/build.py
```

`ingest_uploads.py` maps by filename when GitHub includes one, and by upload order
otherwise — in which case it asks which file number the first URL belongs to, so you
can ingest batch by batch instead of all at once. It prints which numbers are still
missing, and re-runs merge, so a partial upload is safe to resume.

## Keeping it working

New posts contributed later need this same manual pass, otherwise they fall back to the
animated preview. Nothing breaks — `build.py` uses whichever is available per post — but
CI cannot produce inline players on its own.
