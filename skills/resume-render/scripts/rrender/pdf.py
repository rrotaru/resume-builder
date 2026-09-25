"""Print the filled HTML to PDF with Playwright's Chromium.

JavaScript is off and every request is aborted, so a resume cannot make the
renderer fetch anything. The PDF's metadata is rewritten to hold only the
title and author.
"""
from __future__ import annotations

import io

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from pypdf import PdfReader, PdfWriter

PAPER = {"letter": "Letter", "a4": "A4"}
MARGIN = "0.6in"


class ChromiumMissing(RuntimeError):
    """Playwright has no Chromium build installed."""


class ChromiumFailed(RuntimeError):
    """Chromium is installed but did not start."""


class Chromium:
    """One browser for a whole render. Use as a context manager."""

    def __enter__(self) -> "Chromium":
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch()
        except PlaywrightError as exc:
            self._playwright.stop()
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message:
                raise ChromiumMissing(message) from None
            raise ChromiumFailed(message) from None
        return self

    def __exit__(self, *exc) -> None:
        self._browser.close()
        self._playwright.stop()

    def print_pdf(self, html: str, paper: str) -> tuple[bytes, list[str]]:
        """Return the PDF bytes and the URLs of any requests that were blocked."""
        blocked: list[str] = []

        def block(route) -> None:
            blocked.append(route.request.url)
            route.abort()

        context = self._browser.new_context(java_script_enabled=False, offline=True)
        try:
            context.route("**/*", block)
            page = context.new_page()
            page.set_content(html, wait_until="load")
            pdf = page.pdf(
                format=PAPER[paper],
                margin={side: MARGIN for side in ("top", "right", "bottom", "left")},
                print_background=False,
                display_header_footer=False,
            )
        finally:
            context.close()
        return pdf, blocked


def finish(pdf: bytes, title: str, author: str) -> tuple[bytes, int]:
    """Replace the PDF's metadata with the title and author. Returns (bytes, page count)."""
    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter(clone_from=reader)
    writer.metadata = None
    writer.add_metadata({"/Title": title, "/Author": author})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue(), len(reader.pages)


def text(path) -> str:
    """The PDF's text layer, as an ATS would read it."""
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
