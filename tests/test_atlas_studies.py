"""Studies of the rat ↔ human pairs of Neuro Atlas (v188): the MeSH table, the most specific
descriptor, text matches, the fetch and the warehouse query. No network."""

import datetime as dt
import json
import tomllib
from pathlib import Path

import duckdb
import httpx

from synaptica.atlas import studies

ATLAS = Path(studies.__file__).parent

# A tiny MeSH: Corpus Striatum holds Globus Pallidus; Brain Stem holds the cerebellum.
ROWS = [
    {"ui": "D1", "name": "Corpus Striatum", "tree": "A.1", "term": "Corpus Striatum"},
    {"ui": "D2", "name": "Globus Pallidus", "tree": "A.1.2", "term": "Globus Pallidus"},
    {"ui": "D2", "name": "Globus Pallidus", "tree": "A.1.2", "term": "Pallidum"},
    {"ui": "D3", "name": "Caudate Nucleus", "tree": "A.1.3", "term": "Caudate Nucleus"},
    {"ui": "D4", "name": "Brain Stem", "tree": "A.4", "term": "Brainstem"},
    {"ui": "D5", "name": "Cerebellum", "tree": "A.4.5", "term": "Cerebellum"},
    {"ui": "D6", "name": "Pons", "tree": "A.4.6", "term": "Pons"},
    {"ui": "D7", "name": "Cortex, Motor", "tree": "A.7", "term": "Cortex, Motor"},
]
TERMS = {"striatum": ["D1"], "pallidum": ["D2"], "brainstem": ["D4"], "cerebellum": ["D5"]}


def test_the_table_names_every_pair_once_with_descriptors_of_the_vocabulary():
    kinds = [p["kind"] for p in tomllib.loads((ATLAS / "pairs.toml").read_text())["pair"]]
    terms = studies.region_terms()
    assert sorted(terms) == sorted(kinds)
    uis = {r["ui"] for r in studies.vocabulary()}
    assert all(ui in uis for mesh in terms.values() for ui in mesh)
    by_ui = studies.descriptor_kinds(studies.vocabulary(), terms)
    assert all(by_ui[ui] == kind for kind, mesh in terms.items() for ui in mesh)


def test_a_descriptor_goes_to_the_most_specific_root():
    by_ui = studies.descriptor_kinds(ROWS, TERMS)
    assert by_ui == {"D1": "striatum", "D2": "pallidum", "D3": "striatum", "D4": "brainstem",
                     "D5": "cerebellum", "D6": "brainstem"}  # fmt: skip
    real = studies.descriptor_kinds(studies.vocabulary(), studies.region_terms())
    assert real["D005917"] == "pallidum" and real["D002421"] == "striatum"  # pallidum; caudate
    assert real["D002531"] == "cerebellum" and real["D056547"] == "internal"  # CA1


def test_text_needs_one_mention_in_the_title_or_two_in_the_abstract():
    m = studies.Matcher(ROWS, TERMS)
    assert m.text("Dopamine in the globus pallidus") == {"pallidum"}
    assert m.text("A study", "the pons and nothing else") == set()
    assert m.text("A study", "The pons. Again the pons.") == {"brainstem"}
    assert m.text("Cortex, Motor") == set()  # inverted forms are not prose; no pair anyway
    assert m.text("Opponens muscles") == set()  # whole words only
    assert m.mesh(["D3"], ["cerebellum"]) == {"striatum", "cerebellum"}


def test_fetch_pages_through_the_endpoint_and_sorts(tmp_path, monkeypatch):
    monkeypatch.setattr(studies, "PAGE", 2)
    pages = [
        [("D2", "B", "A.2", "b"), ("D1", "A", "A.1", "a")],
        [("D1", "A", "A.1", "a2")],
    ]
    asked = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(int(request.url.params["offset"]))
        assert 'STRSTARTS(?tn, "A08.186.211.")' in request.url.params["query"]
        rows = pages[len(asked) - 1]
        return httpx.Response(200, json={"results": {"bindings": [
            {"d": {"value": f"http://id.nlm.nih.gov/mesh/{u}"}, "name": {"value": n},
             "tn": {"value": t}, "term": {"value": x}} for u, n, t, x in rows]}})  # fmt: skip

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rows = studies.fetch(client)
    assert asked == [0, 2]
    assert [r["term"] for r in rows] == ["a", "a2", "b"]
    path = tmp_path / "v.json"
    assert studies.write_vocabulary(rows, path) and not studies.write_vocabulary(rows, path)
    assert json.loads(path.read_text()) == rows


def warehouse(path: Path) -> Path:
    with duckdb.connect(str(path)) as con:
        con.execute("""create table dim_study (study_id varchar, pmid varchar, doi varchar,
            pmcid varchar, sources varchar[], title varchar, species varchar,
            entered_on date, published_on date, is_neuro boolean, news_type varchar)""")
        con.execute("create table int_pubmed__records (pmid varchar, mesh_uis varchar[], "
                    "keywords varchar[])")  # fmt: skip
        d = dt.date(2026, 11, 10)
        con.executemany("insert into dim_study values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
            ("s1", "1", None, None, ["pubmed"], "Rats and the pallidum", "animals", d, d, True,
             None),
            ("s2", "2", None, None, ["pubmed"], "No region in this title", "humans", d, d, True,
             "disease"),
            ("s3", None, "10.1/x", None, ["biorxiv"], "Globus pallidus in mice", "unknown",
             d + dt.timedelta(days=1), d, True, None),
            ("s4", "4", None, None, ["pubmed"], "Globus pallidus", "unknown", d, d, False, None),
            ("s5", None, "10.1/n", None, ["biorxiv"], "Globus pallidus, noise", "unknown", d, d,
             True, "noise"),
        ])  # fmt: skip
        con.executemany("insert into int_pubmed__records values (?, ?, ?)", [
            ("1", ["D1"], []),  # MeSH says striatum: MeSH wins over the title
            ("2", [], ["brainstem"]),  # no MeSH yet: the author keywords count
        ])  # fmt: skip
    return path


def test_pair_studies_by_mesh_or_text_newest_first_neuro_only_no_noise(tmp_path):
    asked = []

    def abstract(study, cache_root=None):
        asked.append(study["pmid"] or study["doi"])
        return None

    found = studies.pair_studies(warehouse(tmp_path / "w.duckdb"),
                                 ("study_id", "title", "species", "pmid", "doi", "sources"),
                                 abstract=abstract, match=studies.Matcher(ROWS, TERMS))  # fmt: skip
    assert {k: [(s["study_id"], s["basis"]) for s in v] for k, v in found.items()} == {
        "striatum": [("s1", "mesh")],
        "brainstem": [("s2", "text")],
        "pallidum": [("s3", "text")],
    }
    assert sorted(asked) == ["10.1/x", "2"]  # the abstract only for studies without MeSH


def test_species_groups_in_order_with_a_cap():
    rows = [{"species": "unknown"}] * 3 + [{"species": "humans"}] + [{"species": None}]
    groups = studies.by_species(rows, cap=2)
    assert [(g["species"], len(g["studies"]), g["more"], g["total"]) for g in groups] == [
        ("humans", 1, 0, 1),
        ("unknown", 2, 2, 4),
    ]


def test_her_words_match_the_text_and_count_in_what_she_approves(monkeypatch, tmp_path) -> None:
    """A2.1: her synonyms (``text`` in region_terms.toml) find studies by their text, and
    copying them in changes the item's hash, so an approval of the old row stops counting:
    the item goes back to her queue and the pair is a proposal again."""
    from synaptica.review.models import Action, Decision

    m = studies.Matcher(studies.vocabulary(), studies.region_terms(), {"internal": ["CA3"]})
    assert m.text("Recurrent CA3 networks") == {"internal"}  # short, but hers: kept
    before = {i.item_id: i for i in studies.review_items()}["waxholm-1021"]
    review = tmp_path / "review"
    review.mkdir()
    d = Decision(item_type=before.item_type, item_id=before.item_id,
                 content_sha256=before.content_sha256, action=Action.APPROVE, payload={},
                 reviewed_by="sofia", reviewed_at=dt.datetime(2026, 11, 18, 9, tzinfo=dt.UTC),
                 source="issue#1")  # fmt: skip
    (review / "decisions.jsonl").write_text(d.model_dump_json() + "\n")
    assert studies.reviewed(review) == {"internal": "2026-11-18"}
    monkeypatch.setattr(studies, "region_text", lambda: {"internal": ["CA3"]})
    after = {i.item_id: i for i in studies.review_items()}["waxholm-1021"]
    assert after.content.terms[-1] == "CA3" and after.content_sha256 != before.content_sha256
    assert studies.reviewed(review) == {}
