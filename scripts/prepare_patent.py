#!/usr/bin/env python3
"""Prepare a United States patent for the shelf, from its Google Patents page.

    python scripts/prepare_patent.py US6506148B2 -o prepared.json
    python scripts/prepare_patent.py US6506148B2 --html saved.html --pdf facsimile.pdf -o prepared.json

Reads the full text from patents.google.com (or a saved copy of that page),
shapes it into this library's book form -- the abstract, then the
description split at its own headings, then the claims -- and writes a
prepared-book JSON for scripts/add_book.py.

Why the text can be trusted: for patents granted since 1976 the text on
Google Patents is the USPTO's own full-text record, not an OCR of the page
images. The --pdf option cross-checks anyway, against the facsimile PDF's
embedded text layer (which IS rough OCR), and reports per-chapter word
overlap -- a low score there is a prompt to read, not a verdict.

The terms: "Subject to limited exceptions reflected in 37 CFR 1.71(d) &
(e) and 1.84(s), the text and drawings of a patent are typically not
subject to copyright restrictions." (USPTO, Terms of Use.) A patent that
claims one of those exceptions prints a copyright notice in its own text;
this script refuses to prepare a patent whose text contains one, and says
so, rather than shipping the exception.
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import date
from html.parser import HTMLParser

USPTO_TERMS_URI = "https://www.uspto.gov/terms-use-uspto-websites"
USPTO_TERMS_QUOTE = (
    "Patents are published as part of the terms of granting the patent to "
    "the inventor. Subject to limited exceptions reflected in 37 CFR "
    "1.71(d) & (e) and 1.84(s), the text and drawings of a patent are "
    "typically not subject to copyright restrictions."
)


class _Sections(HTMLParser):
    """Collect text blocks from the abstract/description/claims sections of a
    Google Patents page, flushing on the block-level tags the page uses."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.section = None
        self.depth = 0
        self.out = {"abstract": [], "description": [], "claims": []}
        self.buf = []
        self.kind = "paragraph"

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if text and self.section:
            self.out[self.section].append({"type": self.kind, "text": text})
        self.buf = []
        self.kind = "paragraph"

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "section" and a.get("itemprop") in self.out:
            self.section = a["itemprop"]
            self.depth = 1
            return
        if not self.section:
            return
        self.depth += 1
        if tag == "heading":
            self._flush()
            self.kind = "heading"
        elif tag in ("div", "p", "li"):
            self._flush()

    def handle_endtag(self, tag):
        if not self.section:
            return
        if tag == "heading":
            self._flush()
        if tag == "section":
            self.depth = 0
        else:
            self.depth -= 1
        if self.depth <= 0:
            self._flush()
            self.section = None

    def handle_data(self, data):
        if self.section:
            self.buf.append(data)


def _slug(text):
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def _title_case(heading):
    """BACKGROUND OF THE INVENTION -> Background of the Invention."""
    small = {"of", "the", "a", "an", "and", "or", "for", "in", "on", "to", "by"}
    words = heading.lower().split()
    out = [w if (i and w in small) else w.capitalize() for i, w in enumerate(words)]
    return " ".join(out)


def parse_page(html):
    p = _Sections()
    p.feed(html)
    p._flush()

    m = re.search(r'<meta name="DC.title" content="([^"]+)"', html)
    title = m.group(1).strip() if m else None
    inventors = re.findall(r'<meta name="DC.contributor" content="([^"]+)" scheme="inventor"', html)
    dates = dict(re.findall(r'<meta name="DC.date" content="([^"]+)" scheme="([^"]+)"', html))
    pdf = re.search(r'<meta name="citation_pdf_url" content="([^"]+)"', html)
    return {
        "title": title,
        "inventors": inventors,
        "issued": dates.get("issue"),
        "filed": dates.get("dateSubmitted"),
        "pdf_url": pdf.group(1) if pdf else None,
        "abstract": p.out["abstract"],
        "description": p.out["description"],
        "claims": p.out["claims"],
    }


def _drop_labels(blocks, *patterns):
    out = []
    for b in blocks:
        text = b["text"]
        for pat in patterns:
            text = re.sub(pat, "", text, count=1).strip()
        if text:
            out.append({**b, "text": text})
    return out


_SPEC_OPENERS = re.compile(
    r"(To all whom it may concern|Be it known that|This invention relates|"
    r"My invention relates|The invention relates)", re.IGNORECASE)


def scrub_ocr(blocks):
    """For pre-1976 patents the page text is OCR of a scan, and the scan's
    own page furniture (sheet labels, dates, signature lines) arrives as
    text. Drop everything before the specification's own opening line, and
    any later block that reads as page furniture rather than prose: short,
    and mostly capitals, digits and punctuation."""
    started = False
    out = []
    for b in blocks:
        text = b["text"]
        if not started:
            m = _SPEC_OPENERS.search(text)
            if not m:
                continue
            started = True
            text = text[m.start():]
            out.append({**b, "text": text})
            continue
        letters = re.findall(r"[A-Za-z]", text)
        lower = re.findall(r"[a-z]", text)
        if len(text) < 90 and letters and len(lower) / len(letters) < 0.5:
            continue
        out.append(b)
    return out if started else blocks


def build_chapters(parsed):
    chapters = []

    abstract = _drop_labels(parsed["abstract"], r"^Abstract\b")
    if abstract:
        chapters.append({
            "label": "Abstract",
            "types": ["patent", "abstract"],
            "blocks": [{"type": "paragraph", "text": b["text"]} for b in abstract],
        })

    # The description splits into chapters at its own headings.
    description = _drop_labels(parsed["description"], r"^Description\b")
    if parsed.get("scrub_ocr"):
        description = scrub_ocr(description)
    current = None
    for b in description:
        if b["type"] == "heading":
            current = {"label": _title_case(b["text"]), "types": ["patent", "description"], "blocks": []}
            chapters.append(current)
            continue
        if current is None:
            current = {"label": "Description", "types": ["patent", "description"], "blocks": []}
            chapters.append(current)
        current["blocks"].append({"type": "paragraph", "text": b["text"]})

    claims = _drop_labels(parsed["claims"], r"^Claims\s*\(\d+\)\s*", r"^I claim:?\s*", r"^What is claimed is:?\s*")
    if claims:
        chapters.append({
            "label": "Claims",
            "types": ["patent", "claims"],
            "blocks": [{"type": "claim", "text": b["text"]} for b in claims],
        })

    return [c for c in chapters if c["blocks"]]


def crosscheck_pdf(chapters, pdf_path):
    """Per-chapter word overlap against the facsimile's own text layer.
    The facsimile's layer is rough OCR, so this reports rather than
    decides -- but a chapter whose words mostly fail to appear in the
    facsimile at all deserves a human's eye before it ships."""
    import pymupdf  # noqa: PLC0415 -- optional dependency, used only here

    doc = pymupdf.open(pdf_path)
    pdf_words = set(re.findall(r"[a-z]{3,}", " ".join(p.get_text() for p in doc).lower()))
    print("cross-check against %s (%d distinct words in its text layer):" % (pdf_path, len(pdf_words)))
    worst = 1.0
    for ch in chapters:
        words = set(re.findall(r"[a-z]{3,}", " ".join(b["text"] for b in ch["blocks"]).lower()))
        if not words:
            continue
        overlap = len(words & pdf_words) / len(words)
        worst = min(worst, overlap)
        print("  %-36s %5.1f%% of its words appear in the facsimile" % (ch["label"], overlap * 100))
    return worst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("number", help="publication number, e.g. US6506148B2")
    ap.add_argument("--html", help="a saved copy of the Google Patents page (skips the fetch)")
    ap.add_argument("--pdf", help="facsimile PDF to cross-check the text against")
    ap.add_argument("--scrub-ocr", action="store_true",
                    help="pre-1976 patent: drop the scan's own page furniture from the OCR text")
    ap.add_argument("-o", "--out", required=True, help="where to write the prepared-book JSON")
    args = ap.parse_args()

    page_url = "https://patents.google.com/patent/%s/en" % args.number
    if args.html:
        with open(args.html, "r", encoding="utf-8") as f:
            html = f.read()
    else:
        req = urllib.request.Request(page_url, headers={"User-Agent": "superb-catalogue prepare_patent.py"})
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode("utf-8")

    parsed = parse_page(html)
    parsed["scrub_ocr"] = args.scrub_ocr
    if not parsed["title"]:
        print("could not read a title off the page -- is this a Google Patents page?")
        return 1

    chapters = build_chapters(parsed)
    if not chapters:
        print("no readable text sections found")
        return 1

    whole_text = " ".join(b["text"] for c in chapters for b in c["blocks"])
    notice = re.search(r"copyright|all rights reserved|\(c\)\s*\d{4}|©", whole_text, re.IGNORECASE)
    if notice:
        print("REFUSED: the patent's own text contains what reads as a copyright notice")
        print("  (37 CFR 1.71(d)-(e) lets an applicant claim one; this one may have)")
        print("  matched: %r" % notice.group(0))
        return 1

    if args.pdf:
        crosscheck_pdf(chapters, args.pdf)
        with open(args.pdf, "rb") as f:
            pdf_sha = hashlib.sha256(f.read()).hexdigest()
    else:
        pdf_sha = None

    inventors = ", ".join(parsed["inventors"]) or None
    title_for_slug = parsed["title"] if len(parsed["title"]) <= 60 else " ".join(parsed["title"].split()[:8])
    slug = "%s_%s" % (_slug(inventors or args.number), _slug(title_for_slug))

    how = {
        "route": "Google Patents full-text page",
        "page": page_url,
        "fetched": date.today().isoformat(),
    }
    if pdf_sha:
        how["cross_checked_against"] = {"facsimile_pdf": parsed["pdf_url"], "sha256": pdf_sha}

    prepared = {
        "slug": slug,
        "book": {
            "title": parsed["title"],
            "author": inventors,
            "language": "en-US",
            "chapters": chapters,
        },
        "provenance": {
            "title": parsed["title"],
            "author": inventors,
            "identifier": page_url,
            "edition": {
                "publisher": "United States Patent and Trademark Office",
                "page": page_url,
                "published": parsed["issued"],
                "filed": parsed["filed"],
                "publication_number": args.number,
            },
            "made_from": [u for u in (page_url, parsed["pdf_url"]) if u],
            "terms": {
                "licence": "Public domain (United States patent text; 37 CFR 1.71(d)-(e))",
                "licence_uri": USPTO_TERMS_URI,
                "as_stated_by_the_source": USPTO_TERMS_QUOTE,
                "read_at": USPTO_TERMS_URI,
                "no_copyright_notice_in_text": True,
            },
            "genre": "Patent",
            "genres": ["Patent"],
            "category": "Patents",
            "sets": [],
            "how_we_got_it": how,
        },
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(prepared, f, ensure_ascii=False, indent=2)
    words = sum(len(re.findall(r"\S+", b["text"])) for c in chapters for b in c["blocks"])
    print("prepared %s -- %d chapters, %d words -> %s" % (slug, len(chapters), words, args.out))
    print("next: python scripts/add_book.py %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
