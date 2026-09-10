"""POLIVY Brand Book — retrieval explorer.

A single-page Streamlit app over a Chroma index of the brand book. There is no
LLM in the loop: you ask, it retrieves, reranks and shows you the evidence with
the scores that justify it.
"""

from __future__ import annotations

import streamlit as st

import ui
from rag_core import EMBED_MODEL, RERANK_MODEL, RagEngine

st.set_page_config(
    page_title="Brand Book Retrieval",
    page_icon=":material/search:",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(ui.CSS, unsafe_allow_html=True)

SAMPLE_QUERIES = [
    "Minimum clear space around the logo",
    "Peripheral neuropathy safety data",
    "Primary colour palette and hex codes",
    "Typography hierarchy for digital",
    "Droplet supergraphic cropping rules",
    "How do I build a chart?",
]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def get_engine() -> RagEngine:
    return RagEngine()


def init_state():
    st.session_state.setdefault("messages", [])   # chat transcript
    st.session_state.setdefault("results", [])    # RetrievalResult per answer
    st.session_state.setdefault("viewing", None)  # index into results
    st.session_state.setdefault("panel", "controls")
    st.session_state.setdefault("pending", None)  # query awaiting execution


init_state()

with st.spinner("Loading embedding model and building the vector index…"):
    engine = get_engine()
stats = engine.stats()


# ---------------------------------------------------------------------------
# Sidebar — menu + database
# ---------------------------------------------------------------------------

def render_sidebar():
    st.markdown(
        '<div class="sb-brand"><div class="sb-mark">RB</div>'
        '<div><div class="sb-title">Brand Book Retrieval</div>'
        '<div class="sb-sub">Hybrid RAG · no LLM</div></div></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sb-label">Menu</div>', unsafe_allow_html=True)
    if st.button("＋  New search", use_container_width=True):
        st.session_state.messages = []
        st.session_state.results = []
        st.session_state.viewing = None
        st.session_state.panel = "controls"
        st.rerun()
    if st.button("⚙  Retrieval controls", use_container_width=True):
        st.session_state.panel = "controls"
        st.rerun()
    if st.button("▤  Latest report", use_container_width=True, disabled=not st.session_state.results):
        st.session_state.viewing = len(st.session_state.results) - 1
        st.session_state.panel = "report"
        st.rerun()

    st.markdown('<div class="sb-label">Database</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="db-card">'
        f'<div class="db-name">POLIVY Global Brand Book</div>'
        f'<div class="db-meta">Q1 2026 · {stats["pages"]} pages indexed</div>'
        f'<div class="db-grid">'
        f'<div class="db-cell"><b>{stats["sections"]}</b><span>chunks</span></div>'
        f'<div class="db-cell"><b>{stats["passages"]}</b><span>passages</span></div>'
        f'<div class="db-cell"><b>{stats["tables"]}</b><span>tables</span></div>'
        f'<div class="db-cell"><b>{stats["images"]}</b><span>figures</span></div>'
        f"</div>"
        f'<div class="db-model"><span>Store</span><span>Chroma · cosine</span></div>'
        f'<div class="db-model"><span>Embedding</span><span>bge-small-en-v1.5</span></div>'
        f'<div class="db-model"><span>Reranker</span><span>{RERANK_MODEL.split("/")[-1]}</span></div>'
        f'<div class="db-model"><span>Dimensions</span><span>{stats["dim"]}</span></div>'
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sb-label">Try a query</div>', unsafe_allow_html=True)
    for i, q in enumerate(SAMPLE_QUERIES):
        if st.button(q, key=f"sample_{i}", use_container_width=True):
            st.session_state.pending = q
            st.rerun()

    with st.expander("How scoring works"):
        st.markdown(
            "**Relevance** is a composite, not a single model output:\n\n"
            "`0.60 × rerank + 0.25 × vector + 0.15 × term coverage`, then scaled "
            "down for sections with very little body text.\n\n"
            "- **Rerank** — cross-encoder logit, temperature-scaled to 0–1\n"
            "- **Vector** — cosine similarity from Chroma\n"
            "- **BM25** — lexical score, normalised across candidates\n"
            "- **Fusion** — reciprocal-rank fusion of vector + BM25\n\n"
            "These are retrieval confidence signals. There are no ground-truth "
            "labels for this corpus, so nothing here is a measured accuracy."
        )


with st.sidebar:
    render_sidebar()


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

chat_col, panel_col = st.columns([1.45, 1], gap="large")


# ---------------------------------------------------------------------------
# Right panel — controls
# ---------------------------------------------------------------------------

def render_controls():
    st.markdown(
        '<div class="panel-head"><div class="t">Retrieval controls</div>'
        '<span class="sub">applied to the next query</span></div>',
        unsafe_allow_html=True,
    )

    st.slider("Top K sections returned", 1, 10, key="top_k",
              help="How many document sections end up in the report.")
    st.slider("Candidate passages", 10, 60, step=5, key="candidates",
              help="Passages pulled from each retriever before fusion and reranking. "
                   "Higher recall, slower.")
    st.slider("Minimum relevance", 0.0, 1.0, step=0.05, key="min_relevance",
              help="Sections scoring below this are dropped from the report.")

    st.markdown('<div class="sb-label">Pipeline</div>', unsafe_allow_html=True)
    st.toggle("Lexical BM25 retrieval", key="use_bm25",
              help="Adds exact keyword matching alongside the vector search.")
    st.toggle("Cross-encoder reranking", key="use_rerank",
              help="Re-scores every candidate against the query. The single "
                   "biggest accuracy win, and the slowest step.")
    st.slider("Vector vs keyword weight", 0.0, 1.0, step=0.1, key="alpha",
              disabled=not st.session_state.use_bm25,
              help="Fusion weight. 1.0 is vector-only, 0.0 is keyword-only.")

    st.markdown(
        f'<div class="note">Index holds <b>{stats["passages"]} passages</b> across '
        f'<b>{stats["sections"]} chunks</b>. Embeddings: <code>{EMBED_MODEL}</code>.</div>',
        unsafe_allow_html=True,
    )


def init_controls():
    defaults = {
        "top_k": 5, "candidates": 25, "min_relevance": 0.10,
        "use_bm25": True, "use_rerank": True, "alpha": 0.6,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


init_controls()


# ---------------------------------------------------------------------------
# Right panel — report
# ---------------------------------------------------------------------------

def render_report():
    idx = st.session_state.viewing
    if idx is None or idx >= len(st.session_state.results):
        render_empty_panel()
        return
    result = st.session_state.results[idx]

    head_l, head_r = st.columns([3, 1])
    with head_l:
        st.markdown(
            f'<div class="panel-head"><div class="t">Retrieved evidence</div>'
            f'<span class="sub">{len(result.hits)} of {result.metrics["candidates_grouped"]} sections</span></div>',
            unsafe_allow_html=True,
        )
    with head_r:
        if st.button("⚙ Controls", use_container_width=True):
            st.session_state.panel = "controls"
            st.rerun()

    st.markdown(f'<div class="note">Query · “{ui.esc(result.query)}”</div>',
                unsafe_allow_html=True)
    st.markdown(ui.summary_html(result.metrics, result.timings), unsafe_allow_html=True)

    if len(st.session_state.results) > 1:
        labels = [f"{i + 1}. {r.query[:34]}" for i, r in enumerate(st.session_state.results)]
        picked = st.selectbox("Report", labels, index=idx, label_visibility="collapsed")
        new_idx = labels.index(picked)
        if new_idx != idx:
            st.session_state.viewing = new_idx
            st.rerun()

    if not result.hits:
        st.markdown(
            '<div class="empty"><span class="ic">◎</span><b>Nothing cleared the threshold</b>'
            "Lower the minimum relevance, or widen the candidate pool.</div>",
            unsafe_allow_html=True,
        )
        return

    for hit in result.hits:
        st.markdown(ui.chunk_card_html(hit), unsafe_allow_html=True)

    with st.expander("Pipeline timings"):
        for stage in result.trace:
            st.markdown(
                f'<div class="trace-row"><span class="d"></span>'
                f'<span class="l">{ui.esc(stage["label"])}</span>'
                f'<span class="x">{stage["detail"]}</span>'
                f'<span class="t">{stage["ms"]:.0f} ms</span></div>',
                unsafe_allow_html=True,
            )


def render_empty_panel():
    st.markdown(
        '<div class="panel-head"><div class="t">Retrieved evidence</div>'
        '<span class="sub">waiting for a query</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="empty"><span class="ic">◇</span><b>No results yet</b>'
        "Ask something below. The retrieved chunks, their tables, figures and "
        "scores will appear here as a report.</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Centre column — conversation
# ---------------------------------------------------------------------------

def answer_summary_html(result) -> str:
    if not result.hits:
        return (
            '<div class="bubble-bot"><div class="headline">No section passed the '
            "relevance threshold.</div>Try rephrasing, or relax the controls on the "
            "right.</div>"
        )
    m = result.metrics
    items = "".join(
        f'<li><span class="res-n">{h.rank}</span>'
        f'<span class="res-t">{ui.esc(h.section.section_label)}</span>'
        f'<span class="res-p">{ui.esc(h.section.page_label)}</span>'
        f'<span class="res-s">{ui.pct(h.relevance)}</span></li>'
        for h in result.hits
    )
    return (
        f'<div class="bubble-bot">'
        f'<div class="headline">{len(result.hits)} sections retrieved · '
        f'{m["confidence"].lower()} confidence</div>'
        f"Scored {m['scanned']} passages in {result.timings['total_ms']:.0f} ms. "
        f"Top match {ui.pct(m['top_relevance'])}, mean {ui.pct(m['mean_relevance'])}. "
        f"Full evidence is in the report on the right."
        f'<ul class="res-list">{items}</ul></div>'
    )


def replay_history():
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.markdown(f'<div class="row-user"><div class="bubble-user">'
                            f'{ui.esc(msg["text"])}</div></div>',
                            unsafe_allow_html=True)
        else:
            result = st.session_state.results[msg["result"]]
            with st.chat_message("assistant"):
                with st.expander(f"Thought for {result.timings['total_ms']:.0f} ms"):
                    for stage in result.trace:
                        st.markdown(
                            f'<div class="trace-row"><span class="d"></span>'
                            f'<span class="l">{ui.esc(stage["label"])}</span>'
                            f'<span class="x">{stage["detail"]}</span></div>',
                            unsafe_allow_html=True,
                        )
                st.markdown(answer_summary_html(result), unsafe_allow_html=True)
                if st.button("View report ▸", key=f"view_{msg['result']}"):
                    st.session_state.viewing = msg["result"]
                    st.session_state.panel = "report"
                    st.rerun()


def run_query(query: str):
    """Execute one retrieval, streaming the pipeline steps as they happen."""
    with st.chat_message("user"):
        st.markdown(f'<div class="row-user"><div class="bubble-user">'
                    f'{ui.esc(query)}</div></div>',
                    unsafe_allow_html=True)

    with st.chat_message("assistant"):
        with st.status("Thinking…", expanded=True) as status:
            def on_step(label, detail):
                st.markdown(
                    f'<div class="trace-row"><span class="d"></span>'
                    f'<span class="l">{ui.esc(label)}</span>'
                    f'<span class="x">{ui.esc(detail)}</span></div>',
                    unsafe_allow_html=True,
                )

            result = engine.search(
                query,
                top_k=st.session_state.top_k,
                candidates=st.session_state.candidates,
                use_bm25=st.session_state.use_bm25,
                use_rerank=st.session_state.use_rerank,
                min_relevance=st.session_state.min_relevance,
                alpha=st.session_state.alpha,
                on_step=on_step,
            )
            status.update(
                label=f"Thought for {result.timings['total_ms']:.0f} ms",
                state="complete",
                expanded=False,
            )
        st.markdown(answer_summary_html(result), unsafe_allow_html=True)

    st.session_state.results.append(result)
    idx = len(st.session_state.results) - 1
    st.session_state.messages.append({"role": "user", "text": query})
    st.session_state.messages.append({"role": "assistant", "result": idx})
    st.session_state.viewing = idx
    st.session_state.panel = "report"


with chat_col:
    st.markdown(
        '<div class="page-head"><div class="t">Brand Book Retrieval</div>'
        '<span class="tag">retrieval only</span></div>'
        '<p class="page-sub">Hybrid vector + keyword search with cross-encoder '
        "reranking. Answers are the source passages themselves — nothing is "
        "generated.</p>",
        unsafe_allow_html=True,
    )

    if not st.session_state.messages and not st.session_state.pending:
        st.markdown(
            '<div class="empty"><span class="ic">◆</span><b>Ask the brand book something</b>'
            "Logo rules, colour palette, typography, campaign artwork, safety and "
            "efficacy data — all 36 chunks are indexed.</div>",
            unsafe_allow_html=True,
        )

    replay_history()

    pending = st.session_state.pending
    if pending:
        st.session_state.pending = None
        run_query(pending)
        st.rerun()

with panel_col:
    if st.session_state.panel == "report" and st.session_state.results:
        render_report()
    elif st.session_state.results:
        render_controls()
    else:
        render_controls()

typed = st.chat_input("Ask about the brand book…")
if typed:
    st.session_state.pending = typed
    st.rerun()
