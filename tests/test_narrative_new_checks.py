"""New checks (step 17): overclaims, alarm, causal and predictive phrases, the caution
of the facts (English and Spanish), and Spanish spelling. The cases come from Sofía's
blind review of the S5 summaries (ADR D4), rewritten here in short synthetic form."""

import pytest

from synaptica.narrative.checks import (
    check_claims_es,
    check_spelling_es,
    check_text,
    claim_problems,
    unknown_words_es,
)

ASSOCIATED = "Higher air pollution was associated with more anxiety symptoms in the cohort."
NO_EXCESS = "Exposure during pregnancy was not associated with more birth defects in the cohort."
TRIAL = "In the trial, the drug caused a drop in seizures compared with placebo."
MAY = "The authors say spindles may help store memories in mice."


@pytest.mark.parametrize(
    ("sentence", "facts", "problem"),
    [
        ("The drug is safe during pregnancy.", [NO_EXCESS], "says 'safe'"),
        ("Air pollution contributes to anxiety.", [ASSOCIATED], "says 'causal'"),
        ("The gel resulted in less tissue damage.", [ASSOCIATED], "says 'causal'"),  # step 18
        ("Protein levels triggered gene changes.", [ASSOCIATED], "says 'causal'"),
        ("Pollution levels could predict anxiety.", [ASSOCIATED], "says 'predicts'"),
        ("The marker is specific to brain injury.", [TRIAL], "says 'specific'"),
        ("It works where standard tests fail.", [TRIAL], "says 'fail'"),
        ("This devastating disease affects millions.", [TRIAL], "says 'alarm'"),
        ("The findings prove that spindles store memories.", [MAY], "says 'proves'"),
        ("Spindles help mice store memories.", [MAY], "drops the caution"),
        ("Spindles could be measured in mice.", [MAY], "drops the caution"),  # ability
    ],
)
def test_claims_the_facts_do_not_make_fail(sentence, facts, problem):
    assert any(p.startswith(problem) for p in claim_problems(sentence, facts))


@pytest.mark.parametrize(
    ("sentence", "facts"),
    [
        ("More air pollution went with more anxiety symptoms in this group.", [ASSOCIATED]),
        ("Birth defects were not more common after exposure in pregnancy.", [NO_EXCESS]),
        ("In the trial, the drug caused fewer seizures than placebo.", [TRIAL]),  # authors' word
        ("Spindles may help mice store memories.", [MAY]),
        ("The team counted seizures over a year.", [TRIAL, MAY]),  # not every fact hedged
        # Step 18: "could be" + a noun is a caution, as "may" in the abstract.
        ("Red imaging could be a helpful tool for this surgery.", [MAY]),
    ],
)
def test_claims_the_facts_make_pass(sentence, facts):
    assert claim_problems(sentence, facts) == []


def test_claims_are_part_of_the_english_text_checks():
    facts = {"f1": ASSOCIATED}
    report = check_text([("Air pollution causes anxiety symptoms in the cohort.", ["f1"])],
                        facts, [])  # fmt: skip
    assert "says 'causal' but no cited fact does" in report.sentences[0].problems


def test_spanish_adds_no_claim_and_keeps_the_caution():
    en = ["Exposure in pregnancy was not associated with more birth defects.",
          "Spindles may help mice store memories.",
          "Pollution levels were associated with anxiety."]  # fmt: skip
    bad = ["El fármaco es seguro durante el embarazo.",
           "Los husos pueden ayudar a los ratones a guardar recuerdos.",
           "Los niveles de contaminación podían predecir la ansiedad."]  # fmt: skip
    problems = check_claims_es(en, bad)
    assert "sentence 1: 'safe' is not in the English sentence" in problems
    assert "sentence 2: the English sentence is cautious and this is not" in problems
    assert "sentence 3: 'predicts' is not in the English sentence" in problems
    good = ["La exposición en el embarazo no se asoció con más malformaciones.",
            "Los husos podrían ayudar a los ratones a guardar recuerdos.",
            "Los niveles de contaminación se asociaron con la ansiedad."]  # fmt: skip
    assert check_claims_es(en, good) == []


# --- Spanish spelling -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("es", "en", "unknown"),
    [  # the two typos of the S5 texts that no check caught
        (
            "Midieron las respuestas emocinales al miedo.",
            "They measured emotional responses.",
            ["emocinales"],
        ),
        ("Usaron microfibras biimpresas.", "They used bioprinted microfibres.", ["biimpresas"]),
        ("Emocinales y todo.", "Emotional.", ["Emocinales"]),  # first word checked too
    ],
)
def test_typos_are_caught(es, en, unknown):
    assert unknown_words_es(es, en) == unknown


@pytest.mark.parametrize(
    ("es", "en"),
    [
        ("Hallaron cambios en el ARN ribosómico.", "They found changes in ribosomal RNA."),
        ("Aplicaron estimulación transcraneal.", "They applied transcranial stimulation."),
        ("Los pacientes con ictus y los astrocitos reactivos.", "Stroke patients."),  # our list
        ("Las vías sensoriomotoras y los neuroprotectores.", "Pathways."),  # its inflections
        ("El gen UNC-51 actúa en Caenorhabditis elegans.", "The gene unc-51 acts in worms."),
        ("La proteína tau aumentó.", "The protein tau rose."),  # kept from English
        # Step 18 (v2 run): valid words the dictionary lacks, added to our list.
        ("Tras un traumatismo craneoencefálico.", "After a traumatic brain injury."),
        ("Los síntomas autoinformados.", "The symptoms they reported."),
        ("Siguen despejándolos del tejido.", "They keep clearing them."),  # pronouns
        ("En el ictus isquémico agudo.", "In acute stroke."),
    ],
)
def test_terms_names_and_english_twins_pass(es, en):
    assert unknown_words_es(es, en) == []


def test_spelling_is_part_of_the_spanish_checks():
    problems = check_spelling_es(["Emotional responses."], ["Respuestas emocinales."])
    assert problems == ["sentence 1: words not in the Spanish dictionary ['emocinales']"]


def test_spanish_causality_named_as_a_limit_is_not_a_causal_claim():
    # Step 18: «no establece causalidad» translates «does not establish causality».
    en = ["The study does not establish causality."]
    assert check_claims_es(en, ["El estudio no establece causalidad."]) == []
    assert check_claims_es(["Pollution was linked to anxiety."],
                           ["La contaminación causó ansiedad."]) == [
        "sentence 1: 'causal' is not in the English sentence"]  # fmt: skip


@pytest.mark.parametrize(
    ("en", "es"),
    [  # step 20: the caution kept in other words, or no caution to keep
        (
            "The authors suggest lipids drive it.",
            "Los autores proponen que los lípidos lo impulsan.",
        ),
        ("Doctors suggested thicker liquids.", "Los médicos sugerían líquidos más espesos."),
        ("It could improve walking.", "Investigó si podía mejorar la marcha."),
        ("Cells with unclear boundaries.", "Células con límites poco claros."),
        (
            "Women were more likely to develop it.",
            "Las mujeres tenían mayor riesgo de desarrollarla.",
        ),
    ],
)
def test_caution_in_other_words_and_compared_odds_pass(en, es):
    assert check_claims_es([en], [es]) == []


def test_a_promise_is_not_the_caution_of_potential():
    # Step 20: «potential insights» became «perspectivas prometedoras».
    assert check_claims_es(["The results offer potential insights."],
                           ["Los resultados ofrecen perspectivas prometedoras."]) == [
        "sentence 1: the English sentence is cautious and this is not"]  # fmt: skip


def test_more_likely_in_the_facts_is_no_caution_to_keep():
    facts = ["Women were more likely to develop multiple sclerosis."]
    assert claim_problems("Women had a higher risk of multiple sclerosis.", facts) == []


@pytest.mark.parametrize(
    "es",
    [  # step 20: valid terms the dictionary lacks, added to our list
        "Cruzan la barrera hematoencefálica.",
        "Medimos la microbiota y la noradrenalina.",
        "Tras la trombólisis y la radiocirugía estereotáctica.",
        "Tomografía por emisión de positrones.",
    ],
)
def test_step_20_terms_pass(es):
    assert unknown_words_es(es, "Unrelated words.") == []


@pytest.mark.parametrize("word", ["kilopascula", "carecientes", "aprendible"])
def test_doubtful_words_still_fail(word):
    # Left out of the list on purpose: a typo or a non-standard form (step 20).
    assert unknown_words_es(f"Una {word} cosa.", "A thing.") == [word]
