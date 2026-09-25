"""Profile answers in decisions/profile.json: where they may go, writing them under the overlay rules, moved answers.

decisions/profile.json is laid over 03-profile/profile.json by
rcore.profile.overlay: objects merge by key, arrays of objects merge by index
({} keeps an imported entry, items past the end are added), other arrays
combine. So an answer at /work/1/endDate is written as
{"work": [{}, {"endDate": "..."}]}, and an index may be at most one past the
end of the effective array, since a {} past the imported end would add an
empty entry.
"""
from __future__ import annotations

from dataclasses import dataclass

from rcore import profile as core_profile
from rcore.profile import ARRAY_FIELDS, DATE_FIELDS, LOCATION, PROFILE_ITEM, PROSE_FIELDS, SECTIONS

from .common import WIZARD_PROFILE, WizardError, compact
from .state import MISSING, State, entry_of, imported_identity, split_entry

BASICS_FIELDS = ("name", "label", "email", "phone", "url")


def tokens(pointer: str) -> list[str]:
    if not pointer.startswith("/") or pointer == "/" or "//" in pointer or pointer.endswith("/"):
        raise WizardError(f"{pointer!r} is not a JSON Pointer such as /basics/email or /work/1/endDate")
    return pointer[1:].split("/")


def _lookup(doc, parts: list[str]):
    node = doc
    for part in parts:
        if isinstance(node, dict):
            node = node.get(part)
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return None
    return node


@dataclass
class Target:
    pointer: str  # resolved: "-" replaced by the index
    parts: list[str]
    field: str
    entry: str | None  # /work/1, /basics/profiles/0, or None for basics fields
    new_entry: bool  # the index is one past the end of the effective array


def _index(parts: list[str], at: int, effective: dict, pointer: str) -> tuple[list[str], bool]:
    array_parts = parts[:at]
    array = _lookup(effective, array_parts)
    if array is not None and not (isinstance(array, list) and all(isinstance(e, dict) for e in array)):
        raise WizardError(f"{pointer}: /{'/'.join(array_parts)} in the profile is not a list of entries")
    size = len(array or [])
    token = parts[at]
    if token == "-":
        index = size
    elif token.isdigit() and (token == "0" or not token.startswith("0")):
        index = int(token)
    else:
        raise WizardError(f"{pointer}: {token!r} is not an entry number")
    if index > size:
        raise WizardError(f"{pointer}: /{'/'.join(array_parts)} has {size} "
                          f"{'entry' if size == 1 else 'entries'}; use an index up to {size} "
                          f"({size} adds an entry), or -")
    resolved = parts[:at] + [str(index)] + parts[at + 1:]
    return resolved, index == size


def target(pointer: str, effective: dict, for_add: bool = False) -> Target:
    """Check that pointer names a fact field the wizard records, and resolve "-".

    for_add: the field is a list of strings (keywords, courses, roles) that
    answer.py add extends; otherwise it is a single value.
    """
    parts = tokens(pointer)
    head = parts[0]
    new_entry = False
    if head == "basics":
        if len(parts) == 2 and parts[1] in BASICS_FIELDS and not for_add:
            field = parts[1]
        elif len(parts) == 3 and parts[1] == "location" and parts[2] in LOCATION and not for_add:
            field = parts[2]
        elif len(parts) == 4 and parts[1] == "profiles" and parts[3] in PROFILE_ITEM and not for_add:
            parts, new_entry = _index(parts, 2, effective, pointer)
            field = parts[3]
        else:
            raise WizardError(f"{pointer}: not a basics field the wizard records (name, label, email, phone, url, "
                              f"location/<{'|'.join(LOCATION)}>, profiles/<n>/<{'|'.join(PROFILE_ITEM)}>)")
    elif head in SECTIONS:
        if len(parts) != 3:
            raise WizardError(f"{pointer}: name a field of one entry, such as /{head}/0/{SECTIONS[head][0]}")
        field = parts[2]
        if field not in SECTIONS[head]:
            raise WizardError(f"{pointer}: not a {head} field (allowed: {', '.join(SECTIONS[head])})")
        if field in PROSE_FIELDS:
            raise WizardError(f"{pointer}: {field} is prose; the wizard records facts only")
        if field in ARRAY_FIELDS and not for_add:
            raise WizardError(f"{pointer}: {field} is a list; add items with answer.py add")
        if field not in ARRAY_FIELDS and for_add:
            raise WizardError(f"{pointer}: {field} is not a list; set it with answer.py profile")
        parts, new_entry = _index(parts, 1, effective, pointer)
    else:
        raise WizardError(f"{pointer}: not a JSON Resume section (allowed: basics, {', '.join(SECTIONS)})")
    resolved = "/" + "/".join(parts)
    return Target(resolved, parts, field, entry_of(resolved), new_entry)


def check_value(field: str, value: str, pointer: str) -> str:
    value = value.strip()
    if not value:
        raise WizardError(f"{pointer}: the value is empty")
    if field in DATE_FIELDS and not core_profile.is_date(value):
        raise WizardError(f"{pointer}: {value!r} is not a date written as YYYY, YYYY-MM or YYYY-MM-DD")
    return value


def _container(doc: dict, parts: list[str]):
    """The object that holds parts[-1] in doc, created as needed; arrays padded with {}."""
    node = doc
    for k, part in enumerate(parts[:-1]):
        nxt_is_index = parts[k + 1].isdigit()
        if isinstance(node, dict):
            child = node.setdefault(part, [] if nxt_is_index else {})
        elif isinstance(node, list):
            index = int(part)
            while len(node) <= index:
                node.append({})
            child = node[index]
        else:
            child = None
        if not isinstance(child, list if nxt_is_index else dict):
            raise WizardError(f"{WIZARD_PROFILE} /{'/'.join(parts[:k + 1])} is not "
                              f"{'a list' if nxt_is_index else 'an object'}; remove it with answer.py unset")
        node = child
    return node


def set_value(doc: dict, target: Target, value) -> None:
    _container(doc, target.parts)[target.parts[-1]] = value


def add_item(doc: dict, target: Target, value: str) -> None:
    holder = _container(doc, target.parts)
    items = holder.setdefault(target.parts[-1], [])
    if not isinstance(items, list):
        raise WizardError(f"{WIZARD_PROFILE} {target.pointer} is not a list; remove it with answer.py unset")
    if value not in items:
        items.append(value)


def _tidy(doc: dict) -> None:
    """Trim trailing {} from arrays of objects, and drop objects and arrays left empty."""
    def walk(node):
        if isinstance(node, dict):
            for key in list(node):
                node[key] = walk(node[key])
                if node[key] in ({}, []):
                    del node[key]
        elif isinstance(node, list):
            node[:] = [walk(item) for item in node]
            if all(isinstance(item, dict) for item in node):
                while node and node[-1] == {}:
                    node.pop()
        return node
    walk(doc)


def unset(doc: dict, pointer: str) -> None:
    """Remove the wizard's answer at pointer. Raises WizardError when there is none."""
    parts = tokens(pointer)
    holder = _lookup(doc, parts[:-1])
    last = parts[-1]
    if isinstance(holder, dict) and last in holder:
        del holder[last]
    elif isinstance(holder, list) and last.isdigit() and int(last) < len(holder) and holder[int(last)] not in ({},):
        if isinstance(holder[int(last)], dict):
            holder[int(last)] = {}
        else:
            del holder[int(last)]
    else:
        raise WizardError(f"{WIZARD_PROFILE} has no answer at {pointer}")
    _tidy(doc)


def answer_at(doc: dict, entry: str):
    """The wizard's answer object for an entry, or None."""
    node = _lookup(doc, entry.strip("/").split("/"))
    return node if isinstance(node, dict) and node else None


def check_entry(pointer: str) -> str:
    entry = entry_of(pointer)
    if entry is None or entry != pointer:
        raise WizardError(f"{pointer!r} is not an entry such as /work/1 or /basics/profiles/0")
    return entry


# Moved answers -------------------------------------------------------------------

@dataclass
class Moved:
    entry: str
    section: str
    answer: dict
    anchored: bool
    was: dict | None  # the identity it was answered for (anchored only)
    now: dict | None  # the identity of the imported entry there now
    suggest: int | None  # where to move it, if anywhere

    def describe(self) -> str:
        sect = f"{'an' if self.section[0] in 'aeiou' else 'a'} {self.section}"
        if not self.anchored:
            where = (f"it merges into the imported '{core_profile.describe(self.section, self.now)}'"
                     if self.now is not None else f"it adds {sect} entry")
            return f"{compact(self.answer)} has no record of the entry it was answered for; {where}"
        if self.was is None:
            return (f"{compact(self.answer)} added {sect} entry; {self.entry} is now the imported "
                    f"'{core_profile.describe(self.section, self.now)}', which it merges into")
        base = f"{compact(self.answer)} was answered for '{core_profile.describe(self.section, self.was)}'; "
        if self.now is None:
            return base + f"there is no imported {self.entry} now, so it adds a new entry"
        return base + f"{self.entry} is now '{core_profile.describe(self.section, self.now)}'"


def moved_answers(imported: dict, wizard: dict, state: State) -> list[Moved]:
    """Non-empty answers in arrays of objects whose anchor is missing or no longer matches."""
    found = []
    for pointer, section, answers in core_profile.merged_arrays(wizard):
        if not all(isinstance(a, dict) for a in answers):
            continue
        imported_list = _lookup(imported, pointer.strip("/").split("/"))
        imported_list = imported_list if isinstance(imported_list, list) else []
        for i, answer in enumerate(answers):
            if not answer:
                continue
            entry = f"{pointer}/{i}"
            now = imported_identity(imported, entry)
            was = state.anchor(entry)
            if was is not MISSING and was == now:
                continue
            found.append(Moved(entry, section, answer, was is not MISSING, None if was is MISSING else was, now,
                               _suggest(section, was, imported_list, answers, i)))
    return found


def _suggest(section: str, was, imported_list: list, answers: list, i: int) -> int | None:
    if was is MISSING:
        return None
    if was is not None:
        for j, entry in enumerate(imported_list):
            if j != i and core_profile.identity(section, entry) == was:
                return j
        return None
    return max(len(imported_list), len(answers))


def is_pending(entry: str | None, moved: list[Moved]) -> bool:
    return entry is not None and any(m.entry == entry for m in moved)


def anchor_new_entries(before: dict, after: dict, imported: dict, state: State) -> None:
    """Anchor each entry that has an answer now but had none before; drop anchors of entries left without one."""
    for pointer, _, answers in core_profile.merged_arrays(after):
        for i, answer in enumerate(answers):
            entry = f"{pointer}/{i}"
            if isinstance(answer, dict) and answer and answer_at(before, entry) is None:
                state.anchors[entry] = imported_identity(imported, entry)
    for entry in list(state.anchors):
        if answer_at(after, entry) is None:
            del state.anchors[entry]


def move(doc: dict, source: str, dest: str, effective: dict) -> None:
    """Move the answer at source to dest in the same array. Raises WizardError."""
    s_array, _, s_index = split_entry(source)
    d_array, _, d_index = split_entry(dest)
    if s_array != d_array:
        raise WizardError(f"{source} and {dest} are in different lists")
    if source == dest:
        raise WizardError(f"{source} is already there; use answer.py confirm {source}")
    answer = answer_at(doc, source)
    if answer is None:
        raise WizardError(f"{WIZARD_PROFILE} has no answer at {source}")
    if answer_at(doc, dest) is not None:
        raise WizardError(f"{WIZARD_PROFILE} already has an answer at {dest}; move or remove that one first")
    size = len(_lookup(effective, d_array.strip("/").split("/")) or [])
    if d_index > size:
        raise WizardError(f"{dest}: {d_array} has {size} entries; use an index up to {size} ({size} adds an entry)")
    array = _lookup(doc, s_array.strip("/").split("/"))
    while len(array) <= d_index:
        array.append({})
    array[d_index] = answer
    array[s_index] = {}
    _tidy(doc)
