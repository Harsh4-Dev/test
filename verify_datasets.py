"""Prove the app is not tied to one corpus.

Builds several deliberately different JSONL files in a temp directory, runs
each one through the real engine, and checks it loads, indexes, retrieves and
renders. Also runs whatever is actually sitting in dataset/.

    python verify_datasets.py

Exits non-zero if any corpus fails.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import rag_core
import ui
from rag_core import RagEngine, list_datasets

# Each case is (filename, rows, probe query, expected top section label).
# The schemas differ on purpose: different text keys, different title keys,
# missing ids, missing pages, duplicate ids, blank and corrupt lines.
CASES = [
    (
        "langchain_style.jsonl",
        [
            {"page_content": "Deployments\nA Deployment provides declarative updates "
                             "for Pods and ReplicaSets. You describe a desired state "
                             "and the controller changes the actual state to the "
                             "desired state at a controlled rate.",
             "title": "Deployments"},
            {"page_content": "Services\nAn abstract way to expose an application "
                             "running on a set of Pods as a network service. "
                             "ClusterIP is the default service type.",
             "title": "Services"},
            {"page_content": "Horizontal Pod Autoscaling\nThe HorizontalPodAutoscaler "
                             "automatically updates a workload resource, scaling it "
                             "to match demand, based on observed CPU utilisation or "
                             "custom metrics.",
             "title": "Horizontal Pod Autoscaling"},
            {"page_content": "Persistent Volumes\nA PersistentVolume is storage in "
                             "the cluster provisioned by an administrator or "
                             "dynamically provisioned using Storage Classes.",
             "title": "Persistent Volumes"},
        ],
        "how do I automatically scale pods based on CPU",
        "Horizontal Pod Autoscaling",
    ),
    (
        "minimal_text_only.jsonl",
        [
            {"text": "Espresso is brewed by forcing near-boiling water at nine bars "
                     "of pressure through finely ground coffee, yielding about 36 "
                     "grams of liquid in 25 to 30 seconds."},
            {"text": "A pour-over uses gravity rather than pressure. Water at about "
                     "94 degrees is poured over a medium grind in a cone filter over "
                     "three to four minutes."},
            {"text": "Cold brew steeps coarse grounds in cold water for twelve to "
                     "twenty-four hours. It is lower in acidity because the sour "
                     "compounds are less soluble at low temperatures."},
        ],
        "why is cold brew less acidic",
        None,  # no titles in this corpus, so only check that it retrieves
    ),
    (
        "awkward_schema.jsonl",
        [
            {"id": "dup", "heading": "Article One", "content":
                "All human beings are born free and equal in dignity and rights."},
            {"id": "dup", "heading": "Article Two", "content":
                "Everyone is entitled to all the rights and freedoms set forth in "
                "this Declaration, without distinction of any kind."},
            {"id": "three", "heading": "Article Three", "content":
                "Everyone has the right to life, liberty and security of person."},
            {"content": "No one shall be held in slavery or servitude; slavery and "
                        "the slave trade shall be prohibited in all their forms."},
        ],
        "right to life and liberty",
        "Article Three",
    ),
]


def write_corpus(directory: Path, name: str, rows, junk=False) -> Path:
    path = directory / name
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        if junk:
            # A blank line and a corrupt line must be skipped, not fatal.
            fh.write("\n")
            fh.write("{this is not valid json,,,\n")
            fh.write("   \n")
    return path


def check(path: Path, persist: Path, query: str, expect_top) -> bool:
    label = path.name
    try:
        engine = RagEngine(path, persist_dir=persist)
    except Exception as exc:
        print(f"  FAIL  {label}: {type(exc).__name__}: {exc}")
        return False

    stats = engine.stats()
    result = engine.search(query, top_k=3)

    problems = []
    if stats["sections"] == 0:
        problems.append("no chunks loaded")
    if len({s.chunk_id for s in engine.sections}) != len(engine.sections):
        problems.append("duplicate chunk ids")
    if not result.hits:
        problems.append("query returned nothing")
    if expect_top and result.hits and result.hits[0].section.section_label != expect_top:
        problems.append(
            f"top hit was {result.hits[0].section.section_label!r}, "
            f"expected {expect_top!r}"
        )
    try:
        html = "".join(ui.chunk_card_html(h) for h in result.hits)
        if not html:
            problems.append("renderer produced nothing")
    except Exception as exc:
        problems.append(f"renderer raised {type(exc).__name__}: {exc}")

    top = result.hits[0] if result.hits else None
    print(f"  {'FAIL' if problems else 'ok  '}  {label}")
    print(f"          {stats['name']!r} - {stats['sections']} chunks -> "
          f"{stats['passages']} passages - {stats['words']} words")
    if top:
        print(f"          {query!r} -> {top.section.section_label!r} "
              f"at {top.relevance * 100:.0f}% ({result.metrics['confidence']}), "
              f"{result.timings['total_ms']:.0f} ms")
    for p in problems:
        print(f"          ! {p}")
    return not problems


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="rag_verify_"))
    persist = tmp / "chroma"
    passed = failed = 0

    try:
        print(f"\nSynthetic corpora  (temp dir: {tmp})")
        for name, rows, query, expect in CASES:
            path = write_corpus(tmp, name, rows, junk=name.startswith("awkward"))
            if check(path, persist, query, expect):
                passed += 1
            else:
                failed += 1

        print("\nCorpora actually in dataset/")
        real = list_datasets()
        if not real:
            print(f"  (none found in {rag_core.DATASET_DIR})")
        for path in real:
            if check(path, persist, "overview of the main topics", None):
                passed += 1
            else:
                failed += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
