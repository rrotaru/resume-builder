"""Local git repositories: reading the engineer's commits, and turning them into evidence."""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path

from . import refs
from .common import CollectError, Draft, Result, clean, excerpt, iterate, parse_timestamp, raw_ref

SOURCE = "git"
FORMAT = "%x00%H%x1f%an%x1f%ae%x1f%aI%x1f%B%x00"
REFS = ("--branches", "--remotes", "--tags")
# Keep the output parseable whatever the engineer's git config says.
PLAIN = ("--no-show-signature", "--no-color", "--encoding=UTF-8")
_SHORTSTAT = re.compile(r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?")
_SHA = re.compile(r"[0-9a-f]{40}([0-9a-f]{24})?")
_SQUASH = re.compile(r"\(#(\d+)\)\s*$")
_WEB_HOSTS = {"github.com": "{path}/commit/{sha}", "gitlab.com": "{path}/-/commit/{sha}"}


def _git(repo: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, stdin=subprocess.DEVNULL,
                             check=True)
    except FileNotFoundError as exc:
        raise CollectError("git is not installed") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise CollectError(f"{repo}: git {args[0]} failed: {message[-1] if message else exc.returncode}") from exc
    return out.stdout.decode("utf-8", "replace")


def is_work_tree(path: Path) -> bool:
    try:
        return _git(Path(path), "rev-parse", "--is-inside-work-tree").strip() == "true"
    except CollectError:
        return False


def remote_path(url: str | None) -> str | None:
    """host/path of a remote URL: git@github.com:o/r.git, ssh://git@host:22/o/r, https://host/o/r.git."""
    if not url:
        return None
    url = url.strip()
    match = (re.match(r"^[a-z][a-z0-9+.-]*://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$", url, re.IGNORECASE)
             or re.match(r"^(?:[^@/]+@)?([^/:]+):(?!//)(.+)$", url))
    if not match:
        return None
    path = match.group(2).strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return f"{match.group(1).lower()}/{path}" if path else None


def _origin(repo: Path) -> str | None:
    try:
        return remote_path(_git(repo, "remote", "get-url", "origin").strip())
    except CollectError:
        return None


def matches(name: str, email: str, authors: list[str]) -> bool:
    """Exact, case-insensitive: an identity with "@" is an email, anything else a name."""
    for identity in authors:
        target = email if "@" in identity else name
        if target.strip().casefold() == identity.strip().casefold():
            return True
    return False


def parse_log(output: str) -> list[dict]:
    """Commits from git log --shortstat --format=FORMAT."""
    parts = output.split("\x00")
    commits = []
    for record, stat in zip(parts[1::2], parts[2::2] + [""] * len(parts)):
        fields = record.split("\x1f", 4)
        if len(fields) != 5:
            continue
        sha, name, email, authored, message = fields
        match = _SHORTSTAT.search(stat)
        files, additions, deletions = (int(g or 0) for g in match.groups()) if match else (0, 0, 0)
        commits.append({"sha": sha.strip(), "author_name": name, "author_email": email,
                        "authored_at": authored.strip(), "message": message.strip("\n"),
                        "files": files, "additions": additions, "deletions": deletions})
    return commits


def read_repo(repo: Path, authors: list[str], time_range: dict) -> tuple[list[dict], list[str]]:
    """The engineer's commits in one repository, newest first, and a note when there are none."""
    repo = Path(repo)
    if not is_work_tree(repo):
        raise CollectError(f"{repo}: not a git work tree")
    args = ["log", *PLAIN, *REFS, "--no-merges", "-F", "-i", *(f"--author={a}" for a in authors),
            "--shortstat", f"--format={FORMAT}"]
    remote = _origin(repo)
    commits = []
    seen = set()
    for commit in parse_log(_git(repo, *args)):
        authored = parse_timestamp(commit["authored_at"])
        if commit["sha"] in seen or not matches(commit["author_name"], commit["author_email"], authors):
            continue
        if authored is None:
            continue
        date = authored[:10]
        if (time_range.get("start") and date < time_range["start"]) or (
                time_range.get("end") and date > time_range["end"]):
            continue
        seen.add(commit["sha"])
        commits.append({"sha": commit["sha"], "repo": str(repo), "remote": remote, **{
            k: commit[k] for k in ("author_name", "author_email", "authored_at", "message",
                                   "files", "additions", "deletions")}})
    notes = []
    if not commits:
        notes.append(f"{repo}: no commits by {', '.join(authors)} in the time range "
                     f"(git log {' '.join(REFS)} --no-merges -F -i "
                     f"{' '.join('--author=' + a for a in authors)})")
        top = frequent_authors(repo)
        if top:
            notes.append("  most frequent authors there: " + "; ".join(f"{who} ({n})" for who, n in top))
    return commits, notes


def frequent_authors(repo: Path, limit: int = 5) -> list[tuple[str, int]]:
    try:
        out = _git(repo, "log", *PLAIN, *REFS, "--no-merges", "--format=%an <%ae>")
    except CollectError:
        return []
    return Counter(line for line in out.splitlines() if line.strip()).most_common(limit)


def commit_url(remote: str | None, sha: str) -> str | None:
    if not remote or "/" not in remote:
        return None
    host, path = remote.split("/", 1)
    template = _WEB_HOSTS.get(host)
    return f"https://{host}/" + template.format(path=path, sha=sha) if template else None


def normalize(pages, rel: str, label: str, time_range: dict | None) -> Result:
    result = Result(SOURCE, label)
    for page, index, item in iterate(pages, result):
        sha = item.get("sha")
        created = parse_timestamp(item.get("authored_at"))
        message = item.get("message") if isinstance(item.get("message"), str) else None
        problem = ("no commit hash" if not isinstance(sha, str) or not _SHA.fullmatch(sha.lower())
                   else "no message" if message is None
                   else f"authored_at {item.get('authored_at')!r} is not a timestamp" if created is None
                   else None)
        if problem:
            result.bad_row(page.line, problem, index)
            continue
        sha = sha.lower()
        subject, _, body = message.partition("\n")
        remote = item.get("remote") if isinstance(item.get("remote"), str) else None
        path = remote.split("/", 1)[1] if remote and "/" in remote else None
        stats = {k: item.get(v) for k, v in (("additions", "additions"), ("deletions", "deletions"),
                                               ("files", "files"))}
        draft = Draft(
            source=SOURCE, kind="commit", native_key=sha, title=clean(subject), engineer_role="author",
            created_at=created, raw_ref=raw_ref(rel, page.line, index), url=commit_url(remote, sha),
            excerpt=excerpt(body),
            stats=stats if all(isinstance(v, int) and not isinstance(v, bool) and v >= 0
                               for v in stats.values()) else None,
            sha=sha,
        )
        draft.refs = refs.find(message, github_repo=path, gitlab_project=path)
        squash = _SQUASH.search(subject)
        if squash and path:
            draft.squash_of = ("github", f"{path}#{squash.group(1)}")
        result.keep(draft, created, time_range)
    return result
