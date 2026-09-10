# Setup & deployment

Two parts: running it locally, then hosting it free on Streamlit Community
Cloud.

---

## 1. Run locally

**Requires Python 3.9–3.12.** (Python 3.13 is fine locally but Streamlit Cloud
tops out at 3.12, so 3.12 is the safe choice.)

```bash
python -m venv .venv
```

Activate it — macOS/Linux:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```bash
.venv\Scripts\Activate.ps1
```

Then install and run:

```bash
pip install -r requirements.txt
```

```bash
streamlit run app.py
```

It opens at <http://localhost:8501>.

**The first launch is slow (1–2 minutes).** It downloads two ONNX models
(~220 MB total) and embeds the corpus. Every launch after that reads the cached
index from `.chroma/` and starts in a couple of seconds.

The index rebuilds itself automatically whenever `dataset/*.jsonl`, the
embedding model, or the passage-window settings change — a fingerprint of all
three is stored in `.chroma/build.json`. To force a rebuild, delete `.chroma/`.

---

## 2. Push to GitHub

The repo is already initialised. Streamlit Community Cloud deploys from
GitHub, so you need it there.

```bash
git add -A && git commit -m "RAG retrieval UI"
```

Create an **empty** repo on GitHub (no README, no .gitignore), then:

```bash
git remote add origin https://github.com/<you>/<repo>.git
```

```bash
git branch -M main && git push -u origin main
```

The repo can be public or private — Community Cloud handles both on the free
plan.

### What must be committed

- `app.py`, `rag_core.py`, `ui.py`
- `requirements.txt`
- everything in `dataset/` you want available in the deployed app
- `.streamlit/config.toml`

`.chroma/` is gitignored on purpose. The cloud container rebuilds it on first
boot; committing it would just ship a stale index.

---

## 3. Deploy on Streamlit Community Cloud (free)

1. Go to <https://share.streamlit.io> and sign in with GitHub.
2. **Create app** → **Deploy a public app from GitHub**.
3. Fill in:
   - **Repository** — `<you>/<repo>`
   - **Branch** — `main`
   - **Main file path** — `app.py`
4. Open **Advanced settings** and set **Python version** to **3.12**.
5. **Deploy.**

The first build takes roughly 5–10 minutes: it installs the dependencies, then
the container downloads the models and builds the index on first page load.
Watch the build log in the right-hand panel — the app is live once it says
`You can now view your Streamlit app`.

Every push to `main` redeploys automatically.

### Free-plan limits worth knowing

| Limit | Value | What it means here |
|---|---|---|
| Memory | ~1 GB | The app peaks near 500–600 MB. That headroom is why it uses ONNX models instead of torch. |
| Private apps | 1 | Public apps are unlimited. |
| Sleep | after ~7 days idle | Anyone can wake it; the next visitor waits for the rebuild. |
| Disk | ephemeral | `.chroma/` is rebuilt after every restart. Fine — it takes seconds. |

### Two things that are already handled

**sqlite3.** Community Cloud ships a system sqlite older than the 3.35 Chroma
requires. `requirements.txt` pulls `pysqlite3-binary` on Linux and the top of
`rag_core.py` swaps it in before Chroma is imported. Don't remove either half —
without them the deploy fails with
`unsupported version of sqlite3`.

**Torch.** Nothing in the dependency tree pulls it. If you add a library that
does, the install will likely blow the free tier's memory and disk.

---

## 4. Optional: render the figures

The dataset points at images by relative path, e.g.

```
extracted_images/POLIVY_GLOBAL_BRAND_BOOK_Q1_2026_1/p014/pymupdf_vector_render_ba447c625c.png
```

Those files aren't in the repo, so figures currently render as labelled
placeholders. To render them for real, copy the `extracted_images/` folder into
the project root, so paths resolve as
`<project root>/extracted_images/...`, then commit it.

`ui.py` also looks under `dataset/` and `assets/`, so any of these work:

```
<root>/extracted_images/...
<root>/dataset/extracted_images/...
<root>/assets/extracted_images/...
```

Images are inlined as base64 data URIs. Two caps in `ui.py` keep pages light:
`MAX_IMAGES_PER_CHUNK` (12) and `MAX_IMAGE_BYTES` (3 MB per file).

**Before committing images, check the total repo size.** GitHub warns above
1 GB and Community Cloud clones the whole repo on every build.

---

## 5. Tuning

### Swap the reranker

In `rag_core.py`:

```python
RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"   # ~90 MB  (default)
```

`BAAI/bge-reranker-base` is stronger, but it needs roughly **1.1 GB of RAM and
will OOM the free Community Cloud tier.** Use it only when self-hosting or on a
paid plan. Other fastembed cross-encoders that do fit:
`jinaai/jina-reranker-v1-tiny-en`, `Xenova/ms-marco-MiniLM-L-12-v2`.

Changing the reranker takes effect immediately. Changing `EMBED_MODEL` also
changes the index fingerprint, so the index rebuilds on next start.

### Other knobs

All in `rag_core.py`:

| Constant | Default | Effect |
|---|---|---|
| `PASSAGE_WORDS` / `PASSAGE_OVERLAP` | 180 / 45 | passage window; changing either rebuilds the index |
| `RERANK_TEMPERATURE` | 3.0 | lower = more extreme 0/1 scores |
| `W_RERANK` / `W_DENSE` / `W_COVERAGE` | .60 / .25 / .15 | relevance blend; must sum to 1.0 |
| `SUBSTANCE_FLOOR` / `SUBSTANCE_FULL_AT` | 0.40 / 40 | how hard near-empty sections are penalised |

Top-K, candidate pool size, minimum relevance, BM25 on/off, reranking on/off
and the fusion weight are all live in the app's right-hand control panel.

### Use a different dataset

Drop another `.jsonl` into `dataset/` — no code change needed. Every file
there is listed in the sidebar's corpus picker, and each keeps its own Chroma
collection, so switching between them does not force a rebuild.

Only the text is required. It is read from the first present of `chunk_text`,
`text`, `content`, `body`, `passage` or `page_content`. Titles, ids, document
names and page numbers each have their own list of accepted keys and fall back
to sensible defaults; see the field table in [README.md](README.md#any-dataset).
Blank lines, malformed JSON and text-less rows are skipped rather than fatal.

Confirm it before deploying:

```bash
python verify_datasets.py
```

---

## Troubleshooting

**`RuntimeError: Your system has an unsupported version of sqlite3`** — the
`pysqlite3-binary` line is missing from `requirements.txt`, or the shim at the
top of `rag_core.py` was moved below the `chromadb` import. It must run first.

**App crashes or restarts on Community Cloud** — almost always memory. Check
you haven't switched to `BAAI/bge-reranker-base` or pulled in torch.

**First load times out** — reload the page. The models are downloading; the
second attempt hits a warm cache.

**Stale or wrong results after editing a dataset** — delete `.chroma/` and
restart. Normally the per-collection fingerprint catches this automatically.

**A corpus won't load** — the app names the reason on screen. The usual cause
is that no line carries a recognised text key. Run `python verify_datasets.py`
to see it from the terminal.

**Icons render as words like `keyboard_arrow_right`** — a CSS `font-family`
rule is overriding Streamlit's Material Symbols font. Keep the font rule in
`ui.py` scoped to `html, body, .stApp`; never widen it to `[class*="st-"]`.
