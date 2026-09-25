"""Text formats and line normalization (rimport.extract), which need no dependencies."""
import pytest
from rimport import extract

BODY = "Jordan Rivera\nBackend Engineer\nSenior Software Engineer at Northwind Payments since 2023\n"


def test_format_of():
    assert extract.format_of("a/resume.PDF") == "pdf"
    assert extract.format_of("resume.markdown") == "md"
    assert extract.format_of("resume.json") == "json"
    for name in ("resume.doc", "resume.rtf", "resume.odt", "resume.pages", "resume"):
        with pytest.raises(extract.ExtractError, match="unsupported format .* save it as PDF, DOCX, TXT"):
            extract.format_of(name)


def test_line_breaks_all_become_newlines():
    text = "Jordan Rivera\r\nBackend\rEngineer\vA\fB\x1cC\x1dD\x1eE\x85F G H\n" + BODY
    out = extract.normalize_lines(text)
    assert out.splitlines() == out.rstrip("\n").split("\n")
    assert out.startswith("Jordan Rivera\nBackend\nEngineer\nA\nB\nC\nD\nE\nF\nG\nH\n")


def test_tabs_controls_trailing_spaces_and_blank_runs():
    text = "\n\n  Jordan\tRivera  \x00\x07\n\n\n\nBackend Engineer \n\n" + BODY + "\n\n\n"
    assert extract.normalize_lines(text) == "  Jordan Rivera\n\nBackend Engineer\n\n" + BODY


def test_links_are_appended_once_in_order():
    out = extract.normalize_lines(BODY, ["https://b.example", "ftp://skip.example", " https://a.example ",
                                         "https://b.example", "mailto:j@example.com", "javascript:alert(1)"])
    assert out == BODY + "\nLinks in the document:\nhttps://b.example\nhttps://a.example\nmailto:j@example.com\n"


def test_too_few_letters_is_no_text():
    with pytest.raises(extract.NoText, match=r"^no text found in scan.pdf \(2 pages\)\. It looks like a scanned PDF"):
        extract.normalize_lines("  12  \n\n 3 ", ["https://example.com/" + "x" * 80], "scan.pdf", pages=2)
    with pytest.raises(extract.NoText, match=r"^no text found in notes.txt\. Provide another file"):
        extract.normalize_lines("Short text", (), "notes.txt")


@pytest.mark.parametrize("data", [
    BODY.encode("utf-8"),
    b"\xef\xbb\xbf" + BODY.encode("utf-8"),
    BODY.encode("utf-16"),  # with a BOM
    BODY.encode("utf-16-be").join([b"\xfe\xff", b""]),
])
def test_txt_encodings(data):
    assert extract.extract(data, "txt", "resume.txt").text == BODY


def test_txt_must_be_utf8():
    with pytest.raises(extract.ExtractError, match="resume.txt is not UTF-8 text; save it as UTF-8"):
        extract.extract(BODY.encode("cp1252") + b"\xe9", "txt", "resume.txt")


def test_markdown_is_kept_as_written():
    md = "# Jordan Rivera\n\n**Backend Engineer** | [GitHub](https://github.com/jrivera)\n\n" + BODY
    assert extract.extract(md.encode(), "md", "resume.md").text == md


def test_content_must_match_the_extension():
    with pytest.raises(extract.ExtractError, match="resume.pdf: not a PDF file, although its name says so"):
        extract.extract(BODY.encode(), "pdf", "resume.pdf")
    with pytest.raises(extract.ExtractError, match="resume.docx: not a DOCX file"):
        extract.extract(b"%PDF-1.4", "docx", "resume.docx")
