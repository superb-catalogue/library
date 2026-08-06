# Superb catalogue

The library of books that Superb reads from.

Superb is a reading app. This repository holds the books, not the app. The app
lives at [kihea/superb](https://github.com/kihea/superb).

They are kept apart on purpose. Most people working on the app never need the
library, and most people adding a book never need the app, so neither should
have to download the other.

## What is in here

Books that anyone is free to read and pass along: works out of copyright, and
works whose authors or editors have said they may be shared. Every book records
where it came from and on what terms, in a file next to it.

Two sources to start with:

- **[Standard Ebooks](https://standardebooks.org)** publishes carefully typeset
  editions of public-domain books. They put the whole file in the public domain,
  including their own editing work. Most people who improve a free text keep
  something back for the improving; they give it away, which is why their
  editions are the ones worth building on and why anyone else can build on them
  too. Nearly everything here starts as one of theirs. If you use them, consider
  [supporting them](https://standardebooks.org/donate).
- **[Project Gutenberg](https://www.gutenberg.org)** is a much larger
  collection. We add a selection rather than all of it, and we retypeset what we
  add.

## The rules a book has to meet

1. **Anyone may share it.** Public domain, CC0, or a licence that asks only for
   credit or for the same freedom to be passed on. Nothing that forbids
   commercial use, and nothing with no licence at all.
2. **It says where it came from.** Title, author, the edition or the exact page
   it was taken from, the date it was fetched, and the terms it arrived under.
3. **The terms were read, not assumed.** "It's old, so it must be fine" is not a
   provenance record. If we could not find the terms at the source, the book does
   not go in.
4. **The text is the author's.** If anything was left out, the omission is
   marked, so a reader can find every part of it in the original.

Rule 3 has already cost us a source we wanted: a well-known Shakespeare
collection turned out to publish its files with no licence attached at all. The
plays are obviously free; the files were not clearly ours to copy. We took
Shakespeare from Standard Ebooks instead.

## Adding a book

The point of this repository is that adding a book is a normal thing to do, not
an event. The path is:

1. Find a book that meets the four rules.
2. Get the text, and take out anything the source added that is not the book,
   such as headers, footers and licence notices.
3. Clean up the typesetting: chapters, paragraphs, quotation marks, italics.
4. Write the provenance file beside it.
5. Open a pull request.

The tooling for steps 2 and 3 is being built by doing it by hand first, so that
what gets automated is the thing that actually happens rather than a guess at it.
Until it is here, do those steps by hand and say what was awkward. That is the
useful part.

### What the automated check proves, and what it does not

`scripts/gate.py`, and the same check inside `scripts/ingest.py`, confirms two
things fast. The book's own metadata cites a licence URI this library accepts,
checked by parsing it as a URL rather than searching for the allow-listed text.
And the file itself is intact, with a reading order that resolves and an
identifier that points at a real page.

That is all a check on a file's contents can ever confirm. It cannot tell
whether the claim in the metadata is true, because nothing that only reads the
file can: a copy with a forged licence statement would read exactly like a
genuine one.

Here is what that means for the 1,478 books already on this shelf. They came
from Standard Ebooks, whose editions each carry a public-domain dedication in
their own metadata. The check confirms that dedication is present in
machine-readable form and that the file parses. Nobody has independently
re-verified each of the 1,478 works' copyright status against an outside
source. Rule 3 above, "the terms were read, not assumed", was applied when
Standard Ebooks was chosen as a source and when a book's own metadata is read.
It is not a separate, additional per-book check against Standard Ebooks'
website that runs today. If a per-book check at source is wanted later, that is
separate work, not something this repository already does.

### The slower check, and why it is not part of adding a book

`scripts/check_source.py` re-reads a committed book against the EPUB it says it
came from and reports any disagreement: chapter count, reading order, the
sections left out, word count, the licence dedication, and the page it is cited
to. It runs on its own schedule rather than when a book is added, and that is
deliberate. It takes real time across the whole shelf, and nobody should have to
wait on that to add one book. Run it yourself with
`python scripts/check_source.py books/<the-book-you-added>` if you want the
extra confidence before opening a pull request. It is not required.

## Licences

The books each carry their own, recorded per book.

This repository's own files, meaning the scripts and the notes and this page,
are MIT.

One kind of file here is neither. Beside each book's `book.json` sits a
`glosses.json`: the word meanings for that book's own vocabulary, which the
reading app fetches with the text so a tapped word can answer. Those
definitions come from the English Wiktionary and carry Wiktionary's licence,
**CC BY-SA 4.0 or the GFDL**, which asks for credit and for the same freedom
to be passed on. [`NOTICE.md`](NOTICE.md) records that in full. The
obligation binds those files and nothing else: the books beside them keep
their own terms, and the scripts stay MIT.

The app is source-available: free to read, use, change and pass along, but not to
sell. That is the app's licence and it does not reach the books here.

## The shelf

The whole thing, one row per book, is in [`LIBRARY.md`](LIBRARY.md), sorted
by category, with what each book is, who wrote it, and which other lists it
turned up in. `CATEGORIES.md` says what the categories are and why.

## Status

1,478 books, taken from 46 of Standard Ebooks' subject and collection sets,
de-duplicated and retypeset by `scripts/ingest.py`. Those sets held 2,653 files
between them; 1,175 were the same work arriving in more than one set, and one
was rejected at the gate because its reading order resolved to no chapters at
all. More arrive as more of Standard Ebooks' collections are added, as Standard
Ebooks publishes new editions, and as Gutenberg titles are typeset by hand and
added through the same path.
