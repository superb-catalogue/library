#!/usr/bin/env python3
"""Export a versioned, app-facing catalogue artifact from books/.

This does NOT hand the app this repository's internal per-book shape
(book.json + provenance.json, documented in books/HOW-THE-FIRST-BOOK-WENT.md).
That shape is this repository's own working format and is free to change as
more books and text shapes are ingested. The artifact this script writes is
a separate, versioned contract: `catalogue-<version>.json` plus a `.sha256`
sidecar, meant to be pinned by tag/commit/checksum from the app side
(content/catalogue.lock.json in kihea/superb) rather than read live.

    python scripts/export_catalogue.py --slug bram-stoker_dracula

Writes dist/catalogue-<version>.json and dist/catalogue-<version>.sha256.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKS_DIR = os.path.join(REPO_ROOT, "books")
DIST_DIR = os.path.join(REPO_ROOT, "dist")
SCHEMA_VERSION = "0.1.0"

# Block types that carry a book's own reading text, in the order
# read_one_epub (ingest.py) already established. Everything else under a
# chapter's own "header" block (ordinal+roman, bridgehead) is the chapter's
# own heading material, kept separately rather than mixed into the parts a
# reading surface tokenizes -- see `heading` below.
HEADING_TYPES = {"ordinal+roman", "bridgehead"}


def repo_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
    ).strip()


def flatten_text_blocks(blocks, out):
    """Depth-first walk collecting every block that carries its own `text` --
    paragraph, letter salutation/valediction, verse lines, diary dateline,
    etc. -- in document order. HOW-THE-FIRST-BOOK-WENT.md #5 already accepted
    this loss for the first book ("only paragraphs survived"); this export
    keeps each block's own `type` alongside its text rather than collapsing
    them to bare strings, so a later slice can tell a letter's valediction
    from an ordinary paragraph without this script having to be rewritten."""
    for block in blocks:
        if "text" in block and block["type"] not in HEADING_TYPES:
            out.append({"type": block["type"], "text": block["text"]})
        if "blocks" in block:
            flatten_text_blocks(block["blocks"], out)


def heading_lines(blocks):
    lines = []
    for block in blocks:
        if block.get("type") == "header":
            for inner in block.get("blocks", []):
                if inner.get("type") == "bridgehead":
                    lines.append(inner["text"])
    return lines


def export_book(slug: str) -> dict:
    book_dir = os.path.join(BOOKS_DIR, slug)
    with open(os.path.join(book_dir, "book.json"), encoding="utf-8") as f:
        book = json.load(f)
    with open(os.path.join(book_dir, "provenance.json"), encoding="utf-8") as f:
        prov = json.load(f)

    parts = []
    for index, chapter in enumerate(book["chapters"]):
        text_blocks: list = []
        flatten_text_blocks(chapter["blocks"], text_blocks)
        parts.append(
            {
                "index": index,
                "label": chapter["label"],
                "heading": heading_lines(chapter["blocks"]),
                "blocks": text_blocks,
            }
        )

    word_count = sum(len(b["text"].split()) for p in parts for b in p["blocks"])

    return {
        "id": slug,
        "title": book["title"],
        "author": book["author"],
        "translator": prov.get("translator"),
        "language": book["language"],
        "shape": "prose",
        "wordCount": word_count,
        "parts": parts,
        "provenance": {
            "workPage": prov["identifier"],
            "publisher": prov["edition"]["publisher"],
            "editionPublished": prov["edition"]["published"],
            "madeFrom": prov["made_from"],
            "licence": prov["terms"]["licence"],
            "licenceUri": prov["terms"]["licence_uri"],
            "asStatedByTheEdition": prov["terms"]["as_stated_by_the_edition"],
        },
    }


def build(slugs: list[str]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {
            "repository": "https://github.com/superb-catalogue/library",
            "commit": repo_commit(),
        },
        "books": [export_book(slug) for slug in slugs],
    }


def write(catalogue: dict, version: str) -> tuple[str, str]:
    os.makedirs(DIST_DIR, exist_ok=True)
    json_path = os.path.join(DIST_DIR, f"catalogue-{version}.json")
    body = json.dumps(catalogue, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(body)

    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    sha_path = os.path.join(DIST_DIR, f"catalogue-{version}.sha256")
    with open(sha_path, "w", encoding="utf-8") as f:
        f.write(f"{digest}  catalogue-{version}.json\n")

    return json_path, sha_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", action="append", required=True, help="A books/<slug> to include; repeatable.")
    parser.add_argument("--version", default=SCHEMA_VERSION)
    args = parser.parse_args()

    catalogue = build(args.slug)
    json_path, sha_path = write(catalogue, args.version)
    digest = open(sha_path, encoding="utf-8").read().split()[0]
    print(f"wrote {json_path}")
    print(f"wrote {sha_path}")
    print(f"sha256: {digest}")


if __name__ == "__main__":
    main()
