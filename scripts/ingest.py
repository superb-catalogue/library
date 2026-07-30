#!/usr/bin/env python3
"""Ingest every Standard Ebooks bulk-download zip into books/.

    python scripts/ingest.py                 # full run, all zips
    python scripts/ingest.py --archives DIR  # point at a different zip folder
    python scripts/ingest.py --time-one PATH_TO_EPUB   # time adding one book

Reads the zips in place; never moves, renames or modifies them. Writes only
under books/ (and books/INDEX.json, LIBRARY.md at the repo root) inside this
repository's own checkout.
"""
import argparse
import glob
import io
import json
import os
import sys
import time
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selib
from categories import category_for_genre, CATEGORY_ORDER

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKS_DIR = os.path.join(REPO_ROOT, "books")
INDEX_PATH = os.path.join(BOOKS_DIR, "INDEX.json")
LIBRARY_MD_PATH = os.path.join(REPO_ROOT, "LIBRARY.md")
DEFAULT_ARCHIVES = r"E:\archives"


def read_one_epub(zip_path, entry_name, data):
    """Parse a single EPUB's bytes into metadata + chapters. Returns a dict
    or raises, so the caller can turn a raise into a gate failure rather
    than crashing the whole run."""
    ez = zipfile.ZipFile(io.BytesIO(data))
    opf_path = selib.find_opf_path(ez)
    opf_dir = os.path.dirname(opf_path).replace("\\", "/")
    opf_text = ez.read(opf_path).decode("utf-8")
    root = ET.fromstring(opf_text)
    meta = selib.parse_metadata(root)
    if not selib.is_standardebooks_identifier(meta["identifier"]):
        raise ValueError(
            "identifier is not a resolvable Standard Ebooks page in %s!%s: %r"
            % (zip_path, entry_name, meta["identifier"])
        )
    if not selib.is_genuine_public_domain_dedication(meta["rights"]):
        raise ValueError("no genuine public-domain / CC0 dedication in %s!%s" % (zip_path, entry_name))

    spine = selib.parse_manifest_spine(root)
    chapters = selib.extract_chapters(ez, opf_dir, spine)
    if not chapters:
        raise ValueError("reading order resolved to zero chapters in %s!%s" % (zip_path, entry_name))

    return {
        "meta": meta,
        "chapters": chapters,
        "zip_path": zip_path,
        "entry_name": entry_name,
        "sha256": selib.sha256_of(data),
    }


def gate(record):
    """The door gate: three checks, in seconds, nothing heavier.
    Returns (passed, reason)."""
    meta = record["meta"]
    if not selib.is_standardebooks_identifier(meta.get("identifier")):
        return False, "identifier is not a resolvable Standard Ebooks page"
    if not selib.is_genuine_public_domain_dedication(meta.get("rights")):
        return False, "no genuine public-domain / CC0 dedication in metadata"
    if not record.get("chapters"):
        return False, "reading order did not resolve to any chapters"
    return True, "ok"


def build_book_and_provenance(record, sets):
    meta = record["meta"]
    chapters = record["chapters"]
    words = selib.count_words(chapters)

    book = {
        "title": meta["title"],
        "author": ", ".join(meta["creators"]) if meta["creators"] else None,
        "language": meta["language"],
        "chapters": [
            {"label": ch["label"], "types": ch["types"], "blocks": ch["blocks"]}
            for ch in chapters
        ],
    }

    outer_zip_name = os.path.basename(record["zip_path"])
    genres = meta.get("genres") or []
    genre = genres[0] if genres else None
    provenance = {
        "title": meta["title"],
        "author": ", ".join(meta["creators"]) if meta["creators"] else None,
        "identifier": meta["identifier"],
        "edition": {
            "publisher": "Standard Ebooks",
            "page": meta["identifier"],
            "published": meta["date"],
            "modified": meta["modified"],
        },
        "made_from": meta["sources"],
        "terms": {
            "licence": "CC0 1.0 Universal (public domain dedication)",
            "as_stated_by_the_edition": meta["rights"],
            "read_at": meta["identifier"],
        },
        "genre": genre,
        "genres": genres,
        "category": category_for_genre(genre),
        "sets": sets,
        "how_we_got_it": {
            "route": "Standard Ebooks bulk download (Patrons Circle)",
            "collection": outer_zip_name,
            "epub_sha256": record["sha256"],
        },
        "text": {
            "file": "book.json",
            "chapters": len(chapters),
            "words": words,
            "front_and_back_matter": (
                "not included — the publisher's title page, imprint and "
                "colophon are theirs, not the book's"
            ),
        },
    }
    return book, provenance, words


def scan_archives(archives_dir):
    """First pass: read every inner epub's metadata (cheap) across every
    outer zip. Returns (records_by_identifier, files_seen)."""
    files_seen = 0
    by_identifier = {}
    zip_paths = sorted(glob.glob(os.path.join(archives_dir, "*.zip")))
    for zpath in zip_paths:
        outer = zipfile.ZipFile(zpath)
        for name in outer.namelist():
            if not name.endswith(".epub"):
                continue
            files_seen += 1
            data = outer.read(name)
            try:
                rec = read_one_epub(zpath, name, data)
            except Exception as exc:  # noqa: BLE001 — gate failure, reported below
                print("SKIPPED (gate): %s!%s -- %s" % (zpath, name, exc))
                continue
            ident = rec["meta"]["identifier"]
            by_identifier.setdefault(ident, []).append(rec)
    return by_identifier, files_seen, len(zip_paths)


def pick_newest(records):
    """Same identifier, possibly several builds (Standard Ebooks rebuilds
    books over time). The newest dcterms:modified wins; ties keep the first
    one seen and say so."""

    def sort_key(r):
        return r["meta"].get("modified") or r["meta"].get("date") or ""

    ordered = sorted(records, key=sort_key, reverse=True)
    winner = ordered[0]
    superseded = ordered[1:]
    return winner, superseded


def merge_sets(records):
    seen = {}
    for r in records:
        for c in r["meta"]["collections"]:
            seen.setdefault(c["name"], c)
    return list(seen.values())


def run_full_ingest(archives_dir):
    t0 = time.time()
    by_identifier, files_seen, zip_count = scan_archives(archives_dir)
    unique_works = len(by_identifier)
    duplicates_collapsed = files_seen - unique_works

    os.makedirs(BOOKS_DIR, exist_ok=True)
    index_rows = []
    gate_failures = []
    rebuilds_noted = 0

    for ident, records in sorted(by_identifier.items()):
        winner, superseded = pick_newest(records)
        if superseded:
            distinct_shas = {r["sha256"] for r in records}
            if len(distinct_shas) > 1:
                rebuilds_noted += 1
        sets = merge_sets(records)

        passed, reason = gate(winner)
        if not passed:
            gate_failures.append((ident, reason))
            continue

        book, provenance, words = build_book_and_provenance(winner, sets)
        if superseded:
            distinct_shas = {r["sha256"] for r in records}
            if len(distinct_shas) > 1:
                provenance["how_we_got_it"]["superseded_build"] = (
                    "%d other build(s) of this identifier were seen across the "
                    "archives; the newest (by dcterms:modified) was kept."
                    % len(superseded)
                )

        slug = selib.slug_from_identifier(ident)
        book_dir = os.path.join(BOOKS_DIR, slug)
        os.makedirs(book_dir, exist_ok=True)
        with open(os.path.join(book_dir, "book.json"), "w", encoding="utf-8") as f:
            json.dump(book, f, ensure_ascii=False, indent=2)
        with open(os.path.join(book_dir, "provenance.json"), "w", encoding="utf-8") as f:
            json.dump(provenance, f, ensure_ascii=False, indent=2)

        index_rows.append(
            {
                "slug": slug,
                "title": book["title"],
                "author": book["author"],
                "edition_published": provenance["edition"]["published"],
                "category": provenance["category"],
                "genre": provenance["genre"],
                "sets": [s["name"] for s in sets],
                "page": ident,
                "book": "books/%s/book.json" % slug,
                "provenance": "books/%s/provenance.json" % slug,
                "chapters": provenance["text"]["chapters"],
                "words": words,
            }
        )

    index_rows.sort(key=lambda r: (r["category"], r["title"] or ""))
    index = {
        "generated_from": "scripts/ingest.py",
        "arithmetic": {
            "files_seen": files_seen,
            "zips": zip_count,
            "unique_works": unique_works,
            "duplicates_collapsed": duplicates_collapsed,
        },
        "works": index_rows,
    }
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    write_library_md(index)

    elapsed = time.time() - t0
    print("files seen across all zips: %d" % files_seen)
    print("unique works: %d" % unique_works)
    print("duplicates collapsed: %d" % duplicates_collapsed)
    print(
        "reconciles: %d files seen == %d unique + %d duplicates collapsed -> %s"
        % (
            files_seen,
            unique_works,
            duplicates_collapsed,
            files_seen == unique_works + duplicates_collapsed,
        )
    )
    print("works with more than one build seen: %d" % rebuilds_noted)
    if gate_failures:
        print("gate failures (excluded from the shelf): %d" % len(gate_failures))
        for ident, reason in gate_failures:
            print("  %s -- %s" % (ident, reason))
    print("elapsed: %.1fs for %d works (%.3fs/work average)" % (elapsed, unique_works, elapsed / max(unique_works, 1)))
    return index


def write_library_md(index):
    lines = []
    lines.append("# The shelf")
    lines.append("")
    lines.append(
        "One row per book, generated from `books/INDEX.json` — never edited by "
        "hand. Regenerate with `python scripts/ingest.py` and a check fails if "
        "this file drifts from that regeneration."
    )
    lines.append("")
    lines.append(
        "The categories are the library's own — see `CATEGORIES.md` for what "
        "they are and why. `edition published` is the date Standard Ebooks "
        "published this typesetting, not necessarily the year the book was "
        "first written or printed."
    )
    lines.append("")
    by_cat = {}
    for row in index["works"]:
        by_cat.setdefault(row["category"], []).append(row)

    ordered_cats = [c for c in CATEGORY_ORDER if c in by_cat] + sorted(
        c for c in by_cat if c not in CATEGORY_ORDER
    )
    for cat in ordered_cats:
        rows = sorted(by_cat[cat], key=lambda r: (r["title"] or ""))
        lines.append("## %s (%d)" % (cat, len(rows)))
        lines.append("")
        lines.append("| Title | Author | Edition published | Also in |")
        lines.append("|---|---|---|---|")
        for r in rows:
            also_in = ", ".join(s for s in r["sets"]) or "—"
            lines.append(
                "| [%s](books/%s/provenance.json) | %s | %s | %s |"
                % (r["title"] or "—", r["slug"], r["author"] or "—", (r["edition_published"] or "—")[:10], also_in)
            )
        lines.append("")

    with open(LIBRARY_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def cmd_time_one(epub_path):
    """Add one book, and report a clean gate failure rather than a raw
    traceback if the file can't be read at all — a gate that crashes has
    not rejected anything, it has stopped. Returns 0 on success, 1 on a
    reported gate failure."""
    t0 = time.time()
    try:
        with open(epub_path, "rb") as f:
            data = f.read()
        rec = read_one_epub(epub_path, os.path.basename(epub_path), data)
    except Exception as exc:  # noqa: BLE001 — any failure here is a gate rejection, not a crash
        elapsed = time.time() - t0
        print("gate: False (%s)" % exc)
        print("elapsed: %.3fs" % elapsed)
        return 1

    passed, reason = gate(rec)
    if not passed:
        elapsed = time.time() - t0
        print("gate: False (%s)" % reason)
        print("elapsed: %.3fs" % elapsed)
        return 1

    book, provenance, words = build_book_and_provenance(rec, sets=merge_sets([rec]))
    slug = selib.slug_from_identifier(rec["meta"]["identifier"])
    book_dir = os.path.join(BOOKS_DIR, slug)
    os.makedirs(book_dir, exist_ok=True)
    with open(os.path.join(book_dir, "book.json"), "w", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, indent=2)
    with open(os.path.join(book_dir, "provenance.json"), "w", encoding="utf-8") as f:
        json.dump(provenance, f, ensure_ascii=False, indent=2)
    elapsed = time.time() - t0
    print("gate: %s (%s)" % (passed, reason))
    print("wrote books/%s/{book.json,provenance.json} — %d chapters, %d words" % (slug, provenance["text"]["chapters"], words))
    print("elapsed: %.3fs" % elapsed)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archives", default=DEFAULT_ARCHIVES)
    ap.add_argument("--time-one", metavar="EPUB_PATH", help="ingest a single .epub file and time it")
    args = ap.parse_args()

    if args.time_one:
        return cmd_time_one(args.time_one)

    run_full_ingest(args.archives)
    return 0


if __name__ == "__main__":
    sys.exit(main())
