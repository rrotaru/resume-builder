"""extract_text.py and check_profile.py end to end, for TXT and JSON Resume files (no dependencies needed)."""
import json
import subprocess
import sys

import check_profile
import extract_text
from conftest import REPO
from rcore import stages, validation, wsio
from samples import PROFILE, TEXT, TMP, profile, stage_text

SCRIPTS = REPO / "skills" / "resume-import" / "scripts"


def extract(workspace, *args):
    return extract_text.main(["--workspace", str(workspace), *map(str, args)])


def commit(workspace, *args):
    return check_profile.main(["--workspace", str(workspace), "--commit", *args])


def config(workspace):
    return wsio.read_json(workspace / "config.json")


def write_resume(tmp_path, text=TEXT, name="resume.txt"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_text_import_end_to_end(workspace, tmp_path, capsys):
    resume = write_resume(tmp_path, TEXT.replace("\n", "\r\n"))
    assert extract(workspace, "--resume", resume) == 0
    out = capsys.readouterr().out
    assert f"extracted {resume} (txt): 30 lines in {TMP}/resume.txt" in out
    assert f"config.json resume_path set to {resume}" in out
    assert "   1  Jordan Rivera\n   2  Backend Engineer\n" in out
    assert "  30  https://github.com/jrivera/ledger-lint" in out
    assert (workspace / TMP / "resume.txt").read_text(encoding="utf-8") == TEXT
    source = wsio.read_json(workspace / TMP / "source.json")
    assert source["path"] == str(resume) and source["format"] == "txt"
    assert config(workspace)["resume_path"] == str(resume)

    # The model maps the text; the fixture profile is a faithful mapping of it.
    wsio.write_json(workspace / TMP / "profile.json", PROFILE)
    assert commit(workspace) == 0
    assert capsys.readouterr().out == "committed 03-profile: basics, work 2, projects 1, education 1, skills 1\n"
    assert sorted(p.name for p in (workspace / "03-profile").iterdir()) == [
        "_stage.json", "profile.json", "resume.txt", "source.json"]
    assert wsio.read_json(workspace / "03-profile" / "_stage.json")["inputs"] == {}
    assert stages.status(workspace)["03-profile"] == "fresh"
    assert validation.validate_workspace(workspace) == []
    assert not (workspace / TMP).exists()


def test_failed_check_commits_nothing(workspace, capsys):
    before = (workspace / "03-profile" / "profile.json").read_text(encoding="utf-8")
    doc = profile()
    doc["work"][0]["position"] = "Staff Engineer"
    stage_text(workspace, TEXT, doc)
    assert commit(workspace) == 1
    out = capsys.readouterr().out
    assert out.splitlines() == [
        f"{TMP}/profile.json: /work/0/position: 'Staff Engineer' is not in resume.txt lines 7-8",
        "  fix: copy each value exactly as resume.txt writes it (only letter case may change), "
        "or leave it out for the wizard to ask. Never edit resume.txt.",
    ]
    assert (workspace / "03-profile" / "profile.json").read_text(encoding="utf-8") == before
    assert (workspace / TMP).is_dir()


def test_check_without_commit_and_committed(workspace, capsys):
    assert check_profile.main(["--workspace", str(workspace), "--committed"]) == 0
    assert capsys.readouterr().out == "profile check passed\n"
    assert check_profile.main(["--workspace", str(workspace)]) == 1
    assert capsys.readouterr().out == f"{TMP}: not found; run extract_text.py first\n"


def test_commit_warns_about_moved_wizard_answers(workspace, capsys):
    wsio.write_json(workspace / "decisions" / "profile.json",
                    {**wsio.read_json(workspace / "decisions" / "profile.json"),
                     "work": [{}, {"location": "Remote"}]})
    doc = profile()
    doc["work"][1]["name"] = "Contoso"
    stage_text(workspace, TEXT.replace("Software Engineer, Tailspin Toys", "Software Engineer, Contoso"), doc)
    assert commit(workspace) == 0
    assert capsys.readouterr().out.splitlines()[0] == (
        "warning: decisions/profile.json /work/1 was answered for 'Software Engineer, Tailspin Toys'; after this "
        "import /work/1 is 'Software Engineer, Contoso'. Review it with /resume-builder:wizard.")
    assert wsio.read_json(workspace / "03-profile" / "profile.json")["work"][1]["name"] == "Contoso"


def test_resume_path_from_config_is_relative_to_the_workspace(workspace, tmp_path, monkeypatch, capsys):
    write_resume(workspace, name="old-resume.txt")
    cfg = config(workspace)
    wsio.write_json(workspace / "config.json", {**cfg, "resume_path": "old-resume.txt"})
    monkeypatch.chdir(tmp_path)  # not the workspace
    assert extract(workspace) == 0
    out = capsys.readouterr().out
    assert f"extracted {(workspace / 'old-resume.txt').resolve()} (txt)" in out
    assert "resume_path set" not in out and config(workspace)["resume_path"] == "old-resume.txt"


def test_no_resume_path(workspace, capsys):
    wsio.write_json(workspace / "config.json", {**config(workspace), "resume_path": None})
    assert extract(workspace) == 1
    assert capsys.readouterr().err == (
        "error: no resume file: config.json resume_path is not set; pass --resume PATH\n")


def test_errors_leave_config_and_stage_alone(workspace, tmp_path, capsys):
    cfg = config(workspace)
    assert extract(workspace, "--resume", tmp_path / "missing.pdf") == 1
    assert capsys.readouterr().err == f"error: {tmp_path / 'missing.pdf'}: not found\n"
    doc = write_resume(tmp_path, name="resume.doc")
    assert extract(workspace, "--resume", doc) == 1
    assert "unsupported format '.doc'" in capsys.readouterr().err
    empty = write_resume(tmp_path, "  12\n", name="empty.txt")
    assert extract(workspace, "--resume", empty) == 3
    assert capsys.readouterr().err == f"error: no text found in {empty}. Provide another file, or paste the text.\n"
    assert config(workspace) == cfg
    assert not (workspace / TMP).exists()


def test_needs_a_workspace(tmp_path, capsys):
    assert extract(tmp_path / "nowhere", "--resume", write_resume(tmp_path)) == 1
    assert "config.json not found; run /resume-builder:init first" in capsys.readouterr().err


def test_unchanged_file_is_noted(workspace, tmp_path, capsys):
    resume = write_resume(tmp_path)
    assert extract(workspace, "--resume", resume) == 0
    wsio.write_json(workspace / TMP / "profile.json", PROFILE)
    assert commit(workspace) == 0
    capsys.readouterr()
    assert extract(workspace, "--resume", resume) == 0
    assert f"note: {resume} is unchanged since the last import" in capsys.readouterr().out
    resume.write_text(TEXT + "\nAWARDS\n", encoding="utf-8")
    assert extract(workspace, "--resume", resume) == 0
    assert "note:" not in capsys.readouterr().out


def test_json_resume_import_end_to_end(workspace, tmp_path, capsys):
    doc = {"$schema": "https://example.com/schema.json",
           "basics": {"name": "Jordan Rivera", "email": ""},
           "work": [{"name": "Northwind Payments", "position": "Senior Software Engineer",
                     "startDate": "2023-01-01T00:00:00Z"}]}
    resume = tmp_path / "resume.json"
    resume.write_text(json.dumps(doc), encoding="utf-8")
    assert extract(workspace, "--resume", resume) == 0
    out = capsys.readouterr().out
    assert f"loaded JSON Resume {resume} into {TMP}/profile.json: basics, work 1" in out
    assert "note: dropped /$schema\nnote: dropped 1 empty value\n" in out
    assert commit(workspace) == 0
    assert wsio.read_json(workspace / "03-profile" / "profile.json") == {
        "basics": {"name": "Jordan Rivera"},
        "work": [{"name": "Northwind Payments", "position": "Senior Software Engineer", "startDate": "2023-01-01"}]}
    assert not (workspace / "03-profile" / "resume.txt").exists()
    assert wsio.read_json(workspace / "03-profile" / "source.json")["text_sha256"] is None


def test_invalid_json_resume(workspace, tmp_path, capsys):
    resume = tmp_path / "resume.json"
    resume.write_text(json.dumps({"work": [{"endDate": "Dec 2022"}]}), encoding="utf-8")
    assert extract(workspace, "--resume", resume) == 1
    assert capsys.readouterr().err == (
        f"error: {resume}: /work/0/endDate: date 'Dec 2022' is not YYYY, YYYY-MM or YYYY-MM-DD; fix it in the file\n")


def test_scripts_run_standalone(workspace, tmp_path):
    ok = subprocess.run([sys.executable, str(SCRIPTS / "check_profile.py"), "--workspace", str(workspace),
                         "--committed"], capture_output=True, text=True)
    assert ok.returncode == 0 and ok.stdout == "profile check passed\n"
    run = subprocess.run([sys.executable, str(SCRIPTS / "extract_text.py"), "--workspace", str(workspace),
                          "--resume", str(write_resume(tmp_path))], capture_output=True, text=True)
    assert run.returncode == 0 and "30 lines in 03-profile.tmp/resume.txt" in run.stdout
