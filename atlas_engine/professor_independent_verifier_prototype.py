"""Isolated deterministic fact-verifier prototype; not wired into runtime.

This intentionally checks fixture-defined phrase evidence, not semantics.
"""
from dataclasses import dataclass
import re


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _sentences(text: str) -> tuple[str, ...]:
    return tuple(_norm(part) for part in re.split(r"[.!?;]+", text) if _norm(part))


def _negated_phrase_present(text: str, phrase: str) -> bool:
    """Detect narrow negation within the same sentence/semicolon clause."""
    phrase_tokens = _norm(phrase).split()
    if not phrase_tokens:
        return False
    for tokens in (sentence.split() for sentence in _sentences(text)):
        for i in range(len(tokens) - len(phrase_tokens) + 1):
            if tokens[i:i + len(phrase_tokens)] != phrase_tokens:
                continue
            prefix = tokens[max(0, i - 3):i]
            if prefix[-2:] == ["not", "only"]:
                continue
            if prefix[-1:] in (["not"], ["never"], ["without"], ["no"]):
                return True
            if any(prefix[-n:] == pattern for n, pattern in (
                (2, ["did", "not"]), (2, ["does", "not"]),
                (2, ["do", "not"]), (2, ["is", "not"]),
                (2, ["was", "not"]), (3, ["does", "not", "record"]),
                (3, ["did", "not", "record"]), (3, ["do", "not", "record"]),
            )):
                return True
    return False


def _quoted_phrase_present(text: str, phrase: str) -> bool:
    """Treat a matching phrase inside straight/curly quotation marks as reported speech."""
    phrase_tokens = _norm(phrase).split()
    if not phrase_tokens:
        return False
    for sentence in _sentences(text):
        tokens = sentence.split()
        for i in range(len(tokens) - len(phrase_tokens) + 1):
            if tokens[i:i + len(phrase_tokens)] != phrase_tokens:
                continue
            # Locate the original phrase in its sentence and check quote parity.
            original_parts = re.split(r"[.!?;]+", text)
            for part in original_parts:
                normalized_part = _norm(part)
                if _norm(phrase) not in normalized_part:
                    continue
                before = part.lower().find(phrase.lower())
                if before >= 0:
                    prefix = part[:before]
                    suffix = part[before + len(phrase):]
                    if prefix.count('"') % 2 or suffix.count('"') % 2:
                        return True
                    if prefix.count("“") > prefix.count("”") or suffix.count("”") > suffix.count("“"):
                        return True
    return False


def _source_near_phrase(text: str, phrase: str, source_id: str) -> bool:
    """Require a source token in the claim sentence or its immediately following citation sentence."""
    parts = [part for part in re.split(r"[.!?;]+", text) if _norm(part)]
    phrase_norm = _norm(phrase)
    source_pattern = re.compile(r"(?<![A-Z0-9_-])" + re.escape(source_id) + r"(?![A-Z0-9_-])", re.IGNORECASE)
    for index, part in enumerate(parts):
        if phrase_norm not in _norm(part):
            continue
        for candidate in parts[index:index + 2]:
            if source_pattern.search(candidate):
                return True
    return False


def _unestablished_phrase_present(text: str, phrase: str) -> bool:
    """Detect narrow hedge/claim/mention context within a sentence/clause."""
    phrase_tokens = _norm(phrase).split()
    markers = {
        "possibly", "maybe", "alleged", "allegedly", "claimed", "claim",
        "claims", "draft", "unverified", "disputed", "mention", "mentions",
        "mentioned", "speculative", "uncertain", "example", "glossary",
        "illustrative", "hypothetical",
    }
    for sentence in _sentences(text):
        tokens = sentence.split()
        for i in range(len(tokens) - len(phrase_tokens) + 1):
            if tokens[i:i + len(phrase_tokens)] != phrase_tokens:
                continue
            prefix = tokens[max(0, i - 3):i]
            suffix = tokens[i + len(phrase_tokens):i + len(phrase_tokens) + 4]
            if markers.intersection(prefix) or markers.intersection(suffix):
                return True
    return False

@dataclass(frozen=True)
class SourceEvidence:
    """Explicit source text supplied by a deterministic evaluation fixture."""
    source_id: str
    text: str


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
    unsupported_source_ids: tuple[str, ...] = ()
    conflicting_source_ids: tuple[str, ...] = ()
    unsupported_fact_ids: tuple[str, ...] = ()
    conflicting_fact_ids: tuple[str, ...] = ()


def _source_phrase_status(text: str, phrase: str) -> str:
    """Return supported, denied, unestablished, or absent using narrow lexical rules."""
    normalized = _norm(text)
    phrase_norm = _norm(phrase)
    if not phrase_norm or phrase_norm not in normalized:
        return "absent"
    if _negated_phrase_present(text, phrase):
        return "denied"
    if _unestablished_phrase_present(text, phrase) or _quoted_phrase_present(text, phrase):
        return "unestablished"
    return "supported"


def verify_answer(
    answer: str,
    *,
    facts: tuple[Fact, ...],
    required_constraints: tuple[str, ...] = (),
    available_source_ids: tuple[str, ...] = (),
    required_source_ids: tuple[str, ...] = (),
    source_evidence: tuple[SourceEvidence, ...] = (),
    abstention_required: bool = False,
) -> VerificationResult:
    """Verify against explicit, fixture-owned phrase rules and source IDs."""
    normalized = _norm(answer)
    supported, missing, contradicted = [], [], []
    for fact in facts:
        matches = any(_norm(p) in normalized for p in fact.supported_phrases)
        negated_matches = any(
            _negated_phrase_present(answer, p) for p in fact.supported_phrases
        )
        unestablished_matches = any(
            _unestablished_phrase_present(answer, p)
            or _quoted_phrase_present(answer, p)
            for p in fact.supported_phrases
        )
        conflicts = any(_norm(p) in normalized for p in fact.contradiction_phrases)
        if conflicts or negated_matches:
            contradicted.append(fact.fact_id)
        elif unestablished_matches:
            missing.append(fact.fact_id)
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
    missing_sources_list = [
        sid for sid in source_requirements
        if sid not in available or sid not in cited
    ]
    # A fact-linked source must be cited beside its claim, not merely elsewhere in the answer.
    for fact in facts:
        if fact.source_id and fact.source_id in available and not any(
            _source_near_phrase(answer, phrase, fact.source_id)
            for phrase in fact.supported_phrases
        ):
            if fact.source_id not in missing_sources_list:
                missing_sources_list.append(fact.source_id)
    missing_sources = tuple(missing_sources_list)

    unsupported_source_ids: list[str] = []
    conflicting_source_ids: list[str] = []
    unsupported_fact_ids: list[str] = []
    conflicting_fact_ids: list[str] = []
    if source_evidence:
        evidence_by_id: dict[str, list[SourceEvidence]] = {}
        for evidence in source_evidence:
            evidence_by_id.setdefault(evidence.source_id, []).append(evidence)
        for fact in facts:
            if not fact.source_id:
                continue
            matching_phrases = [
                phrase for phrase in fact.supported_phrases
                if _norm(phrase) in _norm(answer)
            ]
            if not matching_phrases:
                continue
            evidence_items = evidence_by_id.get(fact.source_id, [])
            if not evidence_items:
                if fact.source_id not in unsupported_source_ids:
                    unsupported_source_ids.append(fact.source_id)
                unsupported_fact_ids.append(fact.fact_id)
                continue
            statuses = [
                _source_phrase_status(item.text, phrase)
                for item in evidence_items
                for phrase in matching_phrases
            ]
            has_support = "supported" in statuses
            has_denial = "denied" in statuses
            if has_support and has_denial:
                if fact.source_id not in conflicting_source_ids:
                    conflicting_source_ids.append(fact.source_id)
                conflicting_fact_ids.append(fact.fact_id)
            elif not has_support:
                if fact.source_id not in unsupported_source_ids:
                    unsupported_source_ids.append(fact.source_id)
                unsupported_fact_ids.append(fact.fact_id)

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
        and not missing_sources and not unsupported_source_ids
        and not conflicting_source_ids and abstention_ok
    )
    return VerificationResult(
        passed=passed,
        supported_fact_ids=tuple(supported),
        missing_fact_ids=tuple(missing),
        contradicted_fact_ids=tuple(contradicted),
        missing_constraints=missing_constraints,
        missing_source_ids=missing_sources,
        abstention_required=abstention_required,
        unsupported_source_ids=tuple(unsupported_source_ids),
        conflicting_source_ids=tuple(conflicting_source_ids),
        unsupported_fact_ids=tuple(unsupported_fact_ids),
        conflicting_fact_ids=tuple(conflicting_fact_ids),
    )
