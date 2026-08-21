"""The writer-input registry actually validates against its own schema.

CLAUDE.md described `content/writer-inputs.json` as schema-enforced and nothing
enforced it. The registry had drifted past the schema (a `rule_boundary` key the
schema's `additionalProperties: false` rejected) and no test would have said so.
These tests are that enforcement, plus the two invariants a reader of the registry
is entitled to assume: ids are unique, and a class read as FORM rather than as
facts says so explicitly instead of leaving it to prose.
"""

import json
from pathlib import Path

import jsonschema

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "content" / "writer-inputs.json"
SCHEMA = REPO / "scripts" / "schemas" / "writer_inputs.schema.json"


def _load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def test_registry_validates_against_its_schema():
    jsonschema.validate(_load(REGISTRY), _load(SCHEMA))


def test_source_class_ids_are_unique():
    ids = [c["id"] for c in _load(REGISTRY)["source_classes"]]
    assert len(ids) == len(set(ids)), sorted(i for i in set(ids) if ids.count(i) > 1)


def test_form_classes_declare_read_as():
    """`read_as` defaults to "facts" and the registry rule binds facts, quotes and
    storylines. A class the writer reads for register and structure instead has to
    be marked, or the rule appears to demand that its prose be traceable."""
    classes = {c["id"]: c for c in _load(REGISTRY)["source_classes"]}
    assert classes["league_exemplars"]["read_as"] == "form"
    # Everything else is facts-bound; absent means facts.
    for cid, c in classes.items():
        if cid != "league_exemplars":
            assert c.get("read_as", "facts") == "facts", cid


def test_league_exemplars_is_registered_and_points_at_the_bundle_key():
    c = {x["id"]: x for x in _load(REGISTRY)["source_classes"]}["league_exemplars"]
    assert any("league_exemplars" in p for p in c["paths"])
    assert "form" in c["what"].lower()
