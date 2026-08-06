#!/usr/bin/env python3
"""Prepare a Project Gutenberg book for the shelf, retypeset.

    python scripts/prepare_gutenberg.py 1063 --category "Fiction" -o prepared.json

Fetches the book's own page (for the title, author, language and PG's own
statement of copyright status) and its plain-text file, then does by
machine what README.md describes doing by hand:

  1. takes out what the source added that is not the book -- the Project
     Gutenberg header and footer, and [Illustration] markers;
  2. cleans up the typesetting -- chapters found at the text's own
     headings, paragraphs unwrapped, straight quotes curled, -- turned
     into em dashes, _underscore italics_ unwrapped;
  3. records the provenance beside it, quoting PG's own permission
     statement from the file itself rather than assuming it.

What it cannot do is read the result like a person. The structural report
it prints (chapters found, words kept, words set aside as front matter) is
the prompt for that reading, not a substitute -- a book whose report looks
wrong should be opened, not shipped. Front matter before the first
detected chapter (title page, contents list) is set aside, and the
omission is recorded in provenance, per rule 4.
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import date

PG_LICENCE_URI = "https://www.gutenberg.org/policy/license.html"
UA = {"User-Agent": "superb-catalogue prepare_gutenberg.py (one book, politely)"}

START_RE = re.compile(r"\*{3} ?START OF (THE|THIS) PROJECT GUTENBERG EBOOK[^*]*\*{3}", re.IGNORECASE)
END_RE = re.compile(r"\*{3} ?END OF (THE|THIS) PROJECT GUTENBERG EBOOK[^*]*\*{3}", re.IGNORECASE)

# The heading shapes PG books actually use, most specific first. A line has
# to be short and stand alone to count -- prose that happens to start with
# "Chapter" does not.
HEADING_RES = [
    re.compile(r"^(CHAPTER|Chapter|LETTER|Letter|BOOK|Book|PART|Part|CANTO|Canto|ACT|STAVE|STORY)\s+"
               r"([IVXLCDM]+|[0-9]+|[A-Z][a-z]+)\.?( .{0,60})?$"),
    re.compile(r"^([IVXLCDM]+|[0-9]+)\.?$"),
    # "I. The Horror in Clay" -- a numbered section with its title on the line.
    re.compile(r"^([IVXLCDM]+|[0-9]+)\.\s+\S.{0,76}$"),
]


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def metadata(number):
    html = fetch("https://www.gutenberg.org/ebooks/%d" % number).decode("utf-8", "replace")

    def field(name):
        m = re.search(r'<th>%s</th>\s*<td[^>]*>(.*?)</td>' % name, html, re.DOTALL)
        return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else None

    title = field("Title")
    author = field("Author") or field("Editor") or field("Translator")
    language = field("Language")
    rights = field("Copyright") or field("Copyright Status") or ""
    # e.g. "Public domain in the USA."
    return {"title": title, "author": author, "language": language, "rights": rights, "page_html": html}


def plain_text(number):
    for url in ("https://www.gutenberg.org/files/%d/%d-0.txt" % (number, number),
                "https://www.gutenberg.org/cache/epub/%d/pg%d.txt" % (number, number)):
        try:
            data = fetch(url)
            return url, data
        except Exception:
            continue
    raise SystemExit("no plain-text file found for ebook %d" % number)


def strip_boilerplate(text):
    """The body between PG's own START and END markers, and PG's permission
    statement from the header, quoted verbatim for the provenance."""
    start = START_RE.search(text)
    end = END_RE.search(text)
    if not start or not end:
        raise SystemExit("could not find the PG START/END markers")
    header = text[: start.start()]
    stated = None
    m = re.search(r"This ebook is for the use of anyone.*?(?:re-use it|www\.gutenberg\.org)[^.]*\.",
                  header, re.IGNORECASE | re.DOTALL)
    if m:
        stated = re.sub(r"\s+", " ", m.group(0)).strip()
    return text[start.end(): end.start()], stated


def curl_quotes(text):
    text = re.sub(r"(^|[\s(\[{<])\"", "“", text.replace("“", '"').replace("”", '"'))
    text = text.replace('"', "”")
    text = re.sub(r"(^|[\s(\[{<])'", "‘", text.replace("‘", "'").replace("’", "'"))
    text = text.replace("'", "’")
    return text


def typeset(paragraph):
    # A transcriber's note is the source talking, not the book.
    if re.match(r"^\[?Transcriber", paragraph.strip(), re.IGNORECASE):
        return ""
    p = re.sub(r"\[Illustration[^\]]*\]", "", paragraph)
    p = re.sub(r"_([^_]+)_", r"\1", p)          # underscore italics
    p = re.sub(r"(?<=[^-])--(?=[^-])", "—", p)  # -- to em dash
    p = curl_quotes(p)
    return p.strip()


def looks_like_verse(lines):
    if len(lines) < 3:
        return False
    short = sum(1 for l in lines if 0 < len(l.strip()) <= 50)
    unpunct = sum(1 for l in lines if l.strip() and l.strip()[-1] not in ".!?”’:;")
    return short / len(lines) > 0.7 and unpunct / len(lines) > 0.5


def is_heading(line):
    # Headings often arrive centred and _italicised_; judge the words.
    line = line.strip().strip("_*").strip()
    if not line or len(line) > 80:
        return None
    for hr in HEADING_RES:
        m = hr.match(line)
        if m:
            return line
    return None


def build_chapters(body):
    """Split the body at its own headings. Returns (chapters, front_words)."""
    raw_paras = re.split(r"\n\s*\n", body)
    chapters = []
    current = None
    front = []

    for para in raw_paras:
        lines = [l for l in para.splitlines() if l.strip()]
        if not lines:
            continue
        heading = is_heading(lines[0]) if len(lines) <= 2 or len(lines[0].strip()) < 60 else None
        if heading and (len(lines) == 1 or is_heading(lines[0])):
            rest = lines[1:]
            current = {"label": typeset(heading), "types": ["chapter"], "blocks": []}
            chapters.append(current)
            if rest:
                text = typeset(" ".join(l.strip() for l in rest))
                if text:
                    current["blocks"].append({"type": "paragraph", "text": text})
            continue
        if looks_like_verse(lines):
            text = typeset("\n".join(l.strip() for l in lines))
            block = {"type": "verse", "text": text}
        else:
            text = typeset(" ".join(l.strip() for l in lines))
            block = {"type": "paragraph", "text": text}
        if not text:
            continue
        if current is None:
            front.append(text)
        else:
            current["blocks"].append(block)

    chapters = [c for c in chapters if c["blocks"]]
    front_words = sum(len(t.split()) for t in front)

    if len(chapters) < 2:
        # No usable chapter structure -- the whole body is one reading.
        blocks = []
        for para in raw_paras:
            lines = [l for l in para.splitlines() if l.strip()]
            if not lines:
                continue
            if looks_like_verse(lines):
                text = typeset("\n".join(l.strip() for l in lines))
                blocks.append({"type": "verse", "text": text})
            else:
                text = typeset(" ".join(l.strip() for l in lines))
                blocks.append({"type": "paragraph", "text": text})
        blocks = [b for b in blocks if b["text"]]
        return [{"label": "The Text", "types": ["chapter"], "blocks": blocks}], 0

    return chapters, front_words


def drop_title_page(chapters, title, author):
    """The single-chapter fallback keeps everything, including the text's
    own title and byline lines. Set those aside like any other front
    matter: leading short blocks that are the title, the author, or a
    'by ...' line."""
    dropped = 0
    for ch in chapters[:1]:
        while ch["blocks"]:
            text = ch["blocks"][0]["text"]
            short = len(text) <= max(len(title), len(author or "")) + 24
            named = (
                re.sub(r"\W", "", text.lower()) in
                (re.sub(r"\W", "", (title or "").lower()), re.sub(r"\W", "", (author or "").lower()))
                or re.match(r"^by\b", text, re.IGNORECASE)
                or (author and author.split()[-1].lower() in text.lower() and len(text) < 60 and "." not in text.rstrip("."))
            )
            if short and named:
                dropped += len(text.split())
                ch["blocks"].pop(0)
                continue
            break
    return dropped


def _slug(text):
    import unicodedata
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("number", type=int, help="Project Gutenberg ebook number")
    ap.add_argument("--category", required=True, help="shelf category (see CATEGORIES.md)")
    ap.add_argument("--genre", default=None, help="raw genre note for provenance (defaults to category)")
    ap.add_argument("--title", default=None, help="override the page's own title (subtitle trimming)")
    ap.add_argument("--author", default=None, help="override the page's author (name order)")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    meta = metadata(args.number)
    title = args.title or meta["title"]
    author = args.author or meta["author"]
    if not title:
        raise SystemExit("no title on the book's page")
    if meta["language"] and "english" not in meta["language"].lower():
        raise SystemExit("not an English text: %r" % meta["language"])
    if "public domain in the usa" not in (meta["rights"] or "").lower():
        raise SystemExit("PG's own page does not state 'Public domain in the USA': %r" % meta["rights"])

    # PG author fields arrive "Surname, Given (Expansion), dates" -- turn
    # into "Given Surname".
    if author:
        author = re.sub(r"\s*\([^)]*\)", "", author)
        author = re.sub(r",?\s*\d{4}\??-(\d{4}\??)?$", "", author).strip().strip(",")
        parts = [p.strip() for p in author.split(",")]
        if len(parts) == 2:
            author = "%s %s" % (parts[1], parts[0])

    txt_url, data = plain_text(args.number)
    text = data.decode("utf-8-sig", "replace").replace("\r\n", "\n")
    body, stated = strip_boilerplate(text)
    chapters, front_words = build_chapters(body)
    front_words += drop_title_page(chapters, title, author or "")
    words = sum(len(b["text"].split()) for c in chapters for b in c["blocks"])

    page = "https://www.gutenberg.org/ebooks/%d" % args.number
    stated_full = (
        "%s Copyright status as stated on the book's own page: %s"
        % (stated or "(no permission sentence found in the file header)", meta["rights"])
    )

    prepared = {
        "slug": "%s_%s" % (_slug(author or "anonymous"), _slug(title if len(title) <= 60 else " ".join(title.split()[:8]))),
        "book": {"title": title, "author": author, "language": "en", "chapters": chapters},
        "provenance": {
            "title": title,
            "author": author,
            "identifier": page,
            "edition": {"publisher": "Project Gutenberg", "page": page, "published": None},
            "made_from": [page, txt_url],
            "terms": {
                "licence": "Public domain in the USA (as stated by Project Gutenberg)",
                "licence_uri": PG_LICENCE_URI,
                "as_stated_by_the_source": stated_full,
                "read_at": page,
            },
            "genre": args.genre or args.category,
            "genres": [args.genre or args.category],
            "category": args.category,
            "sets": [{"name": "Project Gutenberg top 100", "type": "list"}],
            "how_we_got_it": {
                "route": "Project Gutenberg plain text, retypeset",
                "file": txt_url,
                "sha256": hashlib.sha256(data).hexdigest(),
                "fetched": date.today().isoformat(),
            },
            "text": {
                "front_and_back_matter": (
                    "the Project Gutenberg header, footer and licence are not part of the book and "
                    "are not included; %d words of front matter before the first chapter heading "
                    "(title page, contents) were set aside" % front_words
                ),
            },
        },
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(prepared, f, ensure_ascii=False, indent=2)
    print("prepared %s -- %d chapters, %d words (front matter set aside: %d words) -> %s"
          % (prepared["slug"], len(chapters), words, front_words, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
