"""Text of a document file (PDF, DOCX, TXT, Markdown), normalized for line citations.

Used by resume-import for the resume and by resume-collect for performance
reviews. pypdf and python-docx are imported inside the functions that need
them, so rcore still imports with the standard library alone; only reading a
PDF or DOCX needs them (scripts that do pin them in their PEP 723 block).

normalize_lines() makes str.splitlines() and a plain count of "\\n" agree,
because the model cites lines by number: every line break becomes "\\n",
tabs become spaces, other control characters go, trailing spaces go, runs of
blank lines become one, and link targets found in the file are appended
under LINKS_HEADER.
"""
from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass

FORMATS = {".pdf": "pdf", ".docx": "docx", ".txt": "txt", ".md": "md", ".markdown": "md"}
LINKS_HEADER = "Links in the document:"
MIN_LETTERS = 50
LINK_SCHEMES = ("http://", "https://", "mailto:")
# Characters str.splitlines() breaks on, besides "\n".
_LINE_BREAKS = ("\r\n", "\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", " ", " ")
_FIELD_LINK = re.compile(r'HYPERLINK\s+"([^"]+)"')


class ExtractError(Exception):
    """The file cannot be read."""


class NoText(ExtractError):
    """The file holds no usable text, for example a scanned PDF."""


@dataclass(frozen=True)
class Extracted:
    text: str  # normalized, ends with "\n"
    pages: int | None = None  # PDF only


def check_magic(data: bytes, fmt: str, name: str) -> None:
    # A PDF may have up to 1024 bytes before its header; a DOCX is a ZIP archive.
    if (fmt == "pdf" and b"%PDF-" not in data[:1024]) or (fmt == "docx" and not data.startswith(b"PK")):
        raise ExtractError(f"{name}: not a {fmt.upper()} file, although its name says so")


def _links(targets) -> list[str]:
    seen, out = set(), []
    for target in targets:
        target = target.strip()
        if target.lower().startswith(LINK_SCHEMES) and target not in seen:
            seen.add(target)
            out.append(target)
    return out


def normalize_lines(text: str, links=(), name: str = "the file", pages: int | None = None) -> str:
    """Normalize extracted text (see the module docstring). Raises NoText if it has too few letters."""
    for brk in _LINE_BREAKS:
        text = text.replace(brk, "\n")
    text = text.replace("\t", " ")
    text = "".join(c for c in text if c == "\n" or unicodedata.category(c) != "Cc")
    lines: list[str] = []
    for line in (raw.rstrip() for raw in text.split("\n")):
        if line or (lines and lines[-1]):
            lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    if sum(c.isalpha() for line in lines for c in line) < MIN_LETTERS:
        if pages is not None:
            raise NoText(f"no text found in {name} ({pages} page{'s' if pages != 1 else ''}). "
                         "It looks like a scanned PDF, and OCR is not supported. "
                         "Provide a DOCX or TXT version, or paste the text.")
        raise NoText(f"no text found in {name}. Provide another file, or paste the text.")
    links = _links(links)
    if links:
        lines += ["", LINKS_HEADER, *links]
    return "\n".join(lines) + "\n"


# PDF -------------------------------------------------------------------------

def _pdf_uri(annotation) -> str | None:
    annotation = annotation.get_object()
    if annotation.get("/Subtype") != "/Link":
        return None
    action = annotation.get("/A")
    uri = action.get_object().get("/URI") if action is not None else None
    if hasattr(uri, "get_object"):
        uri = uri.get_object()
    if isinstance(uri, bytes):
        return uri.decode("latin-1")
    return str(uri) if uri is not None else None


def _pdf(data: bytes, name: str) -> Extracted:
    from pypdf import PasswordType, PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                unlocked = reader.decrypt("") != PasswordType.NOT_DECRYPTED
            except Exception:  # noqa: BLE001 - an unsupported cipher is as locked as a password
                unlocked = False
            if not unlocked:
                raise ExtractError(f"{name} is password-protected; save an unprotected copy")
        texts, links = [], []
        for page in reader.pages:
            texts.append(page.extract_text() or "")
            for annotation in (page["/Annots"] if "/Annots" in page else None) or []:
                uri = _pdf_uri(annotation)
                if uri:
                    links.append(uri)
        pages = len(reader.pages)
    except ExtractError:
        raise
    except Exception as exc:  # noqa: BLE001 - pypdf raises many types for a damaged file
        raise ExtractError(f"{name}: cannot be read as a PDF ({exc})") from exc
    return Extracted(normalize_lines("\n\n".join(texts), links, name, pages), pages)


# DOCX ------------------------------------------------------------------------

def _docx(data: bytes, name: str) -> Extracted:
    import docx
    from docx.oxml.ns import qn

    mc_fallback = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
    w_p, w_r, w_t = qn("w:p"), qn("w:r"), qn("w:t")
    breaks = {qn("w:br"): "\n", qn("w:cr"): "\n", qn("w:tab"): " ", qn("w:noBreakHyphen"): "-"}
    r_id = qn("r:id")

    def hidden(element) -> bool:
        run = next(element.iterancestors(w_r), None)
        props = run.find(qn("w:rPr")) if run is not None else None
        vanish = props.find(qn("w:vanish")) if props is not None else None
        return vanish is not None and vanish.get(qn("w:val"), "true").lower() not in ("0", "false", "off")

    def paragraph_text(p) -> str:
        parts = []
        for element in p.iter(w_t, *breaks):
            if next(element.iterancestors(w_p), None) is not p or hidden(element):
                continue  # a nested (text box) paragraph is visited on its own
            parts.append((element.text or "") if element.tag == w_t else breaks[element.tag])
        return "".join(parts)

    def walk(root, part, texts: list[str], links: list[str]) -> None:
        for p in root.iter(w_p):
            if any(a.tag == mc_fallback for a in p.iterancestors()):
                continue  # the fallback copy of a text box
            texts.append(paragraph_text(p))
        for link in root.iter(qn("w:hyperlink")):
            rel = part.rels.get(link.get(r_id)) if link.get(r_id) else None
            if rel is not None and rel.is_external:
                links.append(rel.target_ref)
        for instruction in root.iter(qn("w:instrText")):
            links += _FIELD_LINK.findall(instruction.text or "")

    try:
        document = docx.Document(io.BytesIO(data))
        headers, footers = [], []
        seen = set()
        for section in document.sections:
            for kind, target in (("header", headers), ("footer", footers)):
                for attr in (f"first_page_{kind}", kind, f"even_page_{kind}"):
                    item = getattr(section, attr)
                    if item.is_linked_to_previous or id(item.part) in seen:
                        continue
                    seen.add(id(item.part))
                    target.append((item._element, item.part))
        texts: list[str] = []
        links: list[str] = []
        for root, part in [*headers, (document.element.body, document.part), *footers]:
            walk(root, part, texts, links)
    except Exception as exc:  # noqa: BLE001 - python-docx raises many types for a damaged file
        raise ExtractError(f"{name}: cannot be read as a DOCX ({exc})") from exc
    return Extracted(normalize_lines("\n".join(texts), links, name))


# TXT and Markdown ------------------------------------------------------------

def decode_text(data: bytes, name: str) -> str:
    try:
        if data.startswith(b"\xef\xbb\xbf"):
            return data[3:].decode("utf-8")
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            return data.decode("utf-16")
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExtractError(f"{name} is not UTF-8 text; save it as UTF-8") from exc


def extract(data: bytes, fmt: str, name: str) -> Extracted:
    """Extract and normalize the text of a pdf, docx, txt or md file's bytes."""
    check_magic(data, fmt, name)
    if fmt == "pdf":
        return _pdf(data, name)
    if fmt == "docx":
        return _docx(data, name)
    if fmt in ("txt", "md"):
        return Extracted(normalize_lines(decode_text(data, name), (), name))
    raise ExtractError(f"{name}: {fmt} is not a text format")
