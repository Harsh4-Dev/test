"""Presentation layer: theme CSS plus the HTML that renders a retrieved chunk.

Each chunk is rendered as a single self-contained HTML card so the prose,
tables, images and metrics stay visually welded together. Markdown tables are
converted to HTML here rather than handed to st.markdown, which lets the card
own its own scrolling and typography.
"""

from __future__ import annotations

import base64
import html
import mimetypes
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# Where image paths from the dataset are resolved from, in priority order.
IMAGE_ROOTS = [PROJECT_ROOT, PROJECT_ROOT / "dataset", PROJECT_ROOT / "assets"]

MAX_IMAGES_PER_CHUNK = 12
MAX_IMAGE_BYTES = 3_000_000


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

CSS = """
<style>
:root{
  --blue-800:#083E7D; --blue-700:#0B4F9E; --blue-600:#0A66C2; --blue-500:#2B86D9;
  --blue-100:#DCE9F8; --blue-50:#EFF5FD; --blue-25:#F7FAFE;
  --ink:#16202C; --ink-2:#33465C; --muted:#6A7C91; --faint:#94A5B8;
  --line:#E3EAF2; --line-2:#EEF2F7; --white:#fff;
  --ok:#1A7F5A; --warn:#B4761B; --bad:#B4453C;
  --radius:12px;
  --shadow:0 1px 2px rgba(16,40,70,.05), 0 6px 18px rgba(16,40,70,.05);
}

/* ---------- shell ---------- */
.stApp{ background:var(--white); }
#MainMenu, footer, header [data-testid="stStatusWidget"]{ visibility:hidden; }
/* Streamlit's header is absolutely positioned and 60px tall, and the main
   area scrolls underneath it. Without this clearance the page title and the
   top of the report sit behind it when scrolled all the way up. */
.block-container{ padding-top:4.5rem; padding-bottom:7rem; max-width:1560px; }
/* Note: do NOT widen this to [class*="st-"] - that selector also hits
   Streamlit's icon spans and replaces the Material Symbols font, which makes
   every icon render as its literal ligature name. */
html, body, .stApp{
  font-family:"Inter","Segoe UI",system-ui,-apple-system,sans-serif;
  color:var(--ink);
}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"]{ background:var(--blue-25); border-right:1px solid var(--line); }
[data-testid="stSidebar"] .block-container{ padding-top:1.1rem; }
.sb-brand{ display:flex; gap:.7rem; align-items:center; padding:.1rem 0 .9rem; }
.sb-mark{
  width:36px; height:36px; border-radius:9px; flex:none;
  background:linear-gradient(140deg,var(--blue-600),var(--blue-800));
  color:#fff; font-weight:700; font-size:.95rem;
  display:flex; align-items:center; justify-content:center; letter-spacing:.02em;
}
.sb-title{ font-weight:650; font-size:.95rem; line-height:1.15; }
.sb-sub{ font-size:.72rem; color:var(--muted); margin-top:.12rem; }
.sb-label{
  font-size:.68rem; font-weight:650; letter-spacing:.09em; text-transform:uppercase;
  color:var(--faint); margin:1.1rem 0 .45rem;
}
.db-card{
  background:#fff; border:1px solid var(--line); border-radius:var(--radius);
  padding:.7rem .8rem; box-shadow:var(--shadow);
}
.db-name{ font-weight:600; font-size:.8rem; margin-bottom:.15rem; word-break:break-word; }
.db-meta{ font-size:.7rem; color:var(--muted); margin-bottom:.55rem; }
.db-grid{ display:grid; grid-template-columns:1fr 1fr; gap:.4rem; }
.db-cell{ background:var(--blue-25); border-radius:8px; padding:.35rem .45rem; }
.db-cell b{ display:block; font-size:.95rem; color:var(--blue-700); line-height:1.1; }
.db-cell span{ font-size:.64rem; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; }
.db-model{
  display:flex; justify-content:space-between; gap:.5rem;
  font-size:.68rem; padding:.3rem 0; border-top:1px dashed var(--line-2);
}
.db-model span:first-child{ color:var(--muted); }
.db-model span:last-child{ font-family:ui-monospace,"Cascadia Mono",Menlo,monospace; color:var(--ink-2); }

/* ---------- page header ---------- */
.page-head{ display:flex; align-items:baseline; gap:.6rem; margin:0 0 .1rem; }
.page-head .t{ font-size:1.22rem; font-weight:650; margin:0; letter-spacing:-.01em; }
.page-head .tag{
  font-size:.64rem; font-weight:600; letter-spacing:.06em; text-transform:uppercase;
  color:var(--blue-700); background:var(--blue-50); border:1px solid var(--blue-100);
  padding:.15rem .45rem; border-radius:999px;
}
.page-sub{ font-size:.8rem; color:var(--muted); margin:0 0 1rem; }

/* ---------- chat ---------- */
[data-testid="stChatMessage"]{
  background:transparent; padding:.25rem 0; border:none; gap:0;
}
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"]{ display:none; }
.row-user{ display:flex; justify-content:flex-end; }
.bubble-user{
  background:var(--blue-600); color:#fff; padding:.6rem .85rem; border-radius:12px 12px 3px 12px;
  max-width:88%; font-size:.88rem; line-height:1.45;
}
.bubble-bot{
  background:var(--blue-25); border:1px solid var(--line); border-radius:12px 12px 12px 3px;
  padding:.7rem .9rem; font-size:.87rem; line-height:1.5; color:var(--ink-2);
}
.bubble-bot .headline{ color:var(--ink); font-weight:600; font-size:.9rem; margin-bottom:.4rem; }
.res-list{ margin:.5rem 0 0; padding:0; list-style:none; }
.res-list li{
  display:flex; gap:.55rem; align-items:center; padding:.3rem 0;
  border-top:1px solid var(--line-2); font-size:.82rem;
}
.res-list li:first-child{ border-top:none; }
.res-n{
  flex:none; width:19px; height:19px; border-radius:5px; background:var(--blue-600); color:#fff;
  font-size:.66rem; font-weight:700; display:flex; align-items:center; justify-content:center;
}
.res-t{ flex:1; color:var(--ink); }
.res-p{ color:var(--faint); font-size:.72rem; }
.res-s{ font-variant-numeric:tabular-nums; font-weight:650; color:var(--blue-700); font-size:.78rem; }

/* ---------- right panel ---------- */
.panel-head{
  display:flex; align-items:center; justify-content:space-between;
  padding-bottom:.5rem; margin-bottom:.2rem; border-bottom:2px solid var(--blue-600);
}
.panel-head .t{ font-size:.94rem; font-weight:650; margin:0; }
.panel-head .sub{ font-size:.72rem; color:var(--muted); }

/* summary metric strip */
.mstrip{ display:grid; grid-template-columns:repeat(4,1fr); gap:.4rem; margin:.7rem 0 .2rem; }
.mbox{
  background:#fff; border:1px solid var(--line); border-radius:10px;
  padding:.45rem .5rem; text-align:center;
}
.mbox b{ display:block; font-size:1.02rem; color:var(--blue-700); font-variant-numeric:tabular-nums; line-height:1.2; }
.mbox span{ font-size:.6rem; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; }
.mbox.conf-High b{ color:var(--ok); } .mbox.conf-Moderate b{ color:var(--blue-700); }
.mbox.conf-Low b{ color:var(--warn); } .mbox.conf-Verylow b, .mbox.conf-Nomatch b{ color:var(--bad); }

/* ---------- chunk card ---------- */
.chunk{
  background:#fff; border:1px solid var(--line); border-radius:var(--radius);
  box-shadow:var(--shadow); margin:.85rem 0; overflow:hidden;
}
.chunk-top{
  display:flex; gap:.6rem; align-items:flex-start;
  padding:.7rem .85rem .6rem; border-bottom:1px solid var(--line-2);
  background:linear-gradient(180deg,var(--blue-25),#fff);
}
.chunk-rank{
  flex:none; width:24px; height:24px; border-radius:7px; background:var(--blue-600); color:#fff;
  font-size:.74rem; font-weight:700; display:flex; align-items:center; justify-content:center;
}
.chunk-id{ flex:1; min-width:0; }
.chunk-id .t{ font-size:.9rem; font-weight:650; margin:0; line-height:1.25; color:var(--ink); }
.chunk-id .path{
  font-size:.64rem; color:var(--faint); margin-top:.18rem;
  font-family:ui-monospace,"Cascadia Mono",Menlo,monospace;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
.chunk-score{ flex:none; text-align:right; }
.chunk-score b{ font-size:1.02rem; color:var(--blue-700); font-variant-numeric:tabular-nums; }
.chunk-score span{ display:block; font-size:.6rem; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; }

.chip-row{ display:flex; flex-wrap:wrap; gap:.3rem; padding:.5rem .85rem 0; }
.chip{
  font-size:.66rem; padding:.13rem .42rem; border-radius:999px;
  background:var(--blue-50); color:var(--blue-700); border:1px solid var(--blue-100);
}
.chip.n{ background:#F4F6F9; color:var(--ink-2); border-color:var(--line); }

.chunk-body{ padding:.6rem .85rem .2rem; font-size:.83rem; line-height:1.6; color:var(--ink-2); }
.chunk-body .sub-h{
  font-size:.8rem; font-weight:650; color:var(--blue-800);
  margin:.9rem 0 .3rem; padding-left:.5rem; border-left:3px solid var(--blue-500);
}
.chunk-body .sub-h:first-child{ margin-top:0; }
.chunk-body p{ margin:.35rem 0; }
.chunk-body ul{ margin:.35rem 0; padding-left:1.05rem; }
.chunk-body li{ margin:.16rem 0; }
.chunk-body mark{
  background:var(--blue-100); color:var(--blue-800); font-weight:550;
  padding:0 .12em; border-radius:2px;
}
.chunk-body details{ margin:.2rem 0 0; }
.chunk-body details summary{
  cursor:pointer; font-size:.72rem; font-weight:600; color:var(--blue-700);
  padding:.3rem 0; list-style:none; user-select:none;
}
.chunk-body details summary::-webkit-details-marker{ display:none; }
.chunk-body details summary::before{ content:"▸ "; }
.chunk-body details[open] summary::before{ content:"▾ "; }

/* tables */
.tbl-wrap{ margin:.7rem 0; }
.tbl-cap{ font-size:.66rem; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; margin-bottom:.25rem; }
.tbl-scroll{ overflow-x:auto; border:1px solid var(--line); border-radius:9px; }
.tbl-scroll table{ border-collapse:collapse; width:100%; font-size:.76rem; }
.tbl-scroll th{
  background:var(--blue-600); color:#fff; font-weight:600; text-align:left;
  padding:.4rem .55rem; white-space:nowrap;
}
.tbl-scroll td{ padding:.35rem .55rem; border-top:1px solid var(--line-2); color:var(--ink-2); }
.tbl-scroll tbody tr:nth-child(even){ background:var(--blue-25); }

/* images */
.img-grid{ display:grid; grid-template-columns:repeat(auto-fill,minmax(140px,1fr)); gap:.5rem; margin:.6rem 0; }
.img-frame{ border:1px solid var(--line); border-radius:9px; overflow:hidden; background:#fff; }
.img-frame .shot{
  background:repeating-conic-gradient(#F4F7FB 0 25%, #fff 0 50%) 50%/14px 14px;
  display:flex; align-items:center; justify-content:center; min-height:88px; padding:.3rem;
}
.img-frame img{ max-width:100%; max-height:170px; display:block; }
.img-frame .cap{
  font-size:.62rem; color:var(--muted); padding:.28rem .4rem;
  border-top:1px solid var(--line-2); display:flex; justify-content:space-between; gap:.3rem;
}
.img-miss{
  min-height:88px; display:flex; flex-direction:column; align-items:center; justify-content:center;
  gap:.2rem; border:1px dashed var(--line); border-radius:9px; padding:.5rem; text-align:center;
  background:var(--blue-25);
}
.img-miss .ic{ font-size:1rem; opacity:.45; }
.img-miss .t{ font-size:.62rem; color:var(--muted); }
.img-miss .f{
  font-size:.55rem; color:var(--faint); word-break:break-all; line-height:1.25;
  font-family:ui-monospace,"Cascadia Mono",Menlo,monospace;
}

/* swatches */
.sw-row{ display:flex; flex-wrap:wrap; gap:.3rem; margin:.5rem 0; }
.sw{ display:flex; align-items:center; gap:.3rem; border:1px solid var(--line); border-radius:999px; padding:.12rem .45rem .12rem .15rem; font-size:.64rem; color:var(--ink-2); }
.sw i{ width:13px; height:13px; border-radius:50%; border:1px solid rgba(0,0,0,.12); display:block; }

/* per-chunk metrics */
.mets{ border-top:1px solid var(--line-2); background:var(--blue-25); padding:.55rem .85rem .6rem; }
.mets-lab{ font-size:.6rem; text-transform:uppercase; letter-spacing:.07em; color:var(--faint); margin-bottom:.35rem; }
.mets-grid{ display:grid; grid-template-columns:repeat(auto-fit,minmax(84px,1fr)); gap:.4rem .5rem; }
.met .k{ font-size:.6rem; color:var(--muted); display:flex; justify-content:space-between; gap:.25rem; }
.met .k b{ color:var(--ink); font-variant-numeric:tabular-nums; font-weight:650; }
.met .bar{ height:3px; border-radius:2px; background:var(--blue-100); margin-top:.2rem; overflow:hidden; }
.met .bar i{ display:block; height:100%; background:var(--blue-600); border-radius:2px; }
.met.alt .bar i{ background:var(--blue-500); }

/* empty / info states */
.empty{
  border:1px dashed var(--line); border-radius:var(--radius); padding:1.6rem 1rem;
  text-align:center; color:var(--muted); font-size:.82rem; background:var(--blue-25);
}
.empty .ic{ font-size:1.4rem; display:block; margin-bottom:.4rem; opacity:.5; }
.empty b{ color:var(--ink-2); display:block; margin-bottom:.25rem; font-size:.86rem; }

.note{
  font-size:.72rem; color:var(--muted); background:var(--blue-25);
  border-left:3px solid var(--blue-500); border-radius:0 8px 8px 0; padding:.45rem .6rem; margin:.5rem 0;
}

/* thinking trace */
.trace-row{ display:flex; gap:.5rem; align-items:baseline; font-size:.78rem; padding:.13rem 0; }
.trace-row .d{ flex:none; width:6px; height:6px; border-radius:50%; background:var(--blue-500); }
.trace-row .l{ font-weight:600; color:var(--ink-2); }
.trace-row .x{ color:var(--muted); flex:1; }
.trace-row .t{ color:var(--faint); font-variant-numeric:tabular-nums; font-size:.7rem; }

/* ---------- streamlit widget polish ---------- */
[data-testid="stSidebarCollapseButton"] button, [data-testid="stSidebarCollapsedControl"] button{
  border-radius:8px;
}
.stButton>button{
  border-radius:9px; border:1px solid var(--line); background:#fff; color:var(--ink-2);
  font-size:.78rem; font-weight:550; padding:.3rem .6rem;
}
.stButton>button:hover{ border-color:var(--blue-500); color:var(--blue-700); background:var(--blue-25); }
[data-testid="stSidebar"] .stButton>button{ width:100%; text-align:left; }
div[data-testid="stExpander"] details{
  border:1px solid var(--line); border-radius:10px; background:#fff;
}
div[data-testid="stExpander"] summary{ font-size:.78rem; font-weight:550; }
[data-testid="stMetricValue"]{ font-size:1.05rem; color:var(--blue-700); }

/* the chat bar: keep it over the conversation column, not the report */
[data-testid="stBottomBlockContainer"]{
  background:linear-gradient(180deg,rgba(255,255,255,0),#fff 22%);
  padding-bottom:1rem;
}
[data-testid="stBottomBlockContainer"] .stChatInput{ max-width:none; }
[data-testid="stChatInput"]{ border-radius:11px; border:1px solid var(--line); box-shadow:var(--shadow); }
[data-testid="stChatInput"]:focus-within{ border-color:var(--blue-500); }

@media (min-width:1200px){
  [data-testid="stBottomBlockContainer"] > div{ padding-right:41%; }
  /* Pin the report column so long chunk lists scroll on their own. `top`
     clears the 60px app header, otherwise the panel heading and the summary
     metrics hide behind it at scroll top. */
  div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:last-child{
    align-self:flex-start; position:sticky; top:4.5rem;
    max-height:calc(100vh - 6.5rem); overflow-y:auto; overflow-x:hidden;
    padding-right:.35rem;
  }
  div[data-testid="stColumn"]:last-child::-webkit-scrollbar{ width:7px; }
  div[data-testid="stColumn"]:last-child::-webkit-scrollbar-thumb{
    background:var(--line); border-radius:4px;
  }
}
</style>
"""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def esc(text) -> str:
    return html.escape(str(text), quote=True)


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")


def _inline(text: str) -> str:
    """Escape, then re-enable the tiny bit of markdown the corpus uses."""
    out = esc(text)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    out = _CODE.sub(r"<code>\1</code>", out)
    return out


def highlight(text: str, terms) -> str:
    """Mark query terms inside already-escaped text."""
    out = _inline(text)
    for term in sorted({t for t in terms if len(t) > 3}, key=len, reverse=True):
        out = re.sub(
            r"(?<![\w>])(" + re.escape(esc(term)) + r")(?![\w<])",
            r"<mark>\1</mark>",
            out,
            flags=re.IGNORECASE,
        )
    return out


# ---------------------------------------------------------------------------
# Markdown tables -> HTML
# ---------------------------------------------------------------------------

_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _cells(line: str):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def is_table_line(line: str) -> bool:
    return line.lstrip().startswith("|") and line.count("|") >= 2


def md_table_to_html(markdown: str, caption: str = "") -> str:
    """Convert one GitHub-flavoured markdown table into a scrollable HTML table."""
    rows = [l for l in markdown.strip().split("\n") if l.strip()]
    if not rows:
        return ""
    header, body = None, []
    for i, line in enumerate(rows):
        if _SEP_RE.match(line) and i > 0:
            header = _cells(rows[i - 1])
            body = [_cells(r) for r in rows[i + 1:] if is_table_line(r)]
            break
    if header is None:
        header, body = _cells(rows[0]), [_cells(r) for r in rows[1:]]

    width = max([len(header)] + [len(r) for r in body] or [0])
    header += [""] * (width - len(header))

    thead = "".join(f"<th>{_inline(c)}</th>" for c in header)
    trs = []
    for row in body:
        row = row + [""] * (width - len(row))
        trs.append("".join(f"<td>{_inline(c)}</td>" for c in row))
    tbody = "".join(f"<tr>{r}</tr>" for r in trs)

    cap = f'<div class="tbl-cap">{esc(caption)}</div>' if caption else ""
    return (
        f'<div class="tbl-wrap">{cap}<div class="tbl-scroll"><table>'
        f"<thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody>"
        f"</table></div></div>"
    )


# ---------------------------------------------------------------------------
# Body prose -> HTML
# ---------------------------------------------------------------------------

_BULLETS = ("•", "▪", "‣", "·", "- ", "– ", "— ")


def _is_bullet(line: str) -> bool:
    s = line.strip()
    return bool(s) and (s.startswith(_BULLETS))


def _strip_bullet(line: str) -> str:
    s = line.strip()
    for b in _BULLETS:
        if s.startswith(b):
            return s[len(b):].strip()
    return s


def _is_heading(line: str, nxt: str) -> bool:
    """Decide whether a line is a section heading rather than wrapped prose.

    The source is hard-wrapped, so fragments like "POLIVY-R-C" or "HP" land on
    their own line and used to be mistaken for headings. Requiring several
    words, some lower case and a following line filters those out.
    """
    s = line.strip()
    if not s or not (8 <= len(s) <= 72) or _is_bullet(s):
        return False
    if s.endswith((".", ",", ";", ":", "?", "-", "/")):
        return False
    words = s.split()
    if not (2 <= len(words) <= 9):
        return False
    if not any(c.islower() for c in s):   # an all-caps fragment, not a heading
        return False
    if sum(c.isdigit() for c in s) > len(s) / 4:  # a run of table numbers
        return False
    titled = sum(1 for w in words if w[:1].isupper())
    return titled >= max(1, len(words) - 2) and bool(nxt.strip())


def _absorb_wrap(lines, i: int):
    """Rejoin a heading that the PDF wrapped onto a second line.

    Returns the heading text and the index of the line after it.
    """
    head = lines[i].strip()
    nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
    if (
        nxt
        and len(nxt.split()) <= 2
        and not nxt.endswith((".", ",", ";", ":", "?", "*"))
        and not _is_bullet(nxt)
        and len(head) + len(nxt) <= 90
        and nxt[:1].isupper()
    ):
        return f"{head} {nxt}", i + 2
    return head, i + 1


def _implicit_list(lines):
    """Recover a bullet list that the PDF exported as a caption grid.

    Figure captions come out as runs of very short lines where one label
    repeats ("Do NOT", "Grade", ...). Splitting on that repeated label turns an
    unreadable run-on paragraph back into the list it was drawn as. Returns
    None when the run is ordinary wrapped prose.
    """
    if len(lines) < 4:
        return None
    if sum(len(l) for l in lines) / len(lines) > 32:
        return None

    counts = {}
    for line in lines:
        counts[line] = counts.get(line, 0) + 1
    marker, hits = max(counts.items(), key=lambda kv: kv[1])
    if hits < 2 or not marker[:1].isupper() or len(marker.split()) > 3:
        return None

    items, current = [], []
    for line in lines:
        if line == marker:
            if current:
                items.append(" ".join(current))
            current = [line]
        elif current:
            current.append(line)
    if current:
        items.append(" ".join(current))
    return items if len(items) >= 2 else None


def body_to_html(text: str, terms=()) -> str:
    """Turn PDF-extracted prose into readable HTML.

    The source is hard-wrapped mid-sentence, so lines inside a paragraph are
    rejoined; blank lines, bullets and heading-shaped lines break the flow.
    """
    out = []
    para, bullets = [], []

    def flush_para():
        if not para:
            return
        items = _implicit_list(para)
        if items:
            body = "".join(f"<li>{highlight(x, terms)}</li>" for x in items)
            out.append(f"<ul>{body}</ul>")
        else:
            out.append(f"<p>{highlight(' '.join(para), terms)}</p>")
        para.clear()

    def flush_bullets():
        if bullets:
            items = "".join(f"<li>{highlight(b, terms)}</li>" for b in bullets)
            out.append(f"<ul>{items}</ul>")
            bullets.clear()

    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            flush_para()
            flush_bullets()
            i += 1
            continue

        # Lone glyphs (dingbats the extractor could not map) are noise.
        if len(stripped) == 1 and not stripped.isalnum():
            i += 1
            continue

        if is_table_line(line):
            block = []
            while i < len(lines) and is_table_line(lines[i]):
                block.append(lines[i])
                i += 1
            flush_para()
            flush_bullets()
            out.append(md_table_to_html("\n".join(block)))
            continue

        if _is_bullet(line):
            flush_para()
            bullets.append(_strip_bullet(line))
            i += 1
            continue

        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        starts_block = i == 0 or not lines[i - 1].strip()
        if starts_block and not para and _is_heading(line, nxt):
            flush_bullets()
            heading, i = _absorb_wrap(lines, i)
            out.append(f'<div class="sub-h">{highlight(heading, terms)}</div>')
            continue

        flush_bullets()
        para.append(stripped)
        i += 1

    flush_para()
    flush_bullets()
    if not out:
        return "<p>No body text in this section.</p>"
    return _clamp(out)


# Sections longer than this get their tail folded into a <details>. Some
# chunks run to 1,400+ words of PDF-flattened table text, which buries the
# next result if it is all rendered inline.
CLAMP_AFTER_CHARS = 1400


def _clamp(blocks) -> str:
    """Show the opening of a long section, fold the remainder away."""
    total = sum(len(b) for b in blocks)
    if total <= CLAMP_AFTER_CHARS or len(blocks) < 3:
        return "".join(blocks)

    head, running = [], 0
    for i, block in enumerate(blocks):
        head.append(block)
        running += len(block)
        if running >= CLAMP_AFTER_CHARS * 0.6:
            rest = blocks[i + 1:]
            break
    else:
        return "".join(blocks)

    if not rest:
        return "".join(head)
    return (
        "".join(head)
        + f"<details><summary>Show the rest of this section "
        f"({len(rest)} more block(s))</summary>{''.join(rest)}</details>"
    )


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def resolve_image(local_path: str):
    if not local_path:
        return None
    rel = Path(str(local_path).replace("\\", "/"))
    for root in IMAGE_ROOTS:
        candidate = root / rel
        if candidate.is_file():
            return candidate
    return None


def _data_uri(path: Path):
    try:
        if path.stat().st_size > MAX_IMAGE_BYTES:
            return None
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
    except Exception:
        return None


def images_to_html(images) -> str:
    """Render the section's figures as a grid of framed thumbnails.

    Files that were never shipped alongside the JSONL fall back to a
    placeholder that still names the page and the source path.
    """
    if not images:
        return ""
    shown = images[:MAX_IMAGES_PER_CHUNK]
    cards = []
    for img in shown:
        page = img.get("page_number", "?")
        kind = img.get("classification", "figure")
        path = resolve_image(img.get("local_path", ""))
        uri = _data_uri(path) if path else None
        if uri:
            cards.append(
                f'<figure class="img-frame"><div class="shot">'
                f'<img src="{uri}" alt="Figure from page {esc(page)}" loading="lazy"></div>'
                f'<figcaption class="cap"><span>p. {esc(page)}</span>'
                f"<span>{esc(kind)}</span></figcaption></figure>"
            )
        else:
            name = Path(str(img.get("local_path", "unknown"))).name
            cards.append(
                f'<div class="img-frame"><div class="img-miss">'
                f'<span class="ic">&#128443;</span>'
                f'<span class="t">Figure on p. {esc(page)} &middot; {esc(kind)}</span>'
                f'<span class="f">{esc(name)}</span></div>'
                f'<div class="cap"><span>not bundled</span>'
                f"<span>{esc(kind)}</span></div></div>"
            )
    extra = len(images) - len(shown)
    more = f'<div class="note">{extra} further figure(s) in this section not shown.</div>' if extra > 0 else ""
    return f'<div class="img-grid">{"".join(cards)}</div>{more}'


def swatches_to_html(swatches) -> str:
    if not swatches:
        return ""
    chips = []
    for item in swatches[:14]:
        if isinstance(item, (list, tuple)) and item:
            hex_code, count = str(item[0]), (item[1] if len(item) > 1 else "")
        else:
            hex_code, count = str(item), ""
        safe = hex_code if re.fullmatch(r"#[0-9A-Fa-f]{3,8}", hex_code) else "#CCCCCC"
        label = f"{esc(hex_code)}" + (f" &middot; {esc(count)}" if count != "" else "")
        chips.append(f'<span class="sw"><i style="background:{safe}"></i>{label}</span>')
    return f'<div class="sw-row">{"".join(chips)}</div>'


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _meter(label: str, value: float, display=None, alt=False) -> str:
    width = max(0.0, min(1.0, float(value))) * 100
    shown = display if display is not None else f"{value:.3f}"
    cls = "met alt" if alt else "met"
    return (
        f'<div class="{cls}"><div class="k"><span>{esc(label)}</span><b>{esc(shown)}</b></div>'
        f'<div class="bar"><i style="width:{width:.1f}%"></i></div></div>'
    )


def hit_metrics_html(hit) -> str:
    moved = hit.fusion_rank - hit.rank
    arrow = "&#8593;" if moved > 0 else ("&#8595;" if moved < 0 else "&#8722;")
    meters = "".join([
        _meter("Relevance", hit.relevance, pct(hit.relevance)),
        _meter("Rerank", hit.rerank, f"{hit.rerank:.3f}", alt=True),
        _meter("Vector cos", hit.dense, f"{hit.dense:.3f}", alt=True),
        _meter("BM25", hit.bm25, f"{hit.bm25:.3f}", alt=True),
        _meter("Fusion", hit.fusion, f"{hit.fusion:.3f}", alt=True),
        _meter("Term cover", hit.keyword_coverage, pct(hit.keyword_coverage), alt=True),
    ])
    detail = (
        f"logit {hit.rerank_logit:+.2f} &middot; fused rank {hit.fusion_rank} "
        f"&rarr; {hit.rank} {arrow} &middot; {hit.passages_hit} passage(s) matched"
    )
    return (
        f'<div class="mets"><div class="mets-lab">Retrieval metrics &middot; {detail}</div>'
        f'<div class="mets-grid">{meters}</div></div>'
    )


def summary_html(metrics: dict, timings: dict) -> str:
    conf = metrics.get("confidence", "-")
    cls = "conf-" + conf.replace(" ", "")
    boxes = [
        (pct(metrics["top_relevance"]), "Top relevance", ""),
        (pct(metrics["mean_relevance"]), f"Mean of {metrics['returned']}", ""),
        (conf, "Confidence", cls),
        (f"{timings.get('total_ms', 0):.0f} ms", "Latency", ""),
        (pct(metrics["margin"]), "Score margin", ""),
        (pct(metrics["coverage"]), "Term coverage", ""),
        (pct(metrics["agreement"]), "Retriever agree", ""),
        (str(metrics["scanned"]), "Passages scored", ""),
    ]
    cells = "".join(
        f'<div class="mbox {c}"><b>{esc(v)}</b><span>{esc(l)}</span></div>'
        for v, l, c in boxes
    )
    return f'<div class="mstrip">{cells}</div>'


# ---------------------------------------------------------------------------
# The chunk card
# ---------------------------------------------------------------------------

def chunk_card_html(hit) -> str:
    sec = hit.section
    terms = hit.matched_terms

    chips = []
    if sec.page_label:
        chips.append(f'<span class="chip">{esc(sec.page_label)}</span>')
    if sec.tables:
        chips.append(f'<span class="chip n">{len(sec.tables)} table(s)</span>')
    if sec.images:
        chips.append(f'<span class="chip n">{len(sec.images)} figure(s)</span>')
    chips.append(f'<span class="chip n">{sec.word_count} words</span>')
    for f in sec.matched_fields[:4]:
        chips.append(f'<span class="chip">{esc(f)}</span>')

    tables_html = "".join(
        md_table_to_html(t.get("markdown", ""), f"Table &middot; page {t.get('page_number', '?')}")
        for t in sec.tables
        if (t.get("markdown") or "").strip()
    )

    return (
        f'<div class="chunk">'
        f'<div class="chunk-top">'
        f'<div class="chunk-rank">{hit.rank}</div>'
        f'<div class="chunk-id"><div class="t">{esc(sec.section_label)}</div>'
        f'<div class="path">{esc(sec.chunk_id)}</div></div>'
        f'<div class="chunk-score"><b>{pct(hit.relevance)}</b><span>relevance</span></div>'
        f"</div>"
        f'<div class="chip-row">{"".join(chips)}</div>'
        f'<div class="chunk-body">'
        f"{body_to_html(sec.text, terms)}"
        f"{tables_html}"
        f"{images_to_html(sec.images)}"
        f"{swatches_to_html(sec.color_swatches)}"
        f"</div>"
        f"{hit_metrics_html(hit)}"
        f"</div>"
    )
