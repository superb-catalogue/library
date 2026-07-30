#!/usr/bin/env python3
"""The door gate for one book: three checks, in seconds, nothing heavier.

    python scripts/gate.py books/bram-stoker_dracula
    python scripts/gate.py books/*            # every folder under books/

This is deliberately the whole gate — no corpus-wide analysis, no band-word
scans, no cross-library measurement. Kihea was explicit that a slow add
path is a reason not to use the workflow at all, and a book is inert text
with a citation: the two risks worth checking are "may we publish this" and
"is the file intact," and both are answerable in seconds.

What "may we publish this" means here, precisely: the book's own rights
metadata cites a licence URI this library has agreed to accept
(scripts/selib.py's ACCEPTED_LICENCE_URIS). That confirms the book SAYS it
is free under a licence this library allows — it does not and cannot
confirm the claim is true. No reading of a file's contents can do that; a
forger can write a flawless dedication into a copyrighted book and no
phrase list or pattern match would ever tell the difference, because the
words would be exactly the words a genuine one uses. The claim itself is
verified once, against the book's own public page at Standard Ebooks, when
the book is chosen for the shelf (books/HOW-THE-FIRST-BOOK-WENT.md) — the
same rule this library already applies to every other provenance citation.
A book from a source this library doesn't already trust needs that
page-level check before it is added; this gate is not, and was never meant
to be, a substitute for it.
"""
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selib  # noqa: E402


def check_book_folder(folder):
    reasons = []
    book_path = os.path.join(folder, "book.json")
    prov_path = os.path.join(folder, "provenance.json")

    if not os.path.exists(book_path):
        return ["no book.json"]
    if not os.path.exists(prov_path):
        return ["no provenance.json"]

    try:
        with open(book_path, "r", encoding="utf-8") as f:
            book = json.load(f)
    except Exception as exc:  # noqa: BLE001
        return ["book.json does not parse: %s" % exc]

    try:
        with open(prov_path, "r", encoding="utf-8") as f:
            prov = json.load(f)
    except Exception as exc:  # noqa: BLE001
        return ["provenance.json does not parse: %s" % exc]

    # identifier and provenance are extractable, and resolve to a real page
    if not selib.is_standardebooks_identifier(prov.get("identifier")):
        reasons.append("provenance.identifier is not a resolvable standardebooks.org page")
    if not prov.get("terms", {}).get("read_at"):
        reasons.append("no citable public page in provenance.terms.read_at")

    # the recorded rights text cites a licence URI this library accepts —
    # a structural check, not a reading of the prose around it
    stated = prov.get("terms", {}).get("as_stated_by_the_edition", "")
    if not selib.is_genuine_public_domain_dedication(stated):
        reasons.append("no accepted licence URI recorded in provenance.terms.as_stated_by_the_edition")

    # the file parses and its reading order resolves
    chapters = book.get("chapters", [])
    if not chapters:
        reasons.append("book.json has no chapters — reading order did not resolve")
    else:
        for i, ch in enumerate(chapters):
            if "blocks" not in ch:
                reasons.append("chapter %d has no blocks" % i)
                break

    return reasons


def main():
    args = sys.argv[1:]
    if not args:
        args = sorted(glob.glob(os.path.join("books", "*")))
        args = [a for a in args if os.path.isdir(a)]

    t0 = time.time()
    failed = 0
    for folder in args:
        if not os.path.isdir(folder):
            continue
        reasons = check_book_folder(folder)
        if reasons:
            failed += 1
            print("FAIL %s" % folder)
            for r in reasons:
                print("  - %s" % r)
        else:
            print("ok   %s" % folder)
    elapsed = time.time() - t0
    print("gate: %d folder(s) in %.3fs (%.4fs/book)" % (len(args), elapsed, elapsed / max(len(args), 1)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
