from rcore.schema import SCHEMA_DIR, load_schema


def test_every_schema_file_loads():
    names = sorted(p.name[: -len(".schema.json")] for p in SCHEMA_DIR.glob("*.schema.json"))
    assert len(names) >= 12
    for name in names:
        assert load_schema(name)["$schema"].startswith("https://json-schema.org/")
