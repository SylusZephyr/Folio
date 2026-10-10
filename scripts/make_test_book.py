r"""Generate a large test "book" for trying Folio at scale, and verify a merged result.

  python scripts/make_test_book.py                   # writes test-book/Chapter 1.pdf ... Chapter 120.pdf
  python scripts/make_test_book.py --check book.pdf  # verifies a merged book is complete and in order

Every page is stamped "Chapter N / Page p of P / Book page n", so the order is also easy to check by eye.
About 38,000 pages and 105 MB in total; two chapters carry an image on every page to make them heavy.
"""
import argparse
import os
import random
import re
import sys
from pathlib import Path

import pikepdf

OUT = Path(__file__).resolve().parent.parent / "test-book"
CHAPTERS = 120
HEAVY = {7, 42}  # chapters with a unique incompressible image on every page (~200 KB/page)


def page_counts():
    rng = random.Random(1)  # fixed seed: same book every run, so --check knows what to expect
    return {c: rng.randint(100, 500) for c in range(1, CHAPTERS + 1)}


def make():
    OUT.mkdir(exist_ok=True)
    counts = page_counts()
    book_page = 0
    for c, n in counts.items():
        pdf = pikepdf.new()
        font = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                                                    BaseFont=pikepdf.Name.Helvetica))
        for p in range(1, n + 1):
            book_page += 1
            text = (f"BT /F1 40 Tf 72 690 Td (Chapter {c}) Tj 0 -56 Td /F1 26 Tf (Page {p} of {n}) Tj "
                    f"0 -40 Td /F1 16 Tf (Book page {book_page}) Tj ET\n")
            res = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
            if c in HEAVY:
                img = pikepdf.Stream(pdf, os.urandom(256 * 256 * 3), Type=pikepdf.Name.XObject,
                                     Subtype=pikepdf.Name.Image, Width=256, Height=256,
                                     ColorSpace=pikepdf.Name.DeviceRGB, BitsPerComponent=8)
                res.XObject = pikepdf.Dictionary(Im1=img)
                text += "q 400 0 0 400 106 120 cm /Im1 Do Q\n"
            page = pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, 612, 792], Resources=res,
                                      Contents=pikepdf.Stream(pdf, text.encode()))
            pdf.pages.append(pikepdf.Page(page))
        f = OUT / f"Chapter {c}.pdf"  # unpadded names on purpose: order must be 1, 2, ... 10, not 1, 10, 100
        pdf.save(f)
        print(f"\r{f.name}  ({n} pages)        ", end="", flush=True)
    total = sum(f.stat().st_size for f in OUT.glob("*.pdf"))
    print(f"\n{CHAPTERS} PDFs, {book_page} pages, {total / 1e6:.0f} MB in {OUT}")


def check(book):
    expected = [(c, p) for c, n in page_counts().items() for p in range(1, n + 1)]
    with pikepdf.open(book) as pdf:
        if len(pdf.pages) != len(expected):
            sys.exit(f"FAIL: {len(pdf.pages)} pages, expected {len(expected)}")
        for i, (page, (c, p)) in enumerate(zip(pdf.pages, expected), 1):
            m = re.search(rb"\(Chapter (\d+)\).*?\(Page (\d+) of", page.Contents.read_bytes())
            if not m or (int(m[1]), int(m[2])) != (c, p):
                sys.exit(f"FAIL at book page {i}: expected chapter {c} page {p}, got {m and m.groups()}")
    print(f"PASS: all {len(expected)} pages present and in exact order")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", metavar="MERGED_PDF")
    a = ap.parse_args()
    check(a.check) if a.check else make()
