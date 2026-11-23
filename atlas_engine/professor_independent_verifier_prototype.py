"""Isolated deterministic fact-verifier prototype; not wired into runtime.

This intentionally checks fixture-defined phrase evidence, not semantics.
"""
from dataclasses import dataclass
import re


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _negated_phrase_present(text: str, phrase: str) -> bool:
    """Detect a narrow, deterministic negation window before a supported phrase."""
    phrase = _norm(phrase)
    if not phrase:
        return False
    negation = r"(?:no|not(?!\\s+only)|never|without|did not|does not|do not|is not|was not)"
    # Allow up to three intervening normalized words. This is characterization,
    # not general natural-language negation handling.
    return bool(re.search(rf"\b{negation}\b(?:\w+\s+){{0,3}}{re.escape(phrase)}\b", text))


@dataclass(frozen=True)
class Fact:
    fact_id: str
    supported_phrases: tuple[str, ...]
    contradiction_phrases: tuple[str, ...] = ()
    source_id: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    supported_fact_ids: tuple[str, ...]
    missing_fact_ids: tuple[str, ...]
    contradicted_fact_ids: tuple[str, ...]
    missing_constraints: tuple[str, ...]
    missing_source_ids: tuple[str, ...]
    abstention_required: bool = False


def verify_answer(
    answer: str,
    *,
    facts: tuple[Fact, ...],
    required_constraints: tuple[str, ...] = (),
    available_source_ids: tuple[str, ...] = (),
    required_source_ids: tuple[str, ...] = (),
    abstention_required: bool = False,
) -> VerificationResult:
    """Verify against explicit, fixture-owned phrase rules and source IDs."""
    normalized = _norm(answer)
    supported, missing, contradicted = [], [], []
    for fact in facts:
        matches = any(_norm(p) in normalized for p in fact.supported_phrases)
        negated_matches = any(
            _negated_phrase_present(normalized, p) for p in fact.supported_phrases
        )
        conflicts = any(_norm(p) in normalized for p in fact.contradiction_phrases)
        if conflicts or negated_matches:
            contradicted.append(fact.fact_id)
        elif matches:
            supported.append(fact.fact_id)
        else:
            missing.append(fact.fact_id)

    missing_constraints = tuple(
        c for c in required_constraints if _norm(c) not in normalized
    )
    available = set(available_source_ids)
    cited = set(re.findall(r"\b[A-Z][A-Z0-9_-]*\b", answer))
    fact_source_ids = tuple(f.source_id for f in facts if f.source_id)
    source_requirements = tuple(dict.fromkeys((*required_source_ids, *fact_source_ids)))
    missing_sources = tuple(
        sid for sid in source_requirements
        if sid not in available or sid not in cited
    )
    # An abstention-only fixture passes only when there are no required facts,
    # no required constraints, and the answer explicitly signals inability.
    abstains = any(phrase in normalized for phrase in (
        "cannot verify", "not enough evidence", "unknown", "i do not know"
    ))
    abstention_ok = (not abstention_required) or (
        abstains and not facts and not required_constraints
    )
    passed = (
        not missing and not contradicted and not missing_constraints
        and not missing_sources and abstention_ok
    )
    return VerificationResult(
        passed=passed,
        supported_fact_ids=tuple(supported),
        missing_fact_ids=tuple(missing),
        contradicted_fact_ids=tuple(contradicted),
        missing_constraints=missing_constraints,
        missing_source_ids=missing_sources,
        abstention_required=abstention_required,
    )
