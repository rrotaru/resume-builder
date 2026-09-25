"""Fill templates/classic.html from the render model.

The page is self-contained: CSS inline and Carlito embedded as data: URIs,
so printing it needs no network access. Autoescaping is on for every value.
"""
from __future__ import annotations

import base64
from pathlib import Path

import jinja2

from .model import DASH, SEP, Document

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
FONTS = {"regular": "Carlito-Regular.woff2", "bold": "Carlito-Bold.woff2"}


def _data_uri(name: str) -> str:
    data = (TEMPLATES / "fonts" / name).read_bytes()
    return "data:font/woff2;base64," + base64.b64encode(data).decode("ascii")


def render(doc: Document) -> str:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATES),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    fonts = {weight: _data_uri(name) for weight, name in FONTS.items()}
    return env.get_template("classic.html").render(doc=doc, fonts=fonts, dash=DASH, sep=SEP)
