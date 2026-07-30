# Superb catalogue

The library of books that Superb reads from.

Superb is a reading app. This repository holds the books — not the app. The app
lives at [kihea/superb](https://github.com/kihea/superb).

They are kept apart on purpose. Most people working on the app never need the
library, and most people adding a book never need the app, so neither should
have to download the other.

## What is in here

Books that anyone is free to read and pass along: works out of copyright, and
works whose authors or editors have said they may be shared. Every book records
where it came from and on what terms, in a file next to it.

Two sources to start with:

- **[Standard Ebooks](https://standardebooks.org)** — carefully typeset editions
  of public-domain books. They put the whole file in the public domain, including
  their own editing work. Most people who improve a free text keep something back
  for the improving; they give it away, which is why their editions are the ones
  worth building on and why anyone else can build on them too. Nearly everything
  here starts as one of theirs. If you use them, consider
  [supporting them](https://standardebooks.org/donate).
- **[Project Gutenberg](https://www.gutenberg.org)** — a much larger collection.
  We add a selection rather than all of it, and we retypeset what we add.

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
2. Get the text, and take out anything the source added that is not the book —
   headers, footers, licence notices.
3. Clean up the typesetting: chapters, paragraphs, quotation marks, italics.
4. Write the provenance file beside it.
5. Open a pull request.

The tooling for steps 2 and 3 is being built by doing it by hand first, so that
what gets automated is the thing that actually happens rather than a guess at it.
Until it is here, do those steps by hand and say what was awkward — that is the
useful part.

## Licences

The books each carry their own, recorded per book.

This repository's own files — the scripts, the notes, this page — are MIT.

The app is source-available: free to read, use, change and pass along, but not to
sell. That is the app's licence and it does not reach the books here.

## Status

New, and mostly empty. The shape comes first, then the books.
