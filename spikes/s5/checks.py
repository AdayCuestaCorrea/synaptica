"""Deterministic checks for extracted facts and written sentences (S5 spike).

Copied and adapted from paleo-atlas ``src/paleo/narrative/checks.py`` (same author). Only
the domain-free part is kept; the paleontology rules (abbreviated species, Spanish clade
names) are dropped and the name stop-list is adapted to study summaries.

No model judges another model here: every rule is plain string logic, so a failure can
be explained and reproduced. (The S5 judge is a separate, extra step.)

* **Fact check**: a fact's quote must appear verbatim in the abstract, every number in the
  fact must appear in that quote, and the fact must not copy the abstract's wording.
* **Citation**: every sentence cites at least one existing fact.
* **Faithfulness**: numbers in a sentence must come from the facts it cites; capitalized
  names must come from the facts.
* **Anti-copy**: no sentence shares a run of ``N_GRAM`` words with the source. Runs made
  mostly of names, numbers and function words count as facts, not prose: a run only
  counts as copied when it has at least ``MIN_ORDINARY_WORDS`` ordinary words.
* **Alignment** (EN -> ES): one Spanish sentence per English one, same numbers.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

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


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    return " ".join(text.lower().split())


def numbers(text: str) -> set[str]:
    """Numbers in a language-neutral form: "1,5" and "1.5" -> "1.5"; "1,000" -> "1000"."""
    text = re.sub(r"(?<=\d)[ \u00a0\u202f](?=\d{3}(?:\D|$))", "", text)
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
    if normalize(quote) not in normalize(source):
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
        reports.append(report)
    word_count = sum(len(words(t)) for t, _ in sentences)
    problems = []
    if word_count > MAX_WORDS:
        problems.append(f"too long: {word_count} words (max {MAX_WORDS})")
    if word_count < MIN_WORDS:
        problems.append(f"too short: {word_count} words (min {MIN_WORDS})")
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
