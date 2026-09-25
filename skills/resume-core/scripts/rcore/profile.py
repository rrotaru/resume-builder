"""Effective profile: the imported profile with the wizard's answers laid over it.

03-profile/profile.json is the base and decisions/profile.json is laid over it:
- two objects merge key by key;
- two arrays whose items are all objects merge by index: wizard item i merges
  onto imported item i, wizard items past the end are added, and {} leaves an
  imported item unchanged;
- two other arrays (such as keywords) combine: imported items, then wizard
  items not already present;
- in every other case the wizard's value replaces the imported one.

A missing or unreadable file, or one that is not a JSON object, counts as {}.
The fact-field check and the basics.label check compare against this profile;
wizard: source references still point into the raw decisions/profile.json.
"""
from __future__ import annotations

import copy
from pathlib import Path

from . import wsio

IMPORTED = "03-profile/profile.json"
WIZARD = "decisions/profile.json"


def _merge(imported, wizard):
    if isinstance(imported, dict) and isinstance(wizard, dict):
        merged = dict(imported)
        for key, value in wizard.items():
            merged[key] = _merge(imported[key], value) if key in imported else value
        return merged
    if isinstance(imported, list) and isinstance(wizard, list):
        if all(isinstance(item, dict) for item in imported + wizard):
            merged = [_merge(item, wizard[i]) if i < len(wizard) else item
                      for i, item in enumerate(imported)]
            return merged + wizard[len(imported):]
        combined = list(imported)
        for item in wizard:
            if item not in combined:
                combined.append(item)
        return combined
    return wizard


def overlay(imported, wizard):
    """Lay wizard answers over an imported profile. Returns a new structure."""
    return copy.deepcopy(_merge(imported, wizard))


def _read_object(workspace: Path, rel: str) -> dict:
    data, _ = wsio.load(workspace, rel)
    return data if isinstance(data, dict) else {}


def effective_profile(workspace: Path) -> dict:
    workspace = Path(workspace)
    return overlay(_read_object(workspace, IMPORTED), _read_object(workspace, WIZARD))
