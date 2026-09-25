"""Helpers for the resume-import tests: fixture text and profile, staged imports, sample files."""
import copy
import hashlib
import io
import json
from pathlib import Path

from conftest import FIXTURE_WORKSPACE

TEXT = (FIXTURE_WORKSPACE / "03-profile" / "resume.txt").read_text(encoding="utf-8")
PROFILE = json.loads((FIXTURE_WORKSPACE / "03-profile" / "profile.json").read_text(encoding="utf-8"))
TMP = "03-profile.tmp"


def profile():
    """A fresh copy of the fixture profile, which passes the check against TEXT."""
    return copy.deepcopy(PROFILE)


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def stage_text(workspace: Path, text: str, doc: dict, folder: str = TMP) -> Path:
    """Write a text import (resume.txt, source.json, profile.json) as extract_text.py and the model would."""
    target = workspace / folder
    target.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    (target / "resume.txt").write_bytes(data)
    source = {"path": "/tmp/resume.txt", "format": "txt", "sha256": sha(data), "text_sha256": sha(data)}
    (target / "source.json").write_text(json.dumps(source), encoding="utf-8")
    (target / "profile.json").write_text(json.dumps(doc), encoding="utf-8")
    return target


def _pdf_string(text: str) -> bytes:
    raw = text.encode("cp1252")
    return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def make_pdf(pages: list[list[str]], links: list[str] = ()) -> bytes:
    """A minimal PDF: each page's lines in Helvetica, link annotations on the first page."""
    body: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    next_id, page_ids = 4, []
    for number, lines in enumerate(pages):
        content_id, page_id = next_id, next_id + 1
        next_id += 2
        ops = [b"BT", b"/F1 11 Tf", b"14 TL", b"72 740 Td"]
        ops += [_pdf_string(line) + b" Tj T*" for line in lines]
        ops.append(b"ET")
        stream = b"\n".join(ops)
        body[content_id] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        annots = []
        for j, uri in enumerate(links if number == 0 else []):
            body[next_id] = (b"<< /Type /Annot /Subtype /Link /Rect [72 %d 300 %d] /Border [0 0 0] "
                             b"/A << /S /URI /URI %s >> >>" % (100 + 20 * j, 112 + 20 * j, _pdf_string(uri)))
            annots.append(b"%d 0 R" % next_id)
            next_id += 1
        extra = b" /Annots [" + b" ".join(annots) + b"]" if annots else b""
        body[page_id] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                         b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R%s >>" % (content_id, extra))
        page_ids.append(page_id)
    body[2] = b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % p for p in page_ids) + \
        b"] /Count %d >>" % len(page_ids)
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for oid in sorted(body):
        offsets[oid] = len(out)
        out += b"%d 0 obj\n" % oid + body[oid] + b"\nendobj\n"
    xref, size = len(out), max(body) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for oid in range(1, size):
        out += b"%010d 00000 n \n" % offsets[oid]
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, xref)
    return bytes(out)


def encrypt_pdf(data: bytes, user_password: str) -> bytes:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    writer.encrypt(user_password=user_password, owner_password="owner-secret")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
