"""The steps of a run, the state of each, and the one command that continues the first step not done."""
from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass
from pathlib import Path

from rcore import config, stages, wsio

from . import common, final, jobs
from .common import CONFIG, DECISION_FILES, DECISIONS, SOURCE, BuildError, load, plural

# Each stage step, and the stage whose state is the step's.
STAGE_OF = {"collect": "02-evidence", "import": "03-profile", "analyze": "04-projects", "scan": "05-terms",
            "write": "06-bullets", "apply": "07-sanitized", "ats": "08-ats", "render": "out"}
ORDER = ("init", "collect", "import", "analyze", "scan", "wizard", "write", "apply", "ats", "review", "render")
DONE = ("done", "fresh", "none")
GATED = ("write", "apply", "ats")  # checkpoint 3 comes first, unless a draft is being continued
WIZARD_GATE = "wizard: checkpoint 3 until questions.py prints 'wizard: no open questions' (resume-wizard)"
NOTHING = ("nothing: every stage is fresh and out/ holds the resumes; for another posting, ats.py --jd FILE "
           "(resume-ats), then checkpoint 4 and render")
NEVER_BEGIN_RAW = "never run stage.py begin 01-raw, which deletes it"


@dataclass
class Step:
    name: str
    state: str
    note: str = ""
    action: str = ""  # what to do when this step is next

    @property
    def number(self) -> int:
        return ORDER.index(self.name) + 1


def _age(day: str) -> str:
    try:
        days = (common.today() - datetime.date.fromisoformat(day)).days
    except ValueError:
        return day
    return "today" if days <= 0 else f"{plural(days, 'day')} ago"


def stale_note(reasons: list[tuple[str, str]]) -> str:
    """What makes a stage stale: '<input> changed', '<input> is gone', '<stage> is stale'."""
    parts = []
    for rel, why in reasons:
        text = {"changed": f"{rel} changed", "missing": f"{rel} is gone"}.get(why)
        text = text or f"{rel.split('/', 1)[0]} is stale"
        if text not in parts:
            parts.append(text)
    return "; ".join(parts)


def _only(reasons: list[tuple[str, str]], inputs: set[str]) -> bool:
    """True when every reason is one of inputs changing or going, and no stage upstream is stale."""
    return bool(reasons) and all(why != "stale" and rel in inputs for rel, why in reasons)


def _extra(workspace: Path, stage: str) -> dict:
    data, _ = wsio.load(workspace, f"{stage}/{stages.META}")
    return data if isinstance(data, dict) else {}


class Survey:
    """Reads the workspace once and gives each step its state."""

    def __init__(self, workspace: Path):
        self.ws = Path(workspace)
        self.reasons = stages.stale_inputs(self.ws) if self.ws.is_dir() else {}
        self.config = load(self.ws, CONFIG)

    def tmp(self, stage: str) -> Path | None:
        path = self.ws / f"{stage}.tmp"
        return path if path.is_dir() else None

    def committed(self, stage: str) -> bool:
        return stage in self.reasons

    def stale(self, stage: str) -> list[tuple[str, str]]:
        return self.reasons.get(stage, [])

    def meta(self, stage: str) -> dict:
        return _extra(self.ws, stage)

    # The steps ------------------------------------------------------------

    def init(self) -> Step:
        if self.config is None:
            return Step("init", "missing", "no config.json", "create the workspace and config.json (resume-init)")
        missing = [f"{DECISIONS}/{name}" for name in DECISION_FILES if not (self.ws / DECISIONS / name).is_file()]
        if missing:
            return Step("init", "missing", f"{', '.join(missing)} missing",
                        "run resume-init again: init_workspace.py creates only what is missing")
        return Step("init", "done", "config.json and decisions/")

    def collect(self) -> Step:
        tmp = self.tmp("01-raw")
        if tmp is not None:
            partial = sorted(p.name for p in tmp.glob("*.partial.jsonl"))
            if partial:
                return Step("collect", "draft", f"01-raw.tmp/{partial[0]}: a paused fetch",
                            f"continue the paused fetch in 01-raw.tmp/ (resume-collect step 5); {NEVER_BEGIN_RAW}")
            return Step("collect", "draft", "01-raw.tmp/: a collection in progress",
                        f"continue the collection in 01-raw.tmp/ (resume-collect steps 5 to 8); {NEVER_BEGIN_RAW}")
        if not self.committed("02-evidence"):
            if self.committed("01-raw"):
                return Step("collect", "missing", "01-raw is committed, 02-evidence is not built",
                            "link.py builds 02-evidence from the committed 01-raw (resume-collect step 8)")
            note = "nothing collected"
            if self.config is not None and not self.config.get("data_notice_acknowledged_at"):
                note += "; the data notice is not accepted yet"
            return Step("collect", "missing", note, "checkpoint 1: confirm the sources and collect (resume-collect)")
        if self.stale("02-evidence"):
            return Step("collect", "stale", stale_note(self.stale("02-evidence")),
                        "01-raw changed since 02-evidence was built: link.py (resume-collect step 8)")
        return Step("collect", "fresh", self._collect_note())

    def _collect_note(self) -> str:
        meta = self.meta("02-evidence")
        items = (meta.get("extra") or {}).get("items")
        note = ""
        if isinstance(items, dict):
            detail = ", ".join(f"{source} {n}" for source, n in items.items())
            note = f"{plural(sum(items.values()), 'item')} ({detail}), "
        built = str(meta.get("created_at", ""))[:10]
        if not built:
            return note.rstrip(", ")
        note += f"built {built} ({_age(built)})"
        end = ((self.config or {}).get("time_range") or {}).get("end")
        if _age(built) != "today" and (end is None or end > built):
            note += ("; the time range is open, so work since then is not in it" if end is None else
                     f"; the time range ends {end}, so work since then is not in it")
        return note

    def import_(self) -> Step:
        tmp = self.tmp("03-profile")
        if tmp is not None:
            if (tmp / "profile.json").is_file():
                return Step("import", "draft", "03-profile.tmp/profile.json: waiting for the check",
                            "check and commit it with check_profile.py --commit (resume-import step 5)")
            if (tmp / "resume.txt").is_file():
                return Step("import", "draft", "03-profile.tmp/resume.txt: waiting to be mapped",
                            "map 03-profile.tmp/resume.txt into profile.json, then check_profile.py --commit "
                            "(resume-import steps 4 and 5)")
            return Step("import", "draft", "03-profile.tmp/: empty", "run extract_text.py again (resume-import)")
        resume_path = (self.config or {}).get("resume_path")
        path = str(config.resolve_path(self.ws, resume_path)) if resume_path else None
        if not self.committed("03-profile"):
            if path is None:
                return Step("import", "none", "no resume in config.json: the engineer has none, or checkpoint 1 "
                            "records it")
            if not Path(path).is_file():
                return Step("import", "missing", f"{path} is not found",
                            f"{path} is not found: ask the engineer for the resume (resume-import)")
            return Step("import", "missing", path, f"import {path} (resume-import)")
        if self.stale("03-profile"):
            return Step("import", "stale", stale_note(self.stale("03-profile")), "import it again (resume-import)")
        source = load(self.ws, SOURCE)
        if source is None:
            return Step("import", "fresh", f"{SOURCE} is missing")
        again = ("import it again (resume-import); wizard answers the new import moves become moved: questions "
                 "(resume-wizard)")
        if path is None:
            return Step("import", "fresh", f"config.json names no resume; the import of {source['path']} stays")
        if path != source["path"]:
            return Step("import", "changed", f"config.json names {path}, not the imported {source['path']}", again)
        try:
            digest = "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()
        except OSError:
            return Step("import", "fresh", f"{path} is no longer there; the import stays")
        if digest != source["sha256"]:
            return Step("import", "changed", f"{path} changed since the import", again)
        return Step("import", "fresh", f"{path}, unchanged since the import")

    def analyze(self) -> Step:
        tmp = self.tmp("04-projects")
        if tmp is not None:
            if (tmp / "groups.json").is_file():
                return Step("analyze", "draft", "04-projects.tmp/groups.json: checkpoint 2 in progress",
                            "continue checkpoint 2 with match_projects.py (resume-analyze step 5)")
            if (tmp / "signals.json").is_file():
                return Step("analyze", "draft", "04-projects.tmp/signals.json: grouping in progress",
                            "group the evidence into 04-projects.tmp/groups.json (resume-analyze step 3)")
            return Step("analyze", "draft", "04-projects.tmp/: empty", "run signals.py again (resume-analyze step 2)")
        if not self.committed("04-projects"):
            return Step("analyze", "missing", "", "checkpoint 2: find and review the projects (resume-analyze)")
        reasons = self.stale("04-projects")
        if reasons:
            if _only(reasons, {"decisions/projects.json", CONFIG}):
                action = ("apply it to the committed grouping: stage.py begin 04-projects --from-current, then "
                          "match_projects.py (resume-analyze step 5)")
            else:
                action = ("the evidence changed: group again with signals.py, starting from the last groups.json "
                          "(resume-analyze)")
            return Step("analyze", "stale", stale_note(reasons), action)
        extra = self.meta("04-projects").get("extra") or {}
        note = ""
        if {"projects", "excluded", "metric_prompts", "decisions"} <= set(extra):
            note = (f"{plural(extra['projects'], 'project')} ({extra['excluded']} excluded), metric prompts for "
                    f"{extra['metric_prompts']}, {plural(extra['decisions'], 'decision')}")
        return Step("analyze", "fresh", note)

    def scan(self) -> Step:
        tmp = self.tmp("05-terms")
        if tmp is not None:
            if (tmp / "candidates.json").is_file():
                return Step("scan", "draft", "05-terms.tmp/candidates.json: waiting for the check",
                            "scan.py --commit (resume-sanitize, scan step 5)")
            return Step("scan", "draft", "05-terms.tmp/: scan.py began", "scan.py again (resume-sanitize, scan)")
        if not self.committed("05-terms"):
            return Step("scan", "missing", "", "scan.py (resume-sanitize, scan)")
        if self.stale("05-terms"):
            return Step("scan", "stale", stale_note(self.stale("05-terms")), "scan.py (resume-sanitize, scan)")
        extra = self.meta("05-terms").get("extra") or {}
        return Step("scan", "fresh", plural(extra["candidates"], "candidate") if "candidates" in extra else "")

    def write(self) -> Step:
        tmp = self.tmp("06-bullets")
        committed = self.committed("06-bullets")
        again = "write.py" + (" --from-current" if committed else "")
        if tmp is not None:
            if (tmp / "bullets.json").is_file():
                return Step("write", "draft", "06-bullets.tmp/bullets.json: waiting for the check",
                            "write.py --commit (resume-write step 6)")
            return Step("write", "draft", "06-bullets.tmp/: write.py began",
                        f"{again} again, then write.py --commit (resume-write)")
        if not committed:
            return Step("write", "missing", "", "write the bullets and stories: write.py, then write.py --commit "
                        "(resume-write)")
        reasons = self.stale("06-bullets")
        if reasons:
            if _only(reasons, {"decisions/profile.json", "decisions/metrics.json"}):
                action = ("a wizard answer: recommit the bullets with write.py --from-current, then write.py "
                          "--commit; bullets that still pass keep their IDs, and a new metric needs a bullet that "
                          "cites it (resume-write)")
            else:
                action = "revise the bullets: write.py --from-current, then write.py --commit (resume-write)"
            return Step("write", "stale", stale_note(reasons), action)
        extra = self.meta("06-bullets").get("extra") or {}
        note = ""
        if {"bullets", "quantified", "stories"} <= set(extra):
            note = (f"{plural(extra['bullets'], 'bullet')} ({extra['quantified']} quantified), "
                    f"{plural(extra['stories'], 'story', 'stories')}")
        return Step("write", "fresh", note)

    def apply(self) -> Step:
        tmp = self.tmp("07-sanitized")
        commit = "apply.py, then apply.py --commit (resume-sanitize, apply)"
        if tmp is not None:
            if (tmp / "new-terms.json").is_file():
                return Step("apply", "draft", "07-sanitized.tmp/new-terms.json: waiting for the check",
                            "apply.py --commit; if it says the inputs changed, apply.py again "
                            "(resume-sanitize, apply step 5)")
            return Step("apply", "draft", "07-sanitized.tmp/: apply.py began", commit)
        if not self.committed("07-sanitized"):
            return Step("apply", "missing", "", commit)
        if self.stale("07-sanitized"):
            return Step("apply", "stale", stale_note(self.stale("07-sanitized")), commit)
        extra = self.meta("07-sanitized").get("extra") or {}
        note = ""
        if {"bullets", "changed_bullets", "new_terms"} <= set(extra):
            note = (f"{extra['changed_bullets']} of {plural(extra['bullets'], 'bullet')} changed, "
                    f"{plural(extra['new_terms'], 'new term')}")
        return Step("apply", "fresh", note)

    def ats(self) -> Step:
        tmp = self.tmp("08-ats")
        if tmp is not None:
            names = ["general"] if (tmp / "general").is_dir() else []
            if (tmp / "jobs").is_dir():
                names += sorted(p.name for p in (tmp / "jobs").iterdir() if p.is_dir())
            return Step("ats", "draft", f"08-ats.tmp/ with {', '.join(names) or 'no version'}",
                        "continue with ats.py --commit, or start over from the committed stage with stage.py begin "
                        "08-ats --from-current (resume-ats)")
        if not self.committed("08-ats"):
            return Step("ats", "missing", "", "draft and commit the general resume, then each posting (resume-ats)")
        if self.stale("08-ats"):
            return Step("ats", "stale", stale_note(self.stale("08-ats")),
                        "re-check every version: stage.py begin 08-ats --from-current, then ats.py --commit; redraft "
                        "a version it refuses (ats.py, ats.py --job SLUG) or remove it (ats.py --remove SLUG) "
                        "(resume-ats)")
        versions = jobs.committed_versions(self.ws)
        note = ", ".join(versions)
        slugs = [v for v in versions if v != jobs.GENERAL]
        if slugs:
            attestations = jobs.load_attestations(self.ws)
            flagged = opened = 0
            for slug in slugs:
                job = jobs.load_job(self.ws, slug)
                flagged += len(job.flags["flags"])
                opened += sum(s.is_open for s in jobs.flag_states(job, attestations))
            note += f": {flagged} flagged, {opened} open"
        return Step("ats", "fresh", note)

    def review(self, ats: Step) -> Step:
        if ats.state != "fresh":
            return Step("review", "waiting", "checkpoint 4 comes after ats")
        count = len(final.open_items(self.ws))
        if count:
            return Step("review", "open", f"checkpoint 4: {plural(count, 'open item')}",
                        "checkpoint 4: final_review.py lists the open items")
        return Step("review", "ready", "checkpoint 4: no open items",
                    "checkpoint 4 (final_review.py), then render (resume-render)")

    def render(self) -> Step:
        if not self.committed("out"):
            return Step("render", "missing", "", "render (resume-render)")
        if self.stale("out"):
            return Step("render", "stale", stale_note(self.stale("out")), "render again (resume-render)")
        extra = self.meta("out").get("extra") or {}
        targets = extra.get("targets")
        note = ""
        if isinstance(targets, list):
            files = "PDF, DOCX and TXT" if extra.get("pdf") else "DOCX and TXT"
            note = f"{', '.join(targets)} ({files})"
        return Step("render", "fresh", note)


def survey(workspace: Path) -> list[Step]:
    """Every step with its state, in order. Raises BuildError on an invalid input."""
    s = Survey(workspace)
    ats = s.ats()
    return [s.init(), s.collect(), s.import_(), s.analyze(), s.scan(),
            Step("wizard", "check", "checkpoint 3: questions.py lists what is open"),
            s.write(), s.apply(), ats, s.review(ats), s.render()]


def next_step(steps: list[Step]) -> str:
    """The one step to continue: the first in order that is not done, with checkpoint 3 before a new write,
    apply or ats."""
    by_name = {step.name: step for step in steps}
    for step in steps:
        if step.name == "wizard" or step.state in DONE or step.state == "waiting":
            continue
        if step.name == "review" and step.state == "ready" and by_name["render"].state == "fresh":
            continue
        if step.name == "render" and by_name["review"].state != "ready":
            continue
        if step.name in GATED and step.state != "draft":
            return f"{WIZARD_GATE}; then {step.name}: {step.action}"
        return f"{step.name}: {step.action}"
    return NOTHING


def lines(workspace: Path, steps: list[Step]) -> list[str]:
    cfg = load(workspace, CONFIG) or {}
    role = cfg.get("target_role")
    header = f"resume-builder run in {Path(workspace).resolve()}" + (f" (target role: {role})" if role else "")
    rows = [f"{step.number:>2}. {step.name:<8} {step.state:<8} {step.note}".rstrip() for step in steps]
    return [header, *rows, f"next: {next_step(steps)}"]


__all__ = ["BuildError", "Step", "survey", "next_step", "lines", "stale_note", "STAGE_OF"]
