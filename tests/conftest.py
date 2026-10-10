import pikepdf
import pytest


def make_pdf(path, tag, pages=1, password=None):
    """A PDF whose page i has MediaBox width `tag` and height 1000 + i, so tests can tell pages apart."""
    pdf = pikepdf.new()
    for i in range(1, pages + 1):
        pdf.add_blank_page(page_size=(tag, 1000 + i))
    enc = pikepdf.Encryption(owner=password, user=password) if password else None
    pdf.save(path, encryption=enc)
    return path


def page_ids(path):
    """[(tag, page_number), ...] for every page of a PDF."""
    with pikepdf.open(path) as pdf:
        return [(int(p.mediabox[2]), int(p.mediabox[3]) - 1000) for p in pdf.pages]


@pytest.fixture
def pdfs(tmp_path):
    """Factory: pdfs([3, 1, 2]) -> files 0.pdf.. with that many pages each, tagged 100, 101, ..."""
    def build(page_counts):
        return [make_pdf(tmp_path / f"{i}.pdf", 100 + i, n) for i, n in enumerate(page_counts)]
    return build
