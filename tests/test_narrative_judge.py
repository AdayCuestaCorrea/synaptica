"""Judge of another family (step 19): it gates publication, its reason goes to the
review folder, spanish_natural does not block, and its verdict reaches the run report."""

import datetime as dt
import json

import pytest

from synaptica import report
from synaptica.narrative import fallback, judge, pipeline
from synaptica.narrative import write as write_mod
from test_narrative import STUDY, FakeLLM, cache_abstract

NOW = dt.datetime(2026, 11, 9, 12, tzinfo=dt.UTC)


class FakeJudge:
    def __init__(self, passed=True, label="groq/openai/gpt-oss-120b", natural=2):
        self.passed, self.label, self.natural = passed, label, natural
        self.users = []

    def complete_json(self, system, user, output, max_tokens):
        self.users.append(user)
        return output.model_validate({
            "faithful": True, "no_overclaim": self.passed, "no_medical_advice": True,
            "spanish_matches": True, "passed": self.passed,
            "reason": "" if self.passed else 'Says "may help" as a fact. More text.',
            "spanish_natural": self.natural,
        })  # fmt: skip


@pytest.fixture
def written(tmp_path):
    derived, cache = tmp_path / "data" / "derived", tmp_path / "data" / "cache"
    cache_abstract(cache)
    kw = {"derived_root": derived, "cache_root": cache, "now": NOW}
    llm = FakeLLM()
    llm.label = "groq/qwen/qwen3.8-27b"
    pipeline.run_facts(llm, [STUDY], **kw)
    pipeline.run_write(llm, [STUDY], **kw)
    return kw


def test_a_passed_verdict_publishes_and_does_not_block_on_spanish(written):
    j = FakeJudge(natural=2)  # clumsy Spanish: noted, not a gate
    assert pipeline.run_judge(j, [STUDY], **written).counts == {"passed": 1}
    assert "ABSTRACT:\nBACKGROUND" in j.users[0] and "ES 3. " in j.users[0]
    shown = fallback.summary_for(STUDY, "es", derived_root=written["derived_root"])
    assert shown["kind"] == "verified" and shown["judge"] == "groq/openai/gpt-oss-120b"
    again = FakeJudge()
    assert pipeline.run_judge(again, [STUDY], **written).done == 0 and again.users == []


def test_a_rejected_summary_goes_to_review_with_the_reason_and_shows_the_fallback(written):
    assert pipeline.run_judge(FakeJudge(passed=False), [STUDY], **written).counts == {"rejected": 1}
    derived = written["derived_root"]
    for lang in ("en", "es"):
        assert not write_mod.text_path("10.1/spindles", lang, verified=True,
                                       derived_root=derived).exists()  # fmt: skip
        review = json.loads(write_mod.text_path("10.1/spindles", lang, verified=False,
                                                derived_root=derived).read_text())  # fmt: skip
        assert review["status"] == "rejected_by_judge"
        assert review["problems"] == ["judge: Says … as a fact"]  # no quote kept
        assert fallback.summary_for(STUDY, lang, derived_root=derived)["kind"] == "fallback"
    # Not written again for the same facts and prompts: the quota is not spent twice.
    assert pipeline.run_write(FakeLLM(), [STUDY], **written).up_to_date == 1


def test_the_judge_must_be_of_another_family(written):
    with pytest.raises(ValueError, match="writer's family"):
        pipeline.run_judge(FakeJudge(label="ollama/paleo-qwen3.5-9b"), [STUDY], **written)
    assert judge.family("groq/openai/gpt-oss-120b") == "gpt-oss"
    assert not judge.same_family("groq/openai/gpt-oss-120b", "groq/qwen/qwen3.8-27b")


def test_the_run_report_counts_texts_and_verdicts(written):
    pipeline.run_judge(FakeJudge(natural=3), [STUDY], **written)
    data = written["derived_root"].parent
    summary = report.texts_summary(data, NOW.date())
    assert summary == {"written": {"en_verified": 1, "es_verified": 1},
                       "judge": {"passed": 1, "rejected": 0,
                                 "spanish_natural_mean": 3.0}}  # fmt: skip
    md = report.markdown({"started_at": "x", "trigger": "local", "status": "ok",
                          "changed": True, "texts": summary})  # fmt: skip
    assert "**Summaries today:** en verified 1, es verified 1 · judge: 1 passed" in md
    assert report.texts_summary(data, dt.date(2026, 11, 10)) == {}
