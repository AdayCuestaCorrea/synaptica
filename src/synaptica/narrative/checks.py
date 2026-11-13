"""Deterministic checks for extracted facts and written sentences (plan, step 16).

Copied from spike S5 ``spikes/s5/checks.py``, itself copied and adapted from paleo-atlas
``src/paleo/narrative/checks.py`` (same author, AGPL in both; decision D2). Only the
domain-free part is kept; the paleontology rules (abbreviated species, Spanish clade
names) are dropped and the name stop-list is adapted to study summaries.

No model judges another model here: every rule is plain string logic, so a failure can
be explained and reproduced. (The judge of step 19 is a separate, extra step.)

* **Fact check**: a fact's quote must appear verbatim in the abstract, every number in the
  fact must appear in that quote, and the fact must not copy the abstract's wording.
* **Citation**: every sentence cites at least one existing fact.
* **Faithfulness**: numbers in a sentence must come from the facts it cites; capitalized
  names must come from the facts.
* **Anti-copy**: no sentence shares a run of ``N_GRAM`` words with the source. Runs made
  mostly of names, numbers and function words count as facts, not prose: a run only
  counts as copied when it has at least ``MIN_ORDINARY_WORDS`` ordinary words.
* **Alignment** (EN -> ES): one Spanish sentence per English one, same numbers.
* **Spanish spelling** (step 17): every Spanish word is in the RLA-ES dictionary, in
  our list of terms, or the twin of a word of its English sentence.
* **Claims** (step 17): no overclaim, alarm, causal or predictive phrase that the cited
  facts do not make, and the caution of the facts kept, in English and in Spanish.
"""

from __future__ import annotations

import functools
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import resources

N_GRAM = 8  # CLAUDE.md: never 8 or more consecutive words copied
MIN_ORDINARY_WORDS = 4
MIN_QUOTE_CHARS = 12
MAX_WORDS = 180  # a news summary, not an encyclopedia page
MIN_WORDS = 30

_QUOTES = str.maketrans(
    {
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_WORD = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*|\d+(?:[.,]\d+)*", re.UNICODE)
_CAPITALIZED = re.compile(r"\b[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]{2,}(?:-[a-záéíóúñü]+)?\b")


def _wordset(*texts: str) -> frozenset[str]:
    return frozenset(w for t in texts for w in t.split())


# Capitalized words that are not claims (sentence openers and generic subjects).
_NOT_NAMES = _wordset(
    "the this these its it in on at as a an and but with from during after before unlike "
    "like both some most however although while because their they researchers scientists "
    "study studies participants patients people neuroscientists mice rats today until when "
    "where which who what overall together",
    "el la los las un una este esta estos estas su sus en con de del durante tras antes "
    "después aunque mientras como hoy según investigadores científicos estudio estudios "
    "participantes pacientes personas neurocientíficos ratones ratas en conjunto",
)

_FUNCTION_WORDS = _wordset(
    "a an the of in on at to from by for with and or as is was were be been its it that "
    "this which into are than",
    "el la los las un una de del en por para con y o que se su sus es fue era al lo son",
)


# The Lancet journals write decimals with a middle dot ("0\u00b711"); seen in S5.
_MIDDLE_DOT = re.compile(r"(?<=\d)\u00b7(?=\d)")


def _typography(text: str) -> str:
    """NFKC (thin and no-break spaces become spaces), plain quotes, decimal points."""
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    return _MIDDLE_DOT.sub(".", text)


def normalize(text: str) -> str:
    return " ".join(_typography(text).lower().split())


def numbers(text: str) -> set[str]:
    """Numbers in a language-neutral form: "1,5" and "1.5" -> "1.5"; "1,000" -> "1000"."""
    text = re.sub(r"(?<=\d) (?=\d{3}(?:\D|$))", "", _typography(text))
    out = set()
    for token in _NUMBER.findall(text):
        token = re.sub(r"[.,](?=\d{3}(?:\D|$))", "", token)
        out.add(token.replace(",", "."))
    return out


def words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(unicodedata.normalize("NFKC", text))]


def ngrams(tokens: list[str], n: int = N_GRAM) -> set[tuple[str, ...]]:
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def _is_ordinary(token: str) -> bool:
    return token.islower() and token not in _FUNCTION_WORDS and not token[0].isdigit()


def copied_runs(text: str, source_grams: set[tuple[str, ...]]) -> list[str]:
    """Runs of ``N_GRAM`` words shared with a source that read as copied prose."""
    original = _WORD.findall(unicodedata.normalize("NFKC", text))
    lowered = [t.lower() for t in original]
    runs = []
    for i in range(len(lowered) - N_GRAM + 1):
        if tuple(lowered[i : i + N_GRAM]) in source_grams:
            window = original[i : i + N_GRAM]
            if sum(_is_ordinary(t) for t in window) >= MIN_ORDINARY_WORDS:
                runs.append(" ".join(window))
    return runs


def names(text: str) -> set[str]:
    """Capitalized words that look like names (first word of the text excluded)."""
    return {
        m.group(0)
        for m in _CAPITALIZED.finditer(text)
        if m.start() and m.group(0).lower() not in _NOT_NAMES
    }


def check_fact(statement: str, quote: str, source: str) -> str | None:
    """Why the fact is rejected, or None when its quote supports it."""
    if len(quote.strip()) < MIN_QUOTE_CHARS:
        return "quote too short"
    # A quote that ends a clause with "." where the source has ";" or "," is still verbatim
    # (seen with the local Qwen in S5): trailing punctuation is not compared.
    if normalize(quote).rstrip(" .;,:") not in normalize(source):
        return "quote not found verbatim in the source"
    if missing := numbers(statement) - numbers(quote):
        return f"numbers not in the quote: {sorted(missing)}"
    if copied := copied_runs(statement, ngrams(words(source))):
        return f"statement copies the source wording: {copied[0]!r}"
    return None


@dataclass
class SentenceReport:
    index: int
    text: str
    problems: list[str] = field(default_factory=list)


@dataclass
class TextReport:
    sentences: list[SentenceReport]
    problems: list[str] = field(default_factory=list)
    word_count: int = 0

    @property
    def passed(self) -> bool:
        return not self.problems and all(not s.problems for s in self.sentences)

    def summary(self) -> list[str]:
        out = list(self.problems)
        for s in self.sentences:
            out.extend(f"sentence {s.index + 1} ({s.text[:60]!r}): {p}" for p in s.problems)
        return out


def check_text(
    sentences: list[tuple[str, list[str]]],
    facts: dict[str, str],
    source_texts: Iterable[str],
    *,
    min_words: int = MIN_WORDS,
    max_words: int = MAX_WORDS,
) -> TextReport:
    """Check sentences ``[(text, fact_ids)]`` against facts ``{fact_id: fact text}``."""
    source_grams: set[tuple[str, ...]] = set()
    for text in source_texts:
        source_grams |= ngrams(words(text))
    all_names = (
        set().union(*(names(f) | set(f.split()) for f in facts.values())) if facts else set()
    )
    reports = []
    for i, (text, fact_ids) in enumerate(sentences):
        report = SentenceReport(i, text)
        cited = [facts[f] for f in fact_ids if f in facts]
        if not fact_ids:
            report.problems.append("no citation")
        elif len(cited) != len(fact_ids):
            report.problems.append(f"cites unknown facts {[f for f in fact_ids if f not in facts]}")
        cited_numbers = set().union(*(numbers(c) for c in cited)) if cited else set()
        if missing := numbers(text) - cited_numbers:
            report.problems.append(f"numbers not in the cited facts: {sorted(missing)}")
        if unknown := {n for n in names(text) if n not in all_names}:
            report.problems.append(f"names not in the facts: {sorted(unknown)}")
        if copied := copied_runs(text, source_grams):
            report.problems.append(f"copies {N_GRAM}+ words from a source: {copied[0]!r}")
        report.problems.extend(claim_problems(text, cited))
        reports.append(report)
    word_count = sum(len(words(t)) for t, _ in sentences)
    problems = []
    if word_count > max_words:
        problems.append(f"too long: {word_count} words (max {max_words})")
    if word_count < min_words:
        problems.append(f"too short: {word_count} words (min {min_words})")
    return TextReport(reports, problems, word_count)


_ES_NUMBER_WORDS = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
}  # fmt: skip


def _fold(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn"
    )


def numbers_match(src: str, dst: str) -> bool:
    """Same numbers in a sentence and its Spanish version (small numbers may be words)."""
    s, d = numbers(src), numbers(dst)
    missing = {
        n
        for n in s - d
        if not (
            n.isdigit()
            and any(_ES_NUMBER_WORDS.get(w) == int(n) for w in re.findall(r"\w+", _fold(dst)))
        )
    }
    return not missing and not (d - s)


def check_alignment(source: list[str], adapted: list[str]) -> list[str]:
    """One adapted sentence per source sentence, with the same numbers."""
    if len(source) != len(adapted):
        return [f"{len(adapted)} sentences for {len(source)} in the source text"]
    problems = []
    for i, (src, dst) in enumerate(zip(source, adapted, strict=True)):
        if not numbers_match(src, dst):
            problems.append(
                f"sentence {i + 1}: numbers differ "
                f"({sorted(numbers(src))} vs {sorted(numbers(dst))})"
            )
        if comma := sorted(m for m in re.findall(r"\b\d{1,3}(?:,\d{3})+(?!\d)", src) if m in dst):
            problems.append(f"sentence {i + 1}: thousands with a comma {comma} read as decimals")
    return problems


# --- claims (plan, step 17; Sofía's S5 review in ADR D4) ---------------------------
#
# Plain word lists, so a failure names the phrase. A phrase is allowed when a cited fact
# says it too (the authors wrote "causes" in a trial); otherwise the summary says more
# than the study. The Spanish lists map to the same keys as the English ones, and a
# Spanish sentence may only use a phrase when its English sentence passed with it.

OVERCLAIMS: dict[str, tuple[str, str]] = {  # key -> (English regex, Spanish regex)
    "cure": (r"\bcur(?:e|es|ed|ing)\b", r"\bcura(?:r|n|rá)?\b"),
    "breakthrough": (r"\bbreakthrough|game[- ]changer|revolution\w*|miracle\w*",
                     r"\bavance histórico|revolucion\w*|milagr\w*"),
    "proves": (r"\bprov(?:e|es|ed|en|ing)\b|\bdemonstrat\w+ that\b",
               r"\bdemostr\w+ que|\bprueba(?:n)? que"),
    "safe": (r"\b(?:is|are|was|were) safe\b", r"\b(?:es|son|era|eran|resultó) segur[oa]s?\b"),
    "specific": (r"\b(?:is|are|was|were) specific to\b",
                 r"\b(?:es|son|era|eran) específic[oa]s? de\b"),
    "only": (r"\bthe only\b", r"\b(?:el|la|los|las) únic[oa]s?\b"),
    "fail": (r"\bwhere (?:standard |usual |current |other )?(?:tests|exams|methods) fail",
             r"\bdonde (?:las )?pruebas\b.*\bfallan"),
    "alarm": (r"\balarming|devastating|deadly|terrifying|epidemic of",
              r"\balarmante|devastador\w*|mortal(?:es)?\b|aterrador\w*|epidemia de"),
}  # fmt: skip
# Every tense (step 18: "resulted in" and "triggered" passed in English, and only the
# Spanish check caught "desencadenaban").
CAUSAL = (r"\bcaus(?:e|es|ed|ing)\b|\blead(?:s|ing)? to\b|\bled to\b"
          r"|\bdr(?:ive|ives|iven|ove|iving)\b|\bcontribut\w+ to\b"
          r"|\bresult(?:s|ed|ing)? in\b|\btrigger(?:s|ed|ing)?\b"
          r"|\bdue to\b|\bbecause of\b",
          r"\bcaus(?:a|an|as|ó|aron|ando|ar|ad[oa]s?|ará|arán|aría|arían)\b|\bprovoca\w*"
          r"|\bconduce\w* a\b|\bcontribuy\w+ a\b"
          r"|\bdesencadena\w*")  # fmt: skip
PREDICTS = (r"\bpredict\w*|\bforecast\w*", r"\bpredec\w*|\bpredic\w*|\bpronostic\w*")
# Words of uncertainty only: "associated" is not a hedge but a description (turning it
# into a cause is the causal rule's job), and "appear" is too often sight ("a line
# appeared") to count. "Could" counts unless it is ability ("could be measured", "could
# be seen": a participle follows); step 18 found "could be a helpful tool" flagged as
# certain. In Spanish the causal rule is the verb and the noun, not "causal" nor
# "causalidad", as in English ("does not establish causality" was flagged).
HEDGES = (r"\bmay\b|\bmight\b|\bsuggest\w*|\bpossibl\w*|\blikely\b|\b(?:appears?|seems?) to\b"
          r"|\bcould (?:be (?!\w+(?:ed|en)\b)|help|serve|offer|improve|benefit)"
          r"|\bpreliminar\w*|\bpotential\w*|\bunclear\b|\bneeds? confirm\w*",
          r"\bpodr[íi]\w+|\bsugier\w+|\bsugiere\w*|\bposibl\w*|\bprobabl\w*|\bparec\w+"
          r"|\bpreliminar\w*|\bquiz[aá]s?\b|\btal vez\b|\bapunta\w*|\bpotencial\w*"
          r"|\bno está claro\b|\bconfirmar\w*")  # fmt: skip

_CLAIMS = {**OVERCLAIMS, "causal": CAUSAL, "predicts": PREDICTS}


def _has(pattern: str, text: str) -> bool:
    return re.search(pattern, _typography(text), re.IGNORECASE) is not None


def claims(text: str, lang: str) -> set[str]:
    """Keys of the overclaims, causal and predictive phrases in a text."""
    i = 0 if lang == "en" else 1
    return {key for key, patterns in _CLAIMS.items() if _has(patterns[i], text)}


def claim_problems(text: str, cited: list[str]) -> list[str]:
    """Problems of an English sentence: a claim its cited facts do not make, or the
    hedge of its facts dropped (every cited fact hedged, the sentence certain)."""
    supported = set().union(*(claims(c, "en") for c in cited)) if cited else set()
    problems = [
        f"says '{k}' but no cited fact does" for k in sorted(claims(text, "en") - supported)
    ]
    if cited and all(_has(HEDGES[0], c) for c in cited) and not _has(HEDGES[0], text):
        problems.append("drops the caution of its facts (may, suggests, possibly…)")
    return problems


def check_claims_es(source: list[str], adapted: list[str]) -> list[str]:
    """A Spanish sentence makes no claim its English sentence does not make, and keeps
    its caution ("may" is "podría", not "puede": Sofía, S5)."""
    problems = []
    for i, (en, es) in enumerate(zip(source, adapted, strict=False), start=1):
        for key in sorted(claims(es, "es") - claims(en, "en")):
            problems.append(f"sentence {i}: '{key}' is not in the English sentence")
        if _has(HEDGES[0], en) and not _has(HEDGES[1], es):
            problems.append(f"sentence {i}: the English sentence is cautious and this is not")
    return problems


# --- Spanish spelling (plan, step 17; decision of Aday, SCOPE v73) -------------------
#
# Hunspell with the RLA-ES dictionary (``narrative/hunspell/``) through ``spylls``. Most
# words it does not know are technical terms whose English twin is in the English
# sentence ("ribosómico" for "ribosomal", "transcraneal" for "transcranial"), so an
# unknown word passes when it shares a long stem with a word of that sentence, after
# folding the spellings that differ between the two languages. Measured on the 38 S5
# texts in Spanish: 45 different unknown words without the stem rule, 10 with it, and
# the real typos ("emocinales", "biimpresas") are still caught. What is left is either
# a typo or a term for ``extra_es.txt``. Capitalized words inside a sentence are names
# and are not checked.

_HUNSPELL = resources.files("synaptica.narrative") / "hunspell"
_ES_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_FOLDS = (("ph", "f"), ("th", "t"), ("ch", "c"), ("qu", "c"), ("k", "c"), ("y", "i"),
          ("rr", "r"), ("nm", "m"), ("mm", "m"), ("ss", "s"), ("ll", "l"))  # fmt: skip


@functools.cache
def _dictionary():
    from spylls.hunspell import Dictionary

    with resources.as_file(_HUNSPELL) as folder:
        return Dictionary.from_files(str(folder / "es_ES"))


@functools.cache
def _extra_words() -> frozenset[str]:
    text = (_HUNSPELL / "extra_es.txt").read_text(encoding="utf-8")
    return frozenset(w.strip() for w in text.splitlines() if w.strip() and w[0] != "#")


def _cognate_form(word: str) -> str:
    word = _fold(word)
    for a, b in _FOLDS:
        word = word.replace(a, b)
    return word


def _shares_stem(word: str, english: Iterable[str]) -> bool:
    w = _cognate_form(word)
    for other in english:
        o = _cognate_form(other)
        shorter = min(len(w), len(o))
        common = next((i for i in range(shorter) if w[i] != o[i]), shorter)
        if common >= max(4, -(-6 * shorter // 10)):  # 60 % of the shorter, rounded up
            return True
    return False


def _in_extra(word: str) -> bool:
    extra = _extra_words()
    forms = {word, word.removesuffix("s"), word.removesuffix("es")}
    forms |= {f[:-1] + "o" for f in forms if f.endswith("a")}
    forms |= {f[:-1] for f in forms if f.endswith("ora")}  # sensoriomotora
    return bool(forms & extra)


_CLITICS = re.compile(r"(?:(?:me|te|se|nos|os)(?=l[oae]s?$|$))?(?:l[oae]s?|me|te|se|nos|os)$")
_UNSTRESS = str.maketrans("áéí", "aei")


def _without_clitics(word: str) -> str | None:
    """A gerund or an infinitive without its pronouns: «despejándolos» → «despejando»,
    «dárselo» → «dar». None when the word does not end like one."""
    base = _CLITICS.sub("", word)
    if base == word or not re.search(r"(?:ndo|[aeií]r)$", base.translate(_UNSTRESS)):
        return None
    return base.translate(_UNSTRESS)


def unknown_words_es(sentence: str, english: str = "") -> list[str]:
    """Words of a Spanish sentence that are neither in the dictionary nor in our list,
    nor the twin of a word of its English sentence."""
    english_words = _ES_WORD.findall(english)
    english_lower = {w.lower() for w in english_words}
    out = []
    after_name = False
    for m in _ES_WORD.finditer(unicodedata.normalize("NFC", sentence)):
        word = m.group(0)
        at_start = not sentence[: m.start()].strip(" ¿¡\"'«(")
        if word[0].isupper() and not at_start:
            after_name = sentence[m.end() : m.end() + 1] == " "
            continue  # a name
        if after_name and word.islower() and not _dictionary().lookup(word):
            after_name = False
            continue  # the epithet of a species ("Caenorhabditis elegans")
        after_name = False
        if word.isupper() or word.lower() in english_lower:
            continue  # an acronym, a gene, a word kept from English
        lower = word.lower()
        if _dictionary().lookup(word) or _dictionary().lookup(lower) or _in_extra(lower):
            continue
        if (base := _without_clitics(lower)) and _dictionary().lookup(base):
            continue  # "despejándolos": the dictionary has no forms with pronouns (step 18)
        if not _shares_stem(lower, english_words):
            out.append(word)
    return out


def check_spelling_es(source: list[str], adapted: list[str]) -> list[str]:
    problems = []
    for i, (en, es) in enumerate(zip(source, adapted, strict=False), start=1):
        if unknown := unknown_words_es(es, en):
            problems.append(f"sentence {i}: words not in the Spanish dictionary {unknown}")
    return problems
