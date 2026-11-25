"""Neuro Atlas's introduction (src/synaptica/atlas/intro.py, v221): three Wikipedia
sections pinned to a revision, the shared chain on each with its own fact ids, one
paragraph whose sentences cite the sections they use, her queue and the atlas page. No
network, no LLM: a mock Wikipedia and a fake model answering by output schema."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from synaptica.atlas import intro
from synaptica.http import Throttle, make_client
from synaptica.review.models import ItemType

NO_WAIT = Throttle(1000, sleep=lambda _: None)
TEXTS = {
    "gyrification": "Rodents have the lowest gyrification index of the mammals studied, "
    "and their cortex is lissencephalic, that is smooth. Primates have gyrencephalic brains.",
    "human-brain": "Compared with the rat, the human cerebral cortex devotes a far larger "
    "share to association cortex. Strokes affect it differently.",
    "brain-size": "Rodents form the largest order of mammals, and their brains vary widely "
    "in size across species.",
}
FACTS = {
    "Variation across species": [
        ("The cortex of rodents is smooth, with almost no folds.",
         "their cortex is lissencephalic, that is smooth", "comparison"),
        ("Primate brains are folded.", "Primates have gyrencephalic brains", "comparison"),
    ],
    "Comparative anatomy": [
        ("People have much more association cortex than rats do.",
         "devotes a far larger share to association cortex", "comparison"),
        ("Strokes act on it in another way.", "Strokes affect it differently", "clinical"),
    ],
    "Other animals": [
        ("Brain size differs a lot among rodent species.",
         "their brains vary widely in size across species", "general"),
    ],
}  # fmt: skip
EN = [
    (
        "Both brains share a plan, yet the rat's cortex is smooth, with almost no folds, "
        "while primate brains are folded.",
        ["a1", "a2"],
    ),
    (
        "Humans also have much more association cortex than rats, the cortex that links "
        "the senses with thought.",
        ["b1"],
    ),
    ("Even among rodents, brain size differs a lot from one species to another.", ["c1"]),
]
ES = ["Los dos cerebros comparten un plan, pero la corteza de la rata es lisa, casi sin "
      "pliegues, mientras que la de los primates está plegada.",
      "Los humanos tienen además mucha más corteza de asociación que las ratas, la corteza "
      "que une los sentidos con el pensamiento.",
      "Incluso entre los roedores, el tamaño del cerebro cambia mucho de una especie a "
      "otra."]  # fmt: skip


class FakeLLM:
    label = "fake/model"

    def __init__(self):
        self.calls: list[str] = []
        self.users: list[str] = []

    def complete_json(self, system, user, output, max_tokens):
        self.calls.append(output.__name__)
        self.users.append(user)
        if output.__name__ == "IntroFacts":
            heading = user.split("SECTION «")[1].split("»")[0]
            facts = FACTS[heading]
            data = {"facts": [{"statement": s, "quote": q, "kind": k} for s, q, k in facts]}
        elif output.__name__ == "Summary":
            data = {"sentences": [{"text": t, "fact_ids": f} for t, f in EN]}
        else:
            data = {"sentences": [{"index": i, "text": t} for i, t in enumerate(ES, 1)]}
        return output.model_validate(data)


def html(text: str) -> str:
    return f"<p>{text}</p>"


def wiki(missing: str | None = None):
    asked: list[dict[str, str]] = []
    by_rev = {p.revid: p for p in intro.PINNED}

    def handler(request: httpx.Request) -> httpx.Response:
        q = dict(request.url.params)
        asked.append(q)
        p = by_rev[int(q["oldid"])]
        if q["prop"] == "sections":
            line = "Something else" if p.id == missing else p.heading
            return httpx.Response(200, json={"parse": {"sections": [{"index": "3", "line": line}]}})
        return httpx.Response(200, json={"parse": {"text": html(TEXTS[p.id])}})

    return handler, asked


def stored(tmp_path: Path) -> Path:
    path = tmp_path / "intro_sources.json"
    handler, _ = wiki()
    with make_client(httpx.MockTransport(handler)) as c:
        assert intro.update(c, path=path, throttle=NO_WAIT) == (3, [])
    return path


def drafted(tmp_path: Path) -> tuple[Path, Path]:
    src, out = stored(tmp_path), tmp_path / "intro.json"
    assert intro.write(FakeLLM(), sources_path=src, path=out) == "drafted"
    return out, src


def test_sections_stored_at_their_revision_and_not_asked_again(tmp_path: Path) -> None:
    path = stored(tmp_path)
    secs = json.loads(path.read_text())["sections"]
    assert [secs[p.id]["revid"] for p in intro.PINNED] == [p.revid for p in intro.PINNED]
    assert secs["gyrification"]["text"] == TEXTS["gyrification"]
    handler, asked = wiki()
    with make_client(httpx.MockTransport(handler)) as c:
        assert intro.update(c, path=path, throttle=NO_WAIT) == (0, [])
    assert asked == []


def test_a_missing_section_fails_and_nothing_is_drafted(tmp_path: Path) -> None:
    path = tmp_path / "intro_sources.json"
    handler, _ = wiki(missing="brain-size")
    with make_client(httpx.MockTransport(handler)) as c:
        fetched, failed = intro.update(c, path=path, throttle=NO_WAIT)
    assert fetched == 2 and failed == ["brain-size: no section «Other animals» in revision "
                                       "1385820400"]  # fmt: skip
    llm = FakeLLM()
    assert intro.write(llm, sources_path=path, path=tmp_path / "i.json") == "missing_sources"
    assert llm.calls == []


def test_facts_per_section_never_clinical_and_a_rerun_asks_nothing(tmp_path: Path) -> None:
    src, out = stored(tmp_path), tmp_path / "intro.json"
    llm = FakeLLM()
    assert intro.write(llm, sources_path=src, path=out) == "drafted"
    assert llm.calls[:4] == ["IntroFacts", "IntroFacts", "IntroFacts", "Summary"]
    assert "SECTION «Comparative anatomy» OF THE ARTICLE «Human brain»" in llm.users[1]
    rec = json.loads(out.read_text())["intro"]
    assert [(f["id"], f["source"]) for f in rec["facts"]] == [
        ("a1", "gyrification"), ("a2", "gyrification"), ("b1", "human-brain"),
        ("b2", "human-brain"), ("c1", "brain-size")]  # fmt: skip
    assert "Strokes" not in llm.users[3] and "b1 People have" in llm.users[3]
    again = FakeLLM()
    assert intro.write(again, sources_path=src, path=out) == "unchanged" and again.calls == []


def test_her_card_cites_the_sections_each_sentence_uses(tmp_path: Path) -> None:
    out, src = drafted(tmp_path)
    (item,) = intro.review_items(out, src)
    assert (item.item_type, item.item_id, item.title_es) == (
        ItemType.ATLAS,
        "intro",
        "Humano y rata · Cómo leer las parejas",
    )
    cites = [s.cites for s in item.content.es]
    assert cites == [["wikipedia-en-atlas-intro-gyrification"],
                     ["wikipedia-en-atlas-intro-human-brain"],
                     ["wikipedia-en-atlas-intro-brain-size"]]  # fmt: skip
    label = item.content.sources[1].label
    assert label == ("Wikipedia en inglés: «Human brain», sección «Comparative anatomy» "
                     "(revisión 1386315509)")  # fmt: skip
    assert intro.source_texts([item], src)["wikipedia-en-atlas-intro-brain-size"] == TEXTS[
        "brain-size"]  # fmt: skip


def test_the_atlas_page_shows_only_her_approved_intro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from synaptica.site.build import SiteBuilder
    from synaptica.site.check import check_site

    out, src = drafted(tmp_path)
    monkeypatch.setattr(intro, "TEXTS", out)
    monkeypatch.setattr(intro, "SOURCES", src)
    data, licensed = tmp_path / "data", {"hero": {"files": [], "author": "Sofía",
                                                  "licence": "CC BY-SA 4.0"}}  # fmt: skip
    site = tmp_path / "site"
    SiteBuilder(site, images=licensed, data_dir=data).build()
    page = (site / "es" / "atlas.html").read_text()
    assert "data-atlas-intro" not in page and 'id="gap-atlas_intro"' in page
    (item,) = intro.review_items()
    (data / "review").mkdir(parents=True)
    (data / "review" / "decisions.jsonl").write_text(json.dumps({
        "item_type": "atlas", "item_id": "intro", "content_sha256": item.content_sha256,
        "action": "approve", "payload": {}, "note": None, "reviewed_by": "sofia",
        "reviewed_at": "2026-11-25T10:00:00Z", "source": "issue#41"}) + "\n")  # fmt: skip
    SiteBuilder(site, images=licensed, data_dir=data).build()
    assert check_site(site).passed
    page = (site / "es" / "atlas.html").read_text()
    assert ES[0] in page and "gap-atlas_intro" not in page
    assert "«Brain size», «Other animals»" in page and "CC BY-SA 4.0" in page
    assert "Both brains share a plan" in (site / "en" / "atlas.html").read_text()


# ---- «more differences» (v248): its own sections, fact ids, card and fold ---------------

MORE_TEXTS = {
    "neurogenesis": "Rodents have a very similar architecture to humans, with very little "
    "regenerative capacity.",
    "animal-model": "Rats and mice may be selectively sedentary, which may confound their use "
    "to model human metabolism.",
    "neocortex": "In humans, 90% of the cerebral cortex is neocortex.",
    "whiskers": "A large part of the brain of whisker-specialist mammals processes signals "
    "from the vibrissae.",
}
MORE_FACTS = {
    "Rodents": [("The rodent nervous system is built much like the human one.",
                 "Rodents have a very similar architecture to humans", "comparison")],
    "Challenges and criticisms": [("Laboratory rats and mice may move little, which may "
                                   "blur what they say about human metabolism.",
                                   "Rats and mice may be selectively sedentary",
                                   "comparison")],
    "Evolution": [("Nine tenths of the human cerebral cortex is neocortex, 90%.",
                   "In humans, 90% of the cerebral cortex is neocortex", "comparison")],
    "Neuroscience": [("Mammals that rely on whiskers devote a large share of the brain to "
                      "them.", "A large part of the brain of whisker-specialist mammals",
                      "comparison")],
}  # fmt: skip
MORE_EN = [
    ("The rodent nervous system is organised much like ours, which is why rats are used to "
     "study it.", ["d1"]),
    ("Yet laboratory rats and mice may move little, and that may blur what they tell us "
     "about human metabolism.", ["e1"]),
    ("In people, 90% of the cerebral cortex is neocortex, the most recent part to evolve.",
     ["f1"]),
    ("Rats, in turn, read the world with their whiskers, and a large share of their brain "
     "handles them.", ["g1"]),
]  # fmt: skip
MORE_ES = [
    "El sistema nervioso de los roedores está organizado de forma muy parecida al nuestro, "
    "por eso se usan ratas para estudiarlo.",
    "Pero las ratas y los ratones de laboratorio podrían moverse poco, y eso podría "
    "enturbiar lo que nos dicen del metabolismo humano.",
    "En las personas, el 90% de la corteza cerebral es neocorteza, la parte más reciente.",
    "Las ratas, a su vez, perciben el mundo con sus bigotes, y una gran parte de su cerebro "
    "se ocupa de ellos.",
]


class MoreLLM(FakeLLM):
    def complete_json(self, system, user, output, max_tokens):
        if output.__name__ == "IntroFacts":
            self.calls.append(output.__name__)
            heading = user.split("SECTION «")[1].split("»")[0]
            data = {"facts": [{"statement": s, "quote": q, "kind": k}
                              for s, q, k in MORE_FACTS[heading]]}  # fmt: skip
        elif output.__name__ == "Summary":
            self.calls.append(output.__name__)
            data = {"sentences": [{"text": t, "fact_ids": f} for t, f in MORE_EN]}
        else:
            self.calls.append(output.__name__)
            data = {"sentences": [{"index": i, "text": t} for i, t in enumerate(MORE_ES, 1)]}
        return output.model_validate(data)


def stored_more(tmp_path: Path) -> Path:
    """Both parts' sections in one file, as `syn atlas intro-sources` leaves it."""
    path = stored(tmp_path)
    by_rev = {p.revid: p for p in intro.PINNED_MORE}

    def handler(request: httpx.Request) -> httpx.Response:
        q = dict(request.url.params)
        p = by_rev[int(q["oldid"])]
        if q["prop"] == "sections":
            return httpx.Response(200, json={"parse": {"sections": [
                {"index": "2", "line": p.heading}]}})  # fmt: skip
        return httpx.Response(200, json={"parse": {"text": html(MORE_TEXTS[p.id])}})

    with make_client(httpx.MockTransport(handler)) as c:
        assert intro.update(c, path=path, throttle=NO_WAIT, part=intro.MORE) == (4, [])
    return path


def test_more_differences_is_its_own_card_and_leaves_the_intro_as_it_was(
    tmp_path: Path,
) -> None:
    src = stored_more(tmp_path)
    secs = json.loads(src.read_text())["sections"]
    assert set(secs) == {p.id for q in intro.PARTS for p in q.pinned}  # the intro's kept
    out = tmp_path / "intro.json"
    assert intro.write(FakeLLM(), sources_path=src, path=out) == "drafted"
    before = json.loads(out.read_text())["intro"]
    (card,) = intro.review_items(out, src)
    assert intro.write(MoreLLM(), sources_path=src, path=out, part=intro.MORE) == "drafted"
    body = json.loads(out.read_text())
    assert body["intro"] == before and body["more"]["more"]["status"] == "drafted"
    assert [f["id"] for f in body["more"]["facts"]] == ["d1", "e1", "f1", "g1"]
    first, more = intro.review_items(out, src)
    assert first.content_sha256 == card.content_sha256  # her intro card: the same hash
    assert more.item_id == "intro-more" and more.title_es.endswith("Más diferencias")
    assert [s.id for s in more.content.sources] == [
        f"wikipedia-en-atlas-intro-{k}" for k in MORE_TEXTS
    ]
    texts = intro.source_texts([more], src)
    assert texts["wikipedia-en-atlas-intro-whiskers"] == MORE_TEXTS["whiskers"]
    again = MoreLLM()
    assert intro.write(again, sources_path=src, path=out, part=intro.MORE) == "unchanged"
    assert again.calls == []


def test_more_differences_shows_only_once_she_approved_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from synaptica.site.build import SiteBuilder

    src = stored_more(tmp_path)
    out = tmp_path / "intro.json"
    intro.write(MoreLLM(), sources_path=src, path=out, part=intro.MORE)
    monkeypatch.setattr(intro, "TEXTS", out)
    monkeypatch.setattr(intro, "SOURCES", src)
    data, licensed = tmp_path / "data", {"hero": {"files": [], "author": "Sofía",
                                                  "licence": "CC BY-SA 4.0"}}  # fmt: skip
    site = tmp_path / "site"
    SiteBuilder(site, images=licensed, data_dir=data).build()
    assert "atlas-diff" not in (site / "es" / "atlas.html").read_text()  # no empty fold
    (more,) = intro.review_items()
    (data / "review").mkdir(parents=True)
    (data / "review" / "decisions.jsonl").write_text(json.dumps({
        "item_type": "atlas", "item_id": "intro-more", "content_sha256": more.content_sha256,
        "action": "approve", "payload": {}, "note": None, "reviewed_by": "sofia",
        "reviewed_at": "2026-11-26T10:00:00Z", "source": "issue#42"}) + "\n")  # fmt: skip
    SiteBuilder(site, images=licensed, data_dir=data).build()
    page = (site / "es" / "atlas.html").read_text()
    assert "Más diferencias entre los dos cerebros" in page and MORE_ES[3] in page
    assert page.index("atlas-diff") > page.index('class="brains"')  # below the brains
