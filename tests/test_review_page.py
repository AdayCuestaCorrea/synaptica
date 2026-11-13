"""The generated review page (spike S4, step 2) on the fixture queue, without network."""

import json
import re
from pathlib import Path

import pytest

from synaptica.review.models import ItemType, Queue, ReviewItem
from synaptica.review.page import ORDER, embed, page_data, page_items, render

FIXTURES = Path(__file__).parent / "fixtures" / "review"


@pytest.fixture
def queue() -> Queue:
    return Queue.model_validate_json((FIXTURES / "queue.json").read_text("utf-8"))


def _embedded(html: str) -> dict:
    m = re.search(r"const PAGE = (\{.*?\});\n", html)
    assert m, "no data in the page"
    return json.loads(m.group(1))


def test_order_lists_every_item_type():
    assert sorted(ORDER) == sorted(ItemType)


def test_public_page_never_has_disease_drafts(queue):
    html = render(queue, "public")
    types = {i["item_type"] for i in _embedded(html)["items"]}
    assert "disease" not in types
    assert types == {i.item_type.value for i in queue.items} - {"disease"}
    assert "Texto de prueba del spike S4" not in html


def test_private_page_has_only_the_private_items(queue):
    data = _embedded(render(queue, "private"))
    assert [i["item_id"] for i in data["items"]] == ["test-placeholder"]
    assert data["items"][0]["blocking"] is True
    assert data["propose"] is False


def test_every_item_is_in_exactly_one_variant(queue):
    ids = [i.key for v in ("public", "private") for i in page_items(queue, v)]
    assert sorted(ids) == sorted(i.key for i in queue.items)


def test_items_follow_the_priority_order(queue):
    types = [i.item_type for i in page_items(queue, "public")]
    assert types == sorted(types, key=ORDER.index)
    assert types[0] is ItemType.CLASSICS and types[-1] is ItemType.NEWS


def test_embedded_items_round_trip_with_their_hash(queue):
    for item in _embedded(render(queue, "public"))["items"]:
        sha = item.pop("content_sha256")
        item.pop("blocking")
        assert ReviewItem.model_validate(item).content_sha256 == sha


def test_embedded_json_cannot_close_the_script(queue):
    raw = queue.model_dump(mode="json")
    raw["items"][1]["title_es"] = "</script><script>alert(1)</script><!--"
    html = render(Queue.model_validate(raw), "public")
    assert html.count("</script>") == 1
    assert "<!--" not in html.split("<script>", 1)[1]
    assert "</script><script>alert(1)" in json.dumps(_embedded(html), ensure_ascii=False)


def test_embed_escapes_markup():
    assert embed({"t": "<a & b>"}) == '{"t": "\\u003ca \\u0026 b\\u003e"}'


def test_page_requests_nothing_from_other_domains(queue):
    """No fonts, scripts or styles from elsewhere: only the links to sources Sofía opens."""
    html = render(queue, "public")
    assert not re.search(r"<(link|script|img|iframe)\b[^>]*\b(href|src)=", html)
    assert "@import" not in html and "url(" not in html


def test_page_shows_the_public_note_warning_and_no_abstract(queue):
    html = render(queue, "public")
    assert "se verán en público" in html
    assert "abstract" not in html.lower()


def test_unknown_variant(queue):
    with pytest.raises(ValueError, match="unknown variant"):
        page_data(queue, "everything")


def test_warnings_do_not_change_the_hash(queue):
    item = queue.get(ItemType.NEWS, "pubmed-42971231")
    warned = ReviewItem.model_validate(
        item.model_dump() | {"warnings": ["Una frase copia 9 palabras."]}
    )
    assert warned.content_sha256 == item.content_sha256


def test_the_public_page_lists_the_glossary_terms(queue):
    """Round 1: she proposed EEG, AAV, GFAP and LTP, already in the glossary."""
    from synaptica.review.page import page_data

    terms = page_data(queue, "public")["glossary_terms"]
    assert {"EEG", "AAV", "GFAP", "LTP", "GABA", "SNr"} <= set(terms)
    assert page_data(queue, "private")["glossary_terms"] == []


def test_text_cards_can_propose_one_sentence(queue):
    # Step R: in S4 she wrote her alternative in the note, which changes nothing.
    page = render(queue, "public")
    assert "Proponer otra frase" in page and "La nota no cambia el texto." in page
    assert 'action: "edit", payload: { es: es.join("\\n") }' in page
