# Brand Book Retrieval

A single-page Streamlit app that searches a chunked PDF corpus and shows you
the evidence it found, with the scores that justify each result.

There is **no LLM in the loop.** Nothing is generated or summarised — the
"answer" is the retrieved source material itself, rendered cleanly.

```
query ─► bge-small embedding ─┬─► Chroma (cosine, HNSW) ─┐
                              │                          ├─► RRF fusion ─► cross-encoder rerank ─► section rollup ─► report
                              └─► BM25 (lexical) ────────┘
```

## What it does

- **Hybrid retrieval** — dense vector search and BM25 keyword search run in
  parallel and are merged with reciprocal-rank fusion.
- **Cross-encoder reranking** — every surviving candidate is re-scored against
  the query by a cross-encoder. This is the single biggest accuracy win.
- **Parent-section rollup** — long sections are indexed as overlapping
  passages so nothing overflows the embedder's context, then rolled back up so
  you read whole sections, not fragments.
- **A readable report** — each retrieved chunk renders with its markdown
  tables as real tables, its figures as framed thumbnails, its colour swatches
  as chips, and its retrieval metrics underneath.

## Scoring

The headline **relevance** is a composite, not a single model output:

```
signal    = 0.60 × rerank + 0.25 × vector + 0.15 × term-coverage
relevance = signal × substance
```

| Component | What it is |
|---|---|
| `rerank` | cross-encoder logit, divided by a temperature of 3 and squashed to 0–1 |
| `vector` | Chroma cosine similarity, min-maxed across the candidate pool |
| `term coverage` | fraction of the query's content words present in the section |
| `substance` | 0.4–1.0, scaling down sections that are near-empty divider pages |

**Why a blend and not just the reranker.** On this corpus the reranker
occasionally buries a section that both the vector search and keyword overlap
agree on, and a plain sigmoid over its logits pins almost everything to 0.0 or
1.0 — useless to read off a dashboard. The blend keeps the reranker dominant
while staying legible. Every component is displayed separately on each card, so
the composite is never a black box.

Query-level metrics — top relevance, mean, score margin, retriever agreement,
term coverage, latency, passages scored — sit at the top of the report.

> These are **retrieval confidence signals, not measured accuracy.** This
> corpus has no ground-truth relevance labels, so nothing here is a precision
> or recall figure. Treat them as a way to tell a confident hit from a guess.

## Stack

| Piece | Choice | Why |
|---|---|---|
| UI | Streamlit | single file, deploys free |
| Vector store | Chroma (persistent, cosine) | local, no service to run |
| Embeddings | `BAAI/bge-small-en-v1.5` (384-dim) | strong for its size |
| Reranker | `Xenova/ms-marco-MiniLM-L-6-v2` | ~90 MB, fits the free tier |
| Lexical | `rank-bm25` | pure Python, no index server |
| Runtime | `fastembed` → onnxruntime | **no torch**, which is what keeps the app inside the 1 GB free-tier budget |

## Layout

| File | Role |
|---|---|
| `app.py` | Streamlit page: sidebar, chat column, right-hand panel |
| `rag_core.py` | loading, passage windowing, Chroma index, retrieval, scoring |
| `ui.py` | theme CSS and the HTML for a rendered chunk |
| `dataset/phase4_ready_sections.jsonl` | the corpus (36 chunks) |
| `SETUP.md` | local setup and Streamlit Community Cloud deployment |

## Run it

```bash
pip install -r requirements.txt && streamlit run app.py
```

First launch downloads the two ONNX models (~220 MB) and builds the index.
Later launches reuse the cache in `.chroma/`, which is rebuilt automatically
whenever the dataset or the embedding settings change.

Full instructions, including free-tier deployment, are in [SETUP.md](SETUP.md).

## Figures

The dataset references extracted images by relative path
(`extracted_images/<doc>/<page>/<file>.png`). Those files are **not** part of
this repo, so figures render as labelled placeholders showing the page number,
classification and filename. Drop the `extracted_images/` folder into the
project root and they render inline — see SETUP.md.
