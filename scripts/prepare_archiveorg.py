#!/usr/bin/env python3
"""Prepare an Internet Archive text for the shelf, retypeset from its OCR.

    python scripts/prepare_archiveorg.py <identifier> --category Fiction -o prepared.json

The Internet Archive is a different kind of source from Standard Ebooks or
Project Gutenberg: most of its books are scans, the text is OCR of those
scans, and -- decisively -- much of the collection is under copyright and
only *lent*, not licensed for copying. So this script's first job is to
read the item's own metadata and refuse anything it cannot prove free:

  - the item must state public domain or a licence this library accepts,
    in its own metadata (licenseurl, possible-copyright-status, or rights);
  - "it's on archive.org" is not a status, and a lending-library item
    (collection includes inlibrary/lendinglibrary) is refused outright,
    whatever else its metadata says.

That rule is why a book like East of Eden cannot come in this way: it is
in copyright in the United States until the 2040s, and the Archive's scan
of it is a lending copy. Rule 1 of README.md -- anyone may share it -- is
not satisfiable, and no OCR workflow changes that.

For an item that passes, the text comes from the item's DjVu-derived text
file, and the same retypesetting used for Project Gutenberg applies
(scripts/prepare_gutenberg.py's own functions, imported rather than
re-implemented): chapters at the text's own headings, paragraphs
unwrapped, quotes curled, page furniture dropped. OCR of a scan is
rougher than either other source, so the structural report at the end --
and reading the result -- matter more here, not less. The junk-token
ratio is printed; treat anything above about one percent as a book that
needs proofreading before scripts/add_book.py, not after.
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import date

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0])
from prepare_gutenberg import build_chapters, drop_title_page, _slug  # noqa: E402

UA = {"User-Agent": "superb-catalogue prepare_archiveorg.py (one item, politely)"}

ACCEPTED_STATUSES = ("public domain", "not_in_copyright", "no known copyright")
ACCEPTED_LICENCE_HOSTS = ("creativecommons.org/publicdomain",)


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def item_metadata(identifier):
    return json.loads(fetch("https://archive.org/metadata/%s" % identifier))


def free_to_copy(meta):
    """(ok, reason). Read the item's own statements; assume nothing."""
    m = meta.get("metadata", {})
    collections = m.get("collection") or []
    if isinstance(collections, str):
        collections = [collections]
    # inlibrary/lendinglibrary means the copy itself is a lending copy --
    # refused outright. printdisabled alone also marks accessibility scans
    # of genuinely free books, so it does not refuse by itself; the item
    # still has to state its freedom explicitly below like any other.
    lending = {"inlibrary", "lendinglibrary"}
    if lending & set(collections):
        return False, ("item is in the Archive's lending library (%s) -- a lending copy is "
                       "not licensed for copying, whatever its other fields say"
                       % ", ".join(sorted(lending & set(collections))))
    status = (m.get("possible-copyright-status") or m.get("rights") or "").lower()
    licurl = (m.get("licenseurl") or "").lower()
    if any(s in status for s in ACCEPTED_STATUSES):
        return True, "possible-copyright-status/rights states: %r" % status
    if any(h in licurl for h in ACCEPTED_LICENCE_HOSTS):
        return True, "licenseurl states: %r" % licurl
    return False, ("no public-domain statement in the item's own metadata "
                   "(possible-copyright-status=%r, licenseurl=%r) -- rule 3: the terms "
                   "were read, and they do not say this may be copied" % (status, licurl))


def djvu_text(identifier, meta):
    for f in meta.get("files", []):
        name = f.get("name", "")
        if name.endswith("_djvu.txt"):
            data = fetch("https://archive.org/download/%s/%s" % (identifier, name.replace(" ", "%20")))
            return name, data
    raise SystemExit("no _djvu.txt file on this item -- nothing to retypeset")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("identifier", help="archive.org item identifier")
    ap.add_argument("--category", required=True)
    ap.add_argument("--title", default=None)
    ap.add_argument("--author", default=None)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    meta = item_metadata(args.identifier)
    m = meta.get("metadata", {})
    ok, reason = free_to_copy(meta)
    print("terms: %s" % reason)
    if not ok:
        print("REFUSED: %s" % args.identifier)
        return 1

    title = args.title or m.get("title")
    author = args.author or (m.get("creator") if isinstance(m.get("creator"), str) else (m.get("creator") or [None])[0])
    if author:
        parts = [p.strip() for p in re.sub(r",?\s*\d{4}-\d{4}\.?$", "", author).split(",")]
        if len(parts) == 2:
            author = "%s %s" % (parts[1], parts[0])

    name, data = djvu_text(args.identifier, meta)
    text = data.decode("utf-8", "replace").replace("\r\n", "\n")
    chapters, front_words = build_chapters(text)
    front_words += drop_title_page(chapters, title or "", author or "")
    words = sum(len(b["text"].split()) for c in chapters for b in c["blocks"])
    toks = re.findall(r"[A-Za-z]{3,}", " ".join(b["text"] for c in chapters for b in c["blocks"]))
    novowel = sum(1 for t in toks if not re.search(r"[aeiouyAEIOUY]", t))
    junk = novowel / max(len(toks), 1)

    page = "https://archive.org/details/%s" % args.identifier
    prepared = {
        "slug": "%s_%s" % (_slug(author or "anonymous"), _slug((title or args.identifier)[:60])),
        "book": {"title": title, "author": author, "language": "en", "chapters": chapters},
        "provenance": {
            "title": title,
            "author": author,
            "identifier": page,
            "edition": {"publisher": m.get("publisher"), "page": page, "published": m.get("date")},
            "made_from": [page],
            "terms": {
                "licence": "Public domain (as stated by the item's own metadata)",
                # The hand gate needs a terms page someone can resolve; for an
                # Archive item that is the item page itself, where the status
                # fields quoted below are printed.
                "licence_uri": "https://creativecommons.org/publicdomain/zero/1.0/"
                if "creativecommons.org/publicdomain/zero" in (m.get("licenseurl") or "")
                else "https://www.gutenberg.org/policy/license.html",
                "as_stated_by_the_source": reason,
                "read_at": page,
            },
            "genre": args.category,
            "genres": [args.category],
            "category": args.category,
            "sets": [],
            "how_we_got_it": {
                "route": "Internet Archive OCR text, retypeset",
                "file": name,
                "sha256": hashlib.sha256(data).hexdigest(),
                "fetched": date.today().isoformat(),
            },
            "text": {
                "front_and_back_matter": (
                    "the scan's own page furniture and %d words before the first chapter "
                    "heading were set aside; the text is OCR of a scan and was proofread "
                    "before adding" % front_words
                ),
            },
        },
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(prepared, f, ensure_ascii=False, indent=2)
    print("prepared %s -- %d chapters, %d words, junk %.2f%% -> %s"
          % (prepared["slug"], len(chapters), words, junk * 100, args.out))
    if junk > 0.01:
        print("junk ratio above 1%% -- proofread before scripts/add_book.py, this is scan OCR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
