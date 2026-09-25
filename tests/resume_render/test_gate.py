from rcore import wsio
from rrender import gate

GENERAL = "08-ats/general/resume.json"
JOB = "08-ats/jobs/fintech-sre/resume.json"


def edit(workspace, rel, change):
    data = wsio.read_json(workspace / rel)
    change(data)
    wsio.write_json(workspace / rel, data)


def lines(problems):
    return [(p.group, p.line, p.fix) for p in problems]


def test_discover_every_tailored_resume(workspace):
    targets, errors = gate.discover(workspace)
    assert errors == [] and [t.name for t in targets] == ["general", "fintech-sre"]
    assert targets[1].resume == JOB and targets[1].flags == "08-ats/jobs/fintech-sre/flags.json"
    assert targets[0].flags is None and targets[0].folder == "general"


def test_discover_requested_targets(workspace):
    targets, errors = gate.discover(workspace, ["fintech-sre", "general", "fintech-sre"])
    assert errors == [] and [t.name for t in targets] == ["fintech-sre", "general"]
    assert gate.discover(workspace, ["../x", "Job"])[1] == [
        "../x: not a target (use general or a job slug)", "Job: not a target (use general or a job slug)"]


def test_nothing_to_render(tmp_path):
    assert gate.discover(tmp_path) == ([], ["nothing to render; run /resume-builder:ats"])


def test_inputs_are_every_file_render_reads(workspace):
    targets, _ = gate.discover(workspace)
    assert gate.inputs(workspace, targets) == [
        GENERAL, JOB, "08-ats/jobs/fintech-sre/flags.json", "config.json", "decisions/terms.json",
        "decisions/profile.json", "decisions/metrics.json", "decisions/attestations.json",
        "02-evidence/evidence.jsonl", "03-profile/profile.json", "07-sanitized/stories.md"]
    (workspace / "decisions" / "attestations.json").unlink()
    assert "decisions/attestations.json" not in gate.inputs(workspace, targets)


def test_fixture_passes(workspace):
    targets, _ = gate.discover(workspace)
    assert gate.run(workspace, targets) == []


def test_validation_failure_stops_the_gate(workspace):
    def break_everything(resume):
        resume["awards"] = [{"title": "Engineer of the year"}]
        resume["work"][0]["position"] = "CTO"
        resume["work"][0]["x-highlights"][0]["text"] = "Shipped Project Falcon"
    edit(workspace, GENERAL, break_everything)
    targets, _ = gate.discover(workspace)
    assert lines(gate.run(workspace, targets)) == [
        ("general", f"{GENERAL}: $.awards: unexpected property", "/resume-builder:ats")]


def test_validation_of_shared_files_names_their_owner(workspace):
    wsio.write_json(workspace / "decisions" / "metrics.json", [{"id": "m_1"}])
    (workspace / "08-ats" / "jobs" / "fintech-sre" / "flags.json").unlink()
    targets, _ = gate.discover(workspace)
    problems = lines(gate.run(workspace, targets))
    assert ("fintech-sre", "08-ats/jobs/fintech-sre/flags.json: not found",
            "/resume-builder:ats for job fintech-sre") in problems
    assert all(fix == "/resume-builder:wizard" for group, _, fix in problems if group == "shared")
    assert any(group == "shared" for group, _, _ in problems)


def test_every_later_check_reports_in_one_run(workspace):
    edit(workspace, GENERAL, lambda r: r["basics"].pop("name"))
    edit(workspace, GENERAL, lambda r: r["work"][1]["x-highlights"][0].update(sources=["ev_deadbeef"]))
    edit(workspace, JOB, lambda r: r["work"][0].update(position="CTO"))
    edit(workspace, JOB, lambda r: r["projects"][0].update(name="Project Falcon"))
    wsio.write_json(workspace / "decisions" / "attestations.json", [])
    targets, _ = gate.discover(workspace)
    assert lines(gate.run(workspace, targets)) == [
        ("general", f"{GENERAL}: basics.name is required to render",
         "/resume-builder:wizard to add the name, then /resume-builder:ats"),
        ("general", f"{GENERAL}: bullet b_3: ev_deadbeef: unknown evidence id",
         "/resume-builder:ats; if the bullet itself is wrong, /resume-builder:write first"),
        ("fintech-sre", f"{JOB}: /work/0: position 'CTO' does not match the profile "
         "(closest entry /work/0 has 'Senior Software Engineer')",
         "/resume-builder:ats for job fintech-sre to copy the profile value; "
         "if the profile is wrong, /resume-builder:wizard first"),
        ("fintech-sre", f"{JOB}: /projects/0: name 'Project Falcon' does not match the profile "
         "(closest entry /projects/0 has 'ledger-lint')",
         "/resume-builder:ats for job fintech-sre to copy the profile value; "
         "if the profile is wrong, /resume-builder:wizard first"),
        ("fintech-sre", f"{JOB}:/projects/0/name: contains denylisted term 'Project Falcon'",
         "/resume-builder:wizard to set a replacement value at /projects/0/name, "
         "then /resume-builder:ats for job fintech-sre"),
        ("fintech-sre", "08-ats/jobs/fintech-sre: b_1 is flagged (introduces 'SLO compliance', which no "
         "cited source mentions); accept, revert or edit it",
         "accept, revert or edit it at checkpoint 4 (/resume-builder:build resumes there)"),
    ]


def test_denied_term_in_a_bullet_points_to_sanitize(workspace):
    def change(resume):
        text = "Moved Contoso Bank checkout to Go"
        resume["work"][1]["x-highlights"][0]["text"] = text
        resume["work"][1]["highlights"][0] = text
    edit(workspace, GENERAL, change)
    targets, _ = gate.discover(workspace, ["general"])
    assert lines(gate.run(workspace, targets)) == [
        ("general", f"{GENERAL}:/work/1/highlights/0: contains denylisted term 'Contoso Bank'",
         "/resume-builder:sanitize, then /resume-builder:ats; for a false positive, "
         "an allowed term the engineer agrees to"),
        ("general", f"{GENERAL}:/work/1/x-highlights/0/text: contains denylisted term 'Contoso Bank'",
         "/resume-builder:sanitize, then /resume-builder:ats; for a false positive, "
         "an allowed term the engineer agrees to"),
    ]


def test_bullet_changed_after_the_claim_diff(workspace):
    def change(resume):
        resume["work"][0]["x-highlights"][1]["text"] = "Mentored four new engineers"
        resume["work"][0]["highlights"][1] = "Mentored four new engineers"
    edit(workspace, JOB, change)
    targets, _ = gate.discover(workspace, ["fintech-sre"])
    assert lines(gate.run(workspace, targets)) == [
        ("fintech-sre", "08-ats/jobs/fintech-sre: b_2 changed after the claim diff; re-run the claim diff",
         "/resume-builder:ats for job fintech-sre (re-runs the claim diff)")]


def test_stories_are_terms_checked(workspace):
    (workspace / gate.STORIES).write_text("Led Project Falcon.\n", encoding="utf-8")
    targets, _ = gate.discover(workspace)
    assert lines(gate.run(workspace, targets)) == [
        ("shared", "07-sanitized/stories.md:1: contains denylisted term 'Project Falcon'",
         "/resume-builder:sanitize to rewrite 07-sanitized/stories.md")]


def test_unsanitized_stories_are_not_checked_or_needed(workspace):
    (workspace / gate.STORIES).unlink()
    targets, _ = gate.discover(workspace)
    assert gate.run(workspace, targets) == []  # 06-bullets/stories.md names Project Falcon


def test_missing_terms_file_fails_closed(workspace):
    (workspace / "decisions" / "terms.json").unlink()
    targets, _ = gate.discover(workspace, ["general"])
    assert lines(gate.run(workspace, targets)) == [
        ("shared", "decisions/terms.json: not found; run init_workspace.py",
         "/resume-builder:wizard to fix decisions/terms.json")]


def test_badly_named_job_folder_fails_closed(workspace):
    (workspace / "08-ats" / "jobs" / "fintech-sre").rename(workspace / "08-ats" / "jobs" / "Fintech_SRE")
    targets, _ = gate.discover(workspace)
    problems = lines(gate.run(workspace, targets))
    assert ("Fintech_SRE", "Fintech_SRE: job slug must be a single plain name",
            "/resume-builder:ats for job Fintech_SRE (re-runs the claim diff)") in problems
