import random

import pikepdf
import pytest

from conftest import make_pdf, page_ids
from folio.core import MergeError, Part, _ranges_arg, merge, natural_key, page_count, parse_ranges


def test_natural_sort():
    names = ["Chapter 10.pdf", "chapter 2.pdf", "Chapter 1.pdf", "Appendix.pdf"]
    assert sorted(names, key=natural_key) == ["Appendix.pdf", "Chapter 1.pdf", "chapter 2.pdf", "Chapter 10.pdf"]


@pytest.mark.parametrize("spec, expected", [
    ("", None),
    ("  ", None),
    ("3", [3]),
    ("1-3, 5", [1, 2, 3, 5]),
    ("8-", [8, 9, 10]),
    ("3-1", [3, 2, 1]),
    ("2,2", [2, 2]),
])
def test_parse_ranges(spec, expected):
    assert parse_ranges(spec, 10) == expected


@pytest.mark.parametrize("spec", ["0", "11", "1-11", "a", "1-2-3", "-3", "1,,2"])
def test_parse_ranges_rejects(spec):
    with pytest.raises(MergeError):
        parse_ranges(spec, 10)


@pytest.mark.parametrize("pages, arg", [
    ([1, 2, 3, 7, 6], "1-3,7-6"),
    ([5], "5"),
    ([5, 5], "5,5"),
    ([1, 3, 5], "1,3,5"),
    ([4, 3, 2, 1, 2], "4-1,2"),
])
def test_ranges_arg(pages, arg):
    assert _ranges_arg(pages) == arg


def test_merge_keeps_exact_order_across_hundreds_of_files(tmp_path, pdfs):
    # more files than qpdf keeps open at once (200), in a shuffled order, with 1-3 pages each
    files = pdfs([i % 3 + 1 for i in range(450)])
    random.Random(0).shuffle(files)
    out = tmp_path / "out.pdf"
    total = merge([Part(f, f.stem) for f in files], out, bookmarks=False)
    expected = [pid for f in files for pid in page_ids(f)]
    assert total == len(expected)
    assert page_ids(out) == expected


def test_merge_page_ranges(tmp_path, pdfs):
    a, b = pdfs([5, 4])
    out = tmp_path / "out.pdf"
    merge([Part(a, "A", [4, 2]), Part(b, "B"), Part(a, "A again", [5])], out, bookmarks=False)
    assert page_ids(out) == [(100, 4), (100, 2), (101, 1), (101, 2), (101, 3), (101, 4), (100, 5)]


def test_bookmarks_point_at_each_file(tmp_path, pdfs):
    files = pdfs([3, 2, 4])
    out = tmp_path / "Book.pdf"
    merge([Part(f, f"Chapter {i}") for i, f in enumerate(files, 1)], out)
    with pikepdf.open(out) as pdf, pdf.open_outline() as outline:
        titles = [item.title for item in outline.root]
        targets = [pdf.pages.index(pikepdf.Page(item.destination[0])) for item in outline.root]
        assert pdf.open_metadata()["dc:title"] == "Book"
    assert titles == ["Chapter 1", "Chapter 2", "Chapter 3"]
    assert targets == [0, 3, 5]
    assert not (tmp_path / "Book.pdf.part").exists()


def test_page_count_and_friendly_errors(tmp_path):
    assert page_count(make_pdf(tmp_path / "ok.pdf", 100, 7)) == 7
    locked = make_pdf(tmp_path / "locked.pdf", 100, password="secret")
    with pytest.raises(MergeError, match="password-protected"):
        page_count(locked)
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"this is not a pdf")
    with pytest.raises(MergeError, match="damaged or not a PDF"):
        page_count(junk, "My Scan.pdf")
    with pytest.raises(MergeError, match="My Scan.pdf"):
        merge([Part(junk, "My Scan.pdf")], tmp_path / "out.pdf")


def test_merge_rejects_empty(tmp_path):
    with pytest.raises(MergeError):
        merge([], tmp_path / "out.pdf")
