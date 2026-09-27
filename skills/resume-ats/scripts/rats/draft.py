"""The draft resume ats.py writes for a version, and the form the commit writes back.

The draft copies every fact field tailored-resume.schema.json allows from the
effective profile, exactly, and puts every bullet of 07-sanitized/bullets.json
that has a place under the entry for it, in file order. The model then leaves
out, orders and rewords; it never types a fact.

- basics: name, email, phone, url; location city, region and countryCode
  (render never shows the street address or postal code); each profiles
  item's network, username and url. label is config.json target_role when
  set, else the profile's label. summary is the sanitized profile's summary,
  citing resume:/basics/summary, when the imported profile has one.
- One entry per entry of work, projects, education, certificates and skills,
  in profile order, with the fields the schema allows. A value that does not
  fit the schema is left out (the fact check then names it).
- skills keywords holding a denied term are left out: a keyword cannot be
  replaced, since keywords combine in the overlay.
"""
from __future__ import annotations

from rcore import schema, terms

from .common import one_line
from .material import SECTIONS, Material

LOCATION_SHOWN = ("city", "countryCode", "region")
BULLET_FIELDS = ("highlights", "x-highlights")
ENTRY_SECTIONS = ("work", "projects", "education", "certificates", "skills")


def _spec() -> dict:
    return schema.load_schema("tailored-resume")


def _node(spec: dict, node: dict) -> dict:
    """A schema node, following a local $ref."""
    while "$ref" in node:
        node = spec["$defs"][node["$ref"].rsplit("/", 1)[-1]]
    return node


def _fits(value, node: dict, spec: dict) -> bool:
    return not schema.validate(value, node, spec)


def _copy(source: dict, node: dict, spec: dict, skip=()) -> dict:
    """The fields of source that node allows and whose values fit, in schema order."""
    props = _node(spec, node).get("properties", {})
    return {f: source[f] for f, sub in props.items()
            if f not in skip and f in source and _fits(source[f], sub, spec)}


def _basics(material: Material, spec: dict) -> dict:
    found = material.effective.get("basics")
    found = found if isinstance(found, dict) else {}
    node = spec["properties"]["basics"]
    basics = _copy(found, node, spec, skip=("label", "location", "profiles", "summary", "x-summary-sources"))
    role = material.inputs.target_role
    label = role or found.get("label")
    if isinstance(label, str) and label:
        basics["label"] = label
    if isinstance(found.get("location"), dict):
        location = {k: v for k, v in _copy(found["location"], node["properties"]["location"], spec).items()
                    if k in LOCATION_SHOWN}
        if location:
            basics["location"] = location
    if isinstance(found.get("profiles"), list):
        item = node["properties"]["profiles"]["items"]
        profiles = [copied for p in found["profiles"] if isinstance(p, dict) for copied in [_copy(p, item, spec)]
                    if copied]
        if profiles:
            basics["profiles"] = profiles
    imported = (material.inputs.profile or {}).get("basics")
    sanitized = (material.inputs.sanitized_profile or {}).get("basics")
    summary = sanitized.get("summary") if isinstance(sanitized, dict) else None
    if isinstance(imported, dict) and isinstance(imported.get("summary"), str) and isinstance(summary, str) \
            and summary.strip():
        basics["summary"] = one_line(summary)
        basics["x-summary-sources"] = ["resume:/basics/summary"]
    return normalize_object(basics, node, spec)


def _placed(material: Material) -> dict[tuple[str, int], list[dict]]:
    found: dict[tuple[str, int], list[dict]] = {}
    for bullet in material.bullets:
        where = material.place(bullet)
        if where is not None:
            found.setdefault(where, []).append(bullet)
    return found


def withheld(material: Material) -> list[tuple[str, str, list[str]]]:
    """(pointer, keyword, denied terms) for each skills keyword of the effective profile holding a denied term."""
    found = []
    for i, entry in enumerate(material.entries("skills")):
        keywords = entry.get("keywords") if isinstance(entry, dict) else None
        for k, keyword in enumerate(keywords if isinstance(keywords, list) else []):
            held = terms.terms_in(keyword, material.patterns) if isinstance(keyword, str) else []
            if held:
                found.append((f"/skills/{i}/keywords/{k}", keyword, held))
    return found


def build(material: Material) -> dict:
    """The draft resume: every fact from the profile, every placed bullet in its place."""
    spec = _spec()
    resume = {"basics": _basics(material, spec)}
    placed = _placed(material)
    denied = {pointer for pointer, _, _ in withheld(material)}
    for section in ENTRY_SECTIONS:
        item = spec["properties"][section]["items"]
        entries = []
        for i, source in enumerate(material.entries(section)):
            if not isinstance(source, dict):
                continue
            entry = _copy(source, item, spec, skip=BULLET_FIELDS)
            if section == "skills" and "keywords" in entry:
                entry["keywords"] = [k for j, k in enumerate(entry["keywords"])
                                     if f"/skills/{i}/keywords/{j}" not in denied]
                if not entry["keywords"]:
                    del entry["keywords"]
            if section in SECTIONS:
                entry["x-highlights"] = [{"bullet_id": b["id"], "text": b["text"], "sources": list(b["sources"])}
                                         for b in placed.get((section, i), [])]
            elif not entry:
                continue
            entries.append(entry)
        if entries:
            resume[section] = entries
    return normalize(resume)


def normalize_object(value: dict, node: dict, spec: dict) -> dict:
    """value with keys in schema order, recursively; keys the schema does not name keep their place at the end."""
    node = _node(spec, node)
    props = node.get("properties", {})
    out = {k: normalize_value(value[k], props[k], spec) for k in props if k in value}
    out.update({k: v for k, v in value.items() if k not in props})
    return out


def normalize_value(value, node: dict, spec: dict):
    node = _node(spec, node)
    if isinstance(value, dict):
        return normalize_object(value, node, spec)
    if isinstance(value, list) and "items" in node:
        return [normalize_value(v, node["items"], spec) for v in value]
    return value


def normalize(resume: dict) -> dict:
    """The resume as the commit writes it: highlights set to the x-highlights texts, keys in schema order."""
    for section in SECTIONS:
        for entry in resume.get(section, []):
            if isinstance(entry, dict) and isinstance(entry.get("x-highlights"), list):
                entry["highlights"] = [h.get("text") if isinstance(h, dict) else h for h in entry["x-highlights"]]
    return normalize_object(resume, _spec(), _spec())
