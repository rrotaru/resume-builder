from rcore.schema import load_schema


def test_every_schema_file_loads():
    for name in ["config", "stage", "evidence", "resume", "projects", "bullets", "terms",
                 "term-candidates", "project-decisions", "metrics", "attestations", "flags"]:
        assert load_schema(name)["$schema"].startswith("https://json-schema.org/")
