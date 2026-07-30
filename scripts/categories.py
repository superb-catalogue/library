"""The library's own shelf categories.

Standard Ebooks tags every book with a `schema:genre` value of its own — a
small, plain field describing what kind of book it is (Fiction, Poetry,
Horror, and so on), separate from their collections (prize lists, publisher
canons, series), which describe how a book was *bundled* rather than what it
*is*. The track this came out of says plainly why the collections are wrong
as a shelf scheme: nobody browsing a shelf thinks "Pulitzer for Fiction
winners" first.

So the shelf categories here are ours, derived from that per-book field
rather than adopted wholesale from it: sixteen raw values across the corpus,
several of them rare enough (Satire: 1 book; Science Fiction: 4) that giving
each its own shelf would be a shelf of one. They're folded into a plain
eleven, chosen by what a stranger would actually look for:

  Fiction, Adventure, Mystery & Horror, Fantasy & Science Fiction,
  Comedy & Satire, Children's, Drama, Poetry, Philosophy, Nonfiction,
  Biography & Memoir

A book keeps its raw genre in its own book.json/provenance.json — nothing is
discarded, only regrouped for the shelf.
"""

GENRE_TO_CATEGORY = {
    "Fiction": "Fiction",
    "Adventure": "Adventure",
    "Comedy": "Comedy & Satire",
    "Satire": "Comedy & Satire",
    "Mystery": "Mystery & Horror",
    "Horror": "Mystery & Horror",
    "Fantasy": "Fantasy & Science Fiction",
    "Science Fiction": "Fantasy & Science Fiction",
    "Drama": "Drama",
    "Poetry": "Poetry",
    "Philosophy": "Philosophy",
    "Nonfiction": "Nonfiction",
    "Autobiography": "Biography & Memoir",
    "Memoir": "Biography & Memoir",
    "Biography": "Biography & Memoir",
}

CATEGORY_ORDER = [
    "Fiction",
    "Adventure",
    "Mystery & Horror",
    "Fantasy & Science Fiction",
    "Comedy & Satire",
    "Children’s",
    "Drama",
    "Poetry",
    "Philosophy",
    "Nonfiction",
    "Biography & Memoir",
]


def category_for_genre(genre):
    """`genre` is the book's primary genre (its own first schema:genre —
    some books, mostly story collections, carry a second one describing
    format rather than content, e.g. Ashenden is "Adventure" then "Shorts";
    the first is what goes on the shelf)."""
    if genre is None:
        return "Uncategorised"
    if genre.startswith("Children"):
        return "Children’s"
    return GENRE_TO_CATEGORY.get(genre, "Uncategorised")
