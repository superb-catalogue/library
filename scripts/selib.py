"""Shared reading of Standard Ebooks EPUBs, for the library's ingest scripts.

Everything here reads bytes straight out of the zips — nothing is ever
extracted to disk, and nothing under C:\\archives (or wherever the archives
live) is ever opened for writing.
"""
import hashlib
import re
import urllib.parse
import xml.etree.ElementTree as ET

OPF_NS = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"


def strip_ns(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def norm_type(raw):
    """'z3998:letter se:bridge' -> 'letter+bridge' — namespace prefixes are
    the vocabulary's own bookkeeping, not part of the type a reading surface
    would want to switch on."""
    toks = raw.split()
    out = [t.split(":", 1)[1] if ":" in t else t for t in toks]
    return "+".join(out)


def clean_text(s):
    return re.sub(r"[ \t\r\n]+", " ", s).strip()


def text_of(el):
    return "".join(el.itertext())


# What the door gate's licence check does, and just as importantly does
# not, establish. No reading of a file's contents can decide whether
# someone is lying about a licence — a forger can write a flawless CC0
# dedication into a copyrighted book, and no phrase list, regex or Unicode
# normalisation would ever catch that, because the words on the page are
# exactly the words a genuine dedication would use. Three earlier attempts
# at this check tried to make text carry that weight anyway — a substring
# test for a phrase, then a longer phrase list, then a substring test for a
# URI — and every one was defeated the same way: something else that
# happened to contain the matched string.
#
# So this checks something a substring test can't fake as cheaply: it
# parses every URL found in the book's own rights metadata as a URL —
# scheme, host and path as whole values — and requires the host and path
# to equal, exactly, an entry on this allow-list. A URL that merely
# CONTAINS an accepted URI as a path segment inside a different host
# (https://evil.example.com/creativecommons.org/publicdomain/zero/1.0/)
# does not match, because its host is not creativecommons.org — the
# comparison is structural, not textual containment.
#
# What this still does and does not prove: it confirms the book's own
# metadata cites a licence URI this library has agreed to accept, and
# that the file is intact. It does NOT confirm the underlying copyright
# claim is true, and no per-book check against Standard Ebooks' own site
# happens here or anywhere else in this repository today — see README.md's
# "Adding a book" section for what is and is not actually verified for the
# books on this shelf.
ACCEPTED_LICENCE_URIS = (
    "https://creativecommons.org/publicdomain/zero/1.0/",
)

# Terms pages a hand-added book (scripts/add_book.py) may rest on, checked
# the same structural way. CC0 is Standard Ebooks' dedication; the USPTO
# page is where the United States says the text and drawings of a patent
# are typically not subject to copyright restrictions (37 CFR 1.71(d)-(e),
# 1.84(s)); the Gutenberg page is where Project Gutenberg explains that its
# texts are public domain in the United States. Each entry earns its place
# by someone reading the page, not by the category of the source.
ACCEPTED_HAND_TERMS_URIS = ACCEPTED_LICENCE_URIS + (
    "https://www.uspto.gov/terms-use-uspto-websites",
    "https://www.gutenberg.org/policy/license.html",
)

# Other Creative Commons licences, named here only so a URL citing one of
# them is recognised as "a licence claim" rather than an ordinary link —
# see disallowed_licence_uris_in below. This list does not need to be
# exhaustive of every licence that exists; it only needs to catch the
# specific family (creativecommons.org/licenses/...) that a book claiming
# CC0 might also, contradictorily, cite.
_KNOWN_CC_LICENCE_HOST = "creativecommons.org"
_KNOWN_CC_LICENCE_PATH_PREFIX = "/licenses/"

# Phrases that read as restrictive to a human. These are advisory only —
# they never decide whether a book passes the gate, precisely because a
# phrase list is exactly the mechanism that failed twice already. Every
# caller of the gate surfaces these to a person (stdout at minimum, the
# provenance record at best) rather than acting on them; a phrase found
# here beside an accepted licence URI is worth a look, not an automatic
# rejection or an automatic pass.
ADVISORY_RESTRICTIVE_PHRASES = (
    "all rights reserved",
    "reserves all rights",
    "copyright reserved",
    "may not be reproduced",
    "not be reproduced",
    "without written permission",
    "without permission",
    "without a paid license",
    "without a paid licence",
    "strictly prohibited",
    "reproduction is prohibited",
    "no part of this",
    "not dedicated to the public domain",
    "not in the public domain",
    "not be copied",
    "requires a licence from",
    "requires a license from",
)

_URL_RE = re.compile(r"https?://[^\s<>\"'\)\]]+")


def _urls_in(text):
    if not text:
        return []
    return _URL_RE.findall(clean_text(text))


def _normalize_path(path):
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return path


def _host_and_path(url):
    """Parse `url` as a URL and return (host, normalised path), or
    (None, None) if it can't be parsed as one, has a scheme other than
    http/https, or its host is percent-encoded (rejected rather than
    decoded and matched — an encoded host is not treated as equivalent to
    its decoded form)."""
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return None, None
    if parsed.scheme not in ("http", "https"):
        return None, None
    if "%" in parsed.netloc:
        return None, None
    host = (parsed.hostname or "").lower()
    if not host:
        return None, None
    return host, _normalize_path(parsed.path)


_ACCEPTED_HOST_PATHS = tuple(_host_and_path(u) for u in ACCEPTED_LICENCE_URIS)


def licence_uris_in(rights_text):
    """The accepted licence URI(s) (drawn from ACCEPTED_LICENCE_URIS) that
    this text cites — found by parsing every URL in the text and comparing
    its host and path as whole values, never by testing whether the
    allow-listed string appears as a substring anywhere. A hostile URL
    that merely contains an accepted URI as a path segment inside another
    host does not match, because its host is not the accepted one."""
    matched = []
    for candidate in _urls_in(rights_text):
        host, path = _host_and_path(candidate)
        if host is None:
            continue
        for accepted_uri, (accepted_host, accepted_path) in zip(ACCEPTED_LICENCE_URIS, _ACCEPTED_HOST_PATHS):
            if host == accepted_host and path == accepted_path and accepted_uri not in matched:
                matched.append(accepted_uri)
    return matched


def disallowed_licence_uris_in(rights_text):
    """Any URL in this text that names a *different* Creative Commons
    licence (creativecommons.org/licenses/...) — one this library does
    not accept. A book naming an accepted licence and a disallowed one in
    the same breath is not making one claim; it's making two, and the
    gate treats that as a failure rather than picking the friendlier one."""
    found = []
    for candidate in _urls_in(rights_text):
        host, path = _host_and_path(candidate)
        if host != _KNOWN_CC_LICENCE_HOST:
            continue
        if not path.startswith(_KNOWN_CC_LICENCE_PATH_PREFIX):
            continue
        if any(host == ah and path == ap for ah, ap in _ACCEPTED_HOST_PATHS):
            continue  # it's the accepted one, not a disallowed one
        if candidate not in found:
            found.append(candidate)
    return found


def is_genuine_public_domain_dedication(rights_texts):
    """`rights_texts` is every dc:rights element's text a book carries —
    a book can have more than one, and every one of them has to cite an
    accepted licence URI, with no disallowed licence URI also present, not
    just the last element read — so a restrictive statement or a
    contradictory licence claim sitting beside a genuine one in the same
    metadata can't ride along unexamined."""
    if isinstance(rights_texts, str):
        rights_texts = [rights_texts]
    rights_texts = [t for t in (rights_texts or []) if t]
    if not rights_texts:
        return False
    for t in rights_texts:
        if not licence_uris_in(t):
            return False
        if disallowed_licence_uris_in(t):
            return False
    return True


def advisory_restrictive_phrases_in(rights_texts):
    """Phrases worth a human's eye — never used to decide the gate. See
    the module-level note above ADVISORY_RESTRICTIVE_PHRASES. Every caller
    of the gate is expected to surface this list somewhere a person will
    actually see it; a correctly-implemented function nobody calls is not
    a safety net."""
    if isinstance(rights_texts, str):
        rights_texts = [rights_texts]
    found = []
    for t in rights_texts or []:
        tl = clean_text(t).lower()
        for phrase in ADVISORY_RESTRICTIVE_PHRASES:
            if phrase in tl and phrase not in found:
                found.append(phrase)
    return found


def is_standardebooks_identifier(identifier):
    """The identifier has to actually be a Standard Ebooks ebook page — not
    merely present — so a citation someone can resolve for themselves is
    something the gate checked for, not something it assumed."""
    return bool(identifier) and identifier.startswith("https://standardebooks.org/ebooks/")


def find_opf_path(ez):
    container = ez.read("META-INF/container.xml").decode("utf-8")
    m = re.search(r'full-path="([^"]+)"', container)
    if not m:
        raise ValueError("no full-path in META-INF/container.xml")
    return m.group(1)


def parse_metadata(root):
    """Pull the fields the library needs off an OPF <metadata>. Every text
    read here is decoded as UTF-8 upstream by the caller — a mangled
    character on screen is the terminal, not the file (see
    books/HOW-THE-FIRST-BOOK-WENT.md, point 5)."""
    md = root.find("opf:metadata", OPF_NS)

    identifier = None
    for e in md.findall("dc:identifier", OPF_NS):
        identifier = (e.text or "").strip()

    title = None
    for e in md.findall("dc:title", OPF_NS):
        if e.text and e.text.strip():
            title = e.text.strip()
            break

    creators = [(e.text or "").strip() for e in md.findall("dc:creator", OPF_NS) if e.text]

    language = None
    for e in md.findall("dc:language", OPF_NS):
        language = (e.text or "").strip()

    pub_date = None
    for e in md.findall("dc:date", OPF_NS):
        pub_date = (e.text or "").strip()

    # A book can carry more than one dc:rights element. Every one of them
    # matters to the licence check (see is_genuine_public_domain_dedication),
    # so all of them are kept — not just the last one read.
    rights_list = [(e.text or "").strip() for e in md.findall("dc:rights", OPF_NS) if e.text and e.text.strip()]
    rights = rights_list[-1] if rights_list else None

    sources = [(e.text or "").strip() for e in md.findall("dc:source", OPF_NS) if e.text]

    modified = None
    collections = {}
    genres = []
    for e in md.findall("opf:meta", OPF_NS):
        prop = e.get("property")
        if prop == "dcterms:modified":
            modified = (e.text or "").strip()
        elif prop == "schema:genre":
            # Some books carry more than one — e.g. Ashenden is tagged both
            # "Adventure" (what it is) and "Shorts" (a story collection
            # rather than one continuous narrative). Standard Ebooks lists
            # the primary genre first with no other marker distinguishing
            # them, so document order is the only signal; keep all of them
            # and let the caller decide which is the shelf category.
            genres.append((e.text or "").strip())
        elif prop == "belongs-to-collection":
            cid = e.get("id")
            if cid:
                collections.setdefault(cid, {})["name"] = (e.text or "").strip()
        elif prop == "collection-type":
            refid = (e.get("refines") or "").lstrip("#")
            if refid:
                collections.setdefault(refid, {})["type"] = (e.text or "").strip()
        elif prop == "group-position":
            refid = (e.get("refines") or "").lstrip("#")
            if refid:
                collections.setdefault(refid, {})["position"] = (e.text or "").strip()

    return {
        "identifier": identifier,
        "title": title,
        "creators": creators,
        "language": language,
        "date": pub_date,
        "modified": modified,
        "rights": rights,
        "rights_list": rights_list,
        "sources": sources,
        "genres": genres,
        "collections": list(collections.values()),
    }


def parse_manifest_spine(root):
    manifest = {}
    for item in root.findall("opf:manifest/opf:item", OPF_NS):
        manifest[item.get("id")] = item.get("href")
    spine = []
    for itemref in root.findall("opf:spine/opf:itemref", OPF_NS):
        idref = itemref.get("idref")
        if idref in manifest:
            spine.append(manifest[idref])
    return spine


def block_of(el):
    """Turn one XHTML element into a block the reading surface can decide
    what to do with, keeping the source's own epub:type rather than
    guessing from a title (books/HOW-THE-FIRST-BOOK-WENT.md, point 2) and
    keeping the letters-and-diary-entries structure a flat list of
    paragraphs would throw away."""
    tag = strip_ns(el.tag)
    epub_type = el.get("{%s}type" % EPUB_NS)

    if tag == "hr":
        return {"type": "break"}
    if tag == "img":
        return None

    if tag in ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
        txt = clean_text(text_of(el))
        if not txt:
            return None
        if epub_type:
            btype = norm_type(epub_type)
        elif tag.startswith("h"):
            btype = "heading"
        elif tag == "li":
            btype = "item"
        else:
            btype = "paragraph"
        return {"type": btype, "text": txt}

    # container-like element (blockquote, div, header, footer, figure,
    # ol, ul, table, nested section) — recurse and keep its own type as
    # the wrapper, so a letter or a diary entry stays a distinguishable
    # group of blocks rather than being flattened into it.
    children = []
    for c in el:
        b = block_of(c)
        if b is not None:
            children.append(b)
    if children:
        btype = norm_type(epub_type) if epub_type else tag
        return {"type": btype, "blocks": children}

    txt = clean_text(text_of(el))
    if txt:
        btype = norm_type(epub_type) if epub_type else tag
        return {"type": btype, "text": txt}
    return None


def extract_chapters(ez, opf_dir, spine_hrefs):
    """Walk the book's own stated reading order (the spine), not filenames
    sorted alphabetically — chapter-10.xhtml sorts right after chapter-1.xhtml
    alphabetically, which is wrong (HOW-THE-FIRST-BOOK-WENT.md, point 1).
    Separate the author's text from the publisher's apparatus using each
    file's own body epub:type (point 2) rather than guessing from titles."""
    chapters = []
    for href in spine_hrefs:
        full = (opf_dir + "/" + href) if opf_dir else href
        full = full.replace("\\", "/")
        try:
            raw = ez.read(full)
        except KeyError:
            continue
        text = raw.decode("utf-8")
        root = ET.fromstring(text)
        body = root.find("{%s}body" % XHTML_NS)
        if body is None:
            continue
        body_type = body.get("{%s}type" % EPUB_NS) or ""
        body_tokens = [t.split(":", 1)[1] if ":" in t else t for t in body_type.split()]
        if "bodymatter" not in body_tokens:
            continue  # frontmatter/backmatter: the publisher's apparatus, not the book

        for child in body:
            ctag = strip_ns(child.tag)
            if ctag not in ("section", "article", "div"):
                continue
            child_type = child.get("{%s}type" % EPUB_NS) or ""
            child_tokens = [t.split(":", 1)[1] if ":" in t else t for t in child_type.split()]

            heading_el = None
            for sub in child.iter():
                if strip_ns(sub.tag) in ("h1", "h2", "h3", "h4", "h5", "h6"):
                    heading_el = sub
                    break
            label = clean_text(text_of(heading_el)) if heading_el is not None else None

            blocks = []
            for sub in child:
                if sub is heading_el:
                    continue
                b = block_of(sub)
                if b is not None:
                    blocks.append(b)

            chapters.append(
                {
                    "href": href,
                    "label": label,
                    "types": body_tokens + child_tokens,
                    "blocks": blocks,
                }
            )
    return chapters


def count_words(chapters):
    total = 0

    def walk(b):
        nonlocal total
        if "text" in b:
            total += len(b["text"].split())
        for c in b.get("blocks", []):
            walk(c)

    for ch in chapters:
        if ch.get("label"):
            total += len(ch["label"].split())
        for b in ch["blocks"]:
            walk(b)
    return total


def slug_from_identifier(identifier):
    """https://standardebooks.org/ebooks/bram-stoker/dracula -> bram-stoker_dracula"""
    m = re.search(r"standardebooks\.org/ebooks/(.+)$", identifier)
    if not m:
        raise ValueError("identifier is not a standardebooks.org ebook page: %r" % identifier)
    return m.group(1).rstrip("/").replace("/", "_")


def sha256_of(data):
    return hashlib.sha256(data).hexdigest()
