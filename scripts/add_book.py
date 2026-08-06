#!/usr/bin/env python3
"""Add one prepared book to the shelf by hand.

    python scripts/add_book.py prepared.json

The input is a "prepared book": one JSON file holding the pair this
repository keeps per book, written by whatever produced the text --
scripts/prepare_patent.py, scripts/prepare_gutenberg.py, or a person:

    { "slug": "author_title",
      "book": { title, author, language, chapters: [...] },
      "provenance": { ... } }

This is the path README.md promises for books that do not arrive as
Standard Ebooks epubs. It runs its own gate, then writes
books/<slug>/{book.json,provenance.json}, adds a row to books/INDEX.json
marked "route": "hand", and regenerates LIBRARY.md. A full re-ingest of
the Standard Ebooks archives preserves hand-added rows (see ingest.py).

The gate here mirrors what the epub gate can honestly check, adapted to
sources that are not epubs: the provenance must cite terms this library
accepts, at a page someone can resolve for themselves, with the source's
own words quoted -- rule 3, "the terms were read, not assumed", recorded
rather than implied. It cannot confirm the claim is true, for the same
reason the epub gate cannot; README.md says so out loud.
"""
import argparse
import json
import os
import re
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from categories import CATEGORY_ORDER  # noqa: E402
from ingest import BOOKS_DIR, INDEX_PATH, write_library_md  # noqa: E402
from selib import ACCEPTED_HAND_TERMS_URIS as ACCEPTED_TERMS_URIS  # noqa: E402


def _fail(msg):
    print("gate: False (%s)" % msg)
    return 1


def _resolvable_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def count_words(chapters):
    n = 0
    for ch in chapters:
        for b in ch.get("blocks", []):
            n += len(re.findall(r"\S+", b.get("text", "")))
    return n


def gate(prepared):
    """Returns (passed, reason). Everything here is checkable from the file
    itself; nothing here claims to have verified copyright at the source."""
    slug = prepared.get("slug")
    if not slug or not re.fullmatch(r"[a-z0-9-]+_[a-z0-9_-]+", slug):
        return False, "slug missing or not in author_title form: %r" % slug
    book = prepared.get("book") or {}
    prov = prepared.get("provenance") or {}
    if not book.get("title") or not book.get("language"):
        return False, "book.title and book.language are required"
    chapters = book.get("chapters") or []
    if not chapters or not any(b.get("text", "").strip()
                               for ch in chapters for b in ch.get("blocks", [])):
        return False, "reading order resolved to no readable text"
    if not _resolvable_url(prov.get("identifier")):
        return False, "provenance.identifier is not a resolvable page"
    terms = prov.get("terms") or {}
    uri = terms.get("licence_uri")
    if uri not in ACCEPTED_TERMS_URIS:
        return False, "terms.licence_uri is not one this library accepts: %r" % uri
    if not (terms.get("as_stated_by_the_source") or "").strip():
        return False, "terms.as_stated_by_the_source is empty -- the terms have to be quoted, not assumed"
    if not _resolvable_url(terms.get("read_at")):
        return False, "terms.read_at is not a resolvable page"
    if prov.get("category") not in CATEGORY_ORDER:
        return False, "category %r is not on the shelf (see CATEGORIES.md)" % prov.get("category")
    return True, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prepared", help="path to a prepared-book JSON file")
    args = ap.parse_args()

    with open(args.prepared, "r", encoding="utf-8") as f:
        prepared = json.load(f)

    passed, reason = gate(prepared)
    if not passed:
        return _fail(reason)

    slug = prepared["slug"]
    book = prepared["book"]
    prov = prepared["provenance"]
    words = count_words(book["chapters"])
    prov.setdefault("text", {})
    prov["text"].update({"file": "book.json", "chapters": len(book["chapters"]), "words": words})

    book_dir = os.path.join(BOOKS_DIR, slug)
    os.makedirs(book_dir, exist_ok=True)
    with open(os.path.join(book_dir, "book.json"), "w", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, indent=2)
    with open(os.path.join(book_dir, "provenance.json"), "w", encoding="utf-8") as f:
        json.dump(prov, f, ensure_ascii=False, indent=2)

    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        index = json.load(f)
    row = {
        "slug": slug,
        "title": book["title"],
        "author": book.get("author"),
        "edition_published": (prov.get("edition") or {}).get("published"),
        "category": prov["category"],
        "genre": prov.get("genre"),
        "sets": [s["name"] for s in prov.get("sets") or []],
        "page": prov["identifier"],
        "book": "books/%s/book.json" % slug,
        "provenance": "books/%s/provenance.json" % slug,
        "chapters": len(book["chapters"]),
        "words": words,
        "route": "hand",
    }
    index["works"] = [r for r in index["works"] if r["slug"] != slug] + [row]
    index["works"].sort(key=lambda r: (r["category"], r["title"] or ""))
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    write_library_md(index)

    print("gate: True (ok)")
    print("wrote books/%s/{book.json,provenance.json} -- %d chapters, %d words" % (slug, len(book["chapters"]), words))
    print("books/INDEX.json and LIBRARY.md updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
