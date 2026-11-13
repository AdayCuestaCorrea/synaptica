"""Spanish titles (step 23c): what is translated, batches, cache by title and prompt, and
the mechanical checks, each with a title that passes and one that fails. No network: the
LLM is a fake that answers from a dictionary. The titles are made up for the tests."""

import datetime as dt
import json

import pytest

from synaptica.news import titles

NOW = dt.datetime(2026, 11, 9, 12, tzinfo=dt.UTC)


class FakeLLM:
    """Answers each English title with ``answers[title]``; leaves out the missing ones."""

    label = "fake/model"

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def complete_json(self, system, user, output, max_tokens):
        self.calls.append(user)
        items = []
        for line in user.splitlines()[1:]:
            index, title = line.split(". ", 1)
            if title in self.answers:
                items.append({"index": int(index), "title_es": self.answers[title]})
        return output.model_validate({"items": items})


def items(*pairs):
    return {sid: {"title": title, "entered_on": f"2026-11-0{n}"}
            for n, (sid, title) in enumerate(pairs, start=1)}  # fmt: skip


def rows(root):
    return json.loads(titles.titles_path(root).read_text("utf-8"))


# -- the checks, one pair each (passes, fails) ---------------------------------------

PASSES = [
    ("APOE4 carriers show 2.5-fold higher amyloid in mice",
     "Los portadores de APOE4 muestran 2,5 veces más amiloide en ratones"),
    ("fMRI reveals DNA damage in Parkinson's disease",
     "La RMf revela daño en el ADN en la enfermedad de párkinson"),
    ("Semaglutide reduces alcohol intake in a trial of 48 adults",
     "La semaglutida reduce el consumo de alcohol en un ensayo con 48 adultos"),
    ("Dopaminergic Neurons Encode Reward Prediction Errors",  # Title Case: no name rule
     "Las neuronas dopaminérgicas codifican errores de predicción de la recompensa"),
    ("Neural circuits of courtship in C. elegans and Drosophila",
     "Circuitos neuronales del cortejo en C. elegans y Drosophila"),
    ("Sleep loss may impair memory in three groups of rats",
     "La falta de sueño podría perjudicar la memoria en tres grupos de ratas"),
    ("Receptors for mGluR5 and GLP-1 in the human CA1",
     "Receptores de mGluR5 y GLP-1 en la CA1 humana"),
    # Title Case compounds are not acronyms; the acronym inside one still counts.
    ("Nicotine and Cannabis Co-Use in Social Media-Like Settings via the VDR-clock axis",
     "El consumo conjunto de nicotina y cannabis en entornos similares a redes sociales "
     "a través del eje VDR-reloj"),
]  # fmt: skip

FAILS = [
    ("APOE4 carriers show 2.5-fold higher amyloid",
     "Los portadores muestran 2,5 veces más amiloide", "'APOE4' is missing"),
    ("TREM2 shapes microglia", "TREM2 y BDNF modelan la microglía", "'BDNF' is not in the English"),
    ("The VDR-clock axis in the liver", "El eje del reloj en el hígado", "'VDR' is missing"),
    ("Amyloid rises by 30% in plasma", "El amiloide sube un 40 % en plasma", "numbers differ"),
    ("Hippocampal maps in young Wistar rats", "Mapas hipocampales en ratas jóvenes",
     "name 'Wistar' is missing"),
    ("Lecanemab slows decline in a cohort", "Un anticuerpo frena el deterioro en una cohorte",
     "drug 'lecanemab' is missing"),
    ("Odour learning in D. melanogaster larvae", "Aprendizaje olfativo en larvas de mosca",
     "species 'D. melanogaster' is missing"),
    ("Grid cells remap in mice", "Las células de rejilla se reorganizan en personas",
     "organism 'mouse' is missing"),
    ("Grid cells remap in mice", "Las células de rejilla se reorganizan en ratones y humanos",
     "organism 'human' is not in the English"),
    ("Poor sleep is associated with memory decline",
     "El mal sueño causa deterioro de la memoria", "says 'causal'"),
    ("Microglia in the ageing cortex",
     "Microglía en la corteza que envejece: un hallazgo alarmante", "says 'alarm'"),
    ("Exercise may protect dopaminergic neurons",
     "El ejercicio protege las neuronas dopaminérgicas", "is cautious and this is not"),
    ("Astrocytes and synapses in the adult human cortex", "Astrocitos",
     "length"),
]  # fmt: skip


@pytest.mark.parametrize(("en", "es"), PASSES)
def test_faithful_titles_pass(en, es):
    assert titles.check_title(en, es) == []


@pytest.mark.parametrize(("en", "es", "problem"), FAILS)
def test_each_check_catches_its_problem(en, es, problem):
    assert any(problem in p for p in titles.check_title(en, es)), titles.check_title(en, es)


def test_empty_title_fails():
    assert titles.check_title("Sleep", "  ") == ["empty"]


def test_final_full_stop_is_dropped_not_failed():
    assert titles.clean(" El sueño  y la memoria. ") == "El sueño y la memoria"
    assert titles.clean("¿Y ahora qué...") == "¿Y ahora qué..."


# -- translation: batches, cache, failures -------------------------------------------

GOOD = ("doi:10.1/good", "Sleep loss may impair memory in three groups of rats")
BAD = ("doi:10.1/bad", "Exercise may protect dopaminergic neurons")
ANSWERS = {GOOD[1]: "La falta de sueño podría perjudicar la memoria en tres grupos de ratas.",
           BAD[1]: "El ejercicio protege las neuronas dopaminérgicas"}  # fmt: skip


def test_a_title_that_fails_is_kept_with_its_problems_and_not_shown(tmp_path):
    result = titles.translate(FakeLLM(ANSWERS), items(GOOD, BAD), derived_root=tmp_path, now=NOW)
    assert (result.translated, result.failed, result.total) == (1, 1, 2)
    by_id = {r["study_id"]: r for r in rows(tmp_path)}
    assert by_id[GOOD[0]]["status"] == "ok" and by_id[GOOD[0]]["problems"] == []
    assert by_id[GOOD[0]]["title_es"].endswith("ratas")  # the stop is dropped
    assert by_id[BAD[0]]["status"] == "failed" and by_id[BAD[0]]["problems"]
    assert by_id[BAD[0]]["prompt_version"] == "titles-v1"
    assert by_id[BAD[0]]["generator"] == "fake/model"


def test_second_run_asks_nothing_and_a_new_prompt_asks_again(tmp_path, monkeypatch):
    fake = FakeLLM(ANSWERS)
    titles.translate(fake, items(GOOD, BAD), derived_root=tmp_path, now=NOW)
    before = titles.titles_path(tmp_path).read_text("utf-8")
    again = titles.translate(fake, items(GOOD, BAD), derived_root=tmp_path, now=NOW)
    assert again.up_to_date == 2 and len(fake.calls) == 1  # failed ones are not retried
    assert titles.titles_path(tmp_path).read_text("utf-8") == before
    real = titles.prompt
    monkeypatch.setattr(titles, "prompt", lambda n: (real(n)[0], "titles-v2"))
    assert titles.translate(fake, items(GOOD), derived_root=tmp_path, now=NOW).translated == 1


def test_a_changed_english_title_is_asked_again(tmp_path):
    fake = FakeLLM({**ANSWERS, "Sleep and memory": "Sueño y memoria"})
    titles.translate(fake, items(GOOD), derived_root=tmp_path, now=NOW)
    result = titles.translate(fake, items((GOOD[0], "Sleep and memory")), derived_root=tmp_path)
    assert result.translated == 1 and rows(tmp_path)[0]["title_es"] == "Sueño y memoria"


def test_batches_missing_answers_and_limit_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(titles, "BATCH", 2)
    many = items(*[(f"doi:10.1/{n}", f"Title {n}") for n in range(5)])
    fake = FakeLLM({f"Title {n}": f"Título {n}" for n in range(5) if n != 4})
    result = titles.translate(fake, many, derived_root=tmp_path, now=NOW)
    assert len(fake.calls) == 3 and result.missing == 1 and result.translated == 4
    assert "doi:10.1/4" not in {r["study_id"] for r in rows(tmp_path)}  # asked again next run
    other = tmp_path / "other"
    titles.translate(FakeLLM({"Title 4": "Título 4"}), many, derived_root=other, limit=1)
    assert [r["study_id"] for r in rows(other)] == ["doi:10.1/4"]  # the newest


def test_an_empty_file_is_written_when_nothing_is_shown(tmp_path):
    titles.translate(FakeLLM({}), {}, derived_root=tmp_path)
    assert rows(tmp_path) == []


def test_the_site_selection_is_translated(tmp_path):
    from test_site_news import study as site_study
    from test_site_news import warehouse

    rows_in = [site_study("doi:10.1/a"), site_study("doi:10.1/nsc", sources=["journals"]),
               site_study("doi:10.1/noise", news_type="noise"),
               site_study("doi:10.1/old", entered_on=dt.date(2026, 10, 1))]  # fmt: skip
    path = warehouse(tmp_path, studies=rows_in) / "warehouse.duckdb"
    assert sorted(titles.titles_to_translate(path)) == ["doi:10.1/a", "doi:10.1/nsc"]


def test_cli_without_provider_or_warehouse(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from synaptica.cli import app

    monkeypatch.setenv("SYN_DATA_DIR", str(tmp_path))
    out = CliRunner().invoke(app, ["titles"])
    assert out.exit_code == 0 and "nothing translated" in out.output


def test_calls_and_tokens_are_recorded_per_day(tmp_path):
    from synaptica.llm import CallStats

    class Counting(FakeLLM):
        def __init__(self, answers):
            super().__init__(answers)
            self.stats = CallStats()

        def complete_json(self, system, user, output, max_tokens):
            self.stats.calls += 1
            self.stats.prompt_tokens += 500
            self.stats.completion_tokens += 120
            return super().complete_json(system, user, output, max_tokens)

    titles.translate(Counting(ANSWERS), items(GOOD, BAD), derived_root=tmp_path, now=NOW)
    usage = json.loads(titles.usage_path(tmp_path).read_text("utf-8"))
    assert usage == {"2026-11-09": {"calls": 1, "cached": 0, "prompt_tokens": 500,
                                    "completion_tokens": 120}}  # fmt: skip


def test_a_broken_answer_leaves_its_batch_for_the_next_run(tmp_path, monkeypatch):
    from synaptica.llm import LLMOutputError

    class Broken(FakeLLM):
        def complete_json(self, system, user, output, max_tokens):
            if "Exercise" in user:
                raise LLMOutputError("not JSON")
            return super().complete_json(system, user, output, max_tokens)

    monkeypatch.setattr(titles, "BATCH", 1)
    result = titles.translate(Broken(ANSWERS), items(GOOD, BAD), derived_root=tmp_path)
    assert (result.translated, result.missing) == (1, 1)
    assert [r["study_id"] for r in rows(tmp_path)] == [GOOD[0]]
