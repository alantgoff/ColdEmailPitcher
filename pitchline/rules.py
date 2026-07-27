"""Parse ``PITCH_RULES.md`` into typed constants.

This module is the single source of truth for every threshold in Pitchline. No rule
value may be hard-coded elsewhere: modules import the constants below, and tests assert
against them. If ``PITCH_RULES.md`` is edited, the change propagates on next import — and
if a required rule or parameter goes missing, import fails loudly with every problem
listed at once rather than silently falling back to a default.

Rule file grammar (a deliberately small subset of Markdown):

    ## §<n> — <section title>
    ### <RULE-ID> — <rule title>
    - **Severity:** hard | soft | advisory
    - **Enforced by:** <dotted.module>[, ...]
    - **Source:** <quoted passage the rule derives from>
    > **RULE-CHECK:** <note where the source is silent and we took the stricter reading>
    ```params
    key = <int | float | bool | "string" | [list, of, scalars]>
    ```

A document-level ```meta block carries the spec version.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Final, Iterator, Mapping, Sequence

__all__ = [
    "RuleSpecError",
    "RuleNotFoundError",
    "RuleParamError",
    "Severity",
    "Rule",
    "RuleBook",
    "parse_rules_text",
    "load_rulebook",
    "RULES",
]


# --------------------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------------------


class RuleSpecError(RuntimeError):
    """The rules file is missing, malformed, or fails the required-parameter manifest."""


class RuleNotFoundError(RuleSpecError):
    """A rule ID referenced by code does not exist in the rules file."""


class RuleParamError(RuleSpecError):
    """A rule parameter is missing or has the wrong type."""


# --------------------------------------------------------------------------------------
# Value model
# --------------------------------------------------------------------------------------


class Severity(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    ADVISORY = "advisory"


ScalarValue = bool | int | float | str
ParamValue = ScalarValue | tuple[ScalarValue, ...]


@dataclass(frozen=True)
class Rule:
    """One rule, e.g. ``R2.1``."""

    id: str
    section: int
    section_title: str
    title: str
    severity: Severity
    enforced_by: tuple[str, ...]
    source: str
    prose: str
    params: Mapping[str, ParamValue]
    rule_checks: tuple[str, ...]
    line_no: int

    @property
    def is_hard(self) -> bool:
        return self.severity is Severity.HARD

    def get(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)

    def require(self, key: str) -> ParamValue:
        try:
            return self.params[key]
        except KeyError:
            raise RuleParamError(f"{self.id}: missing required parameter {key!r}") from None

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return f"{self.id} ({self.severity.value}) — {self.title}"


# --------------------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^##\s+§(?P<num>\d+)\s*[—–-]\s*(?P<title>.+?)\s*$")
_RULE_RE = re.compile(r"^###\s+(?P<id>R\d+\.\d+)\s*[—–-]\s*(?P<title>.+?)\s*$")
_META_FIELD_RE = re.compile(r"^-\s+\*\*(?P<key>[A-Za-z][A-Za-z ]*?):?\*\*\s*(?P<value>.*?)\s*$")
_RULE_CHECK_RE = re.compile(r"^>\s*\*\*RULE-CHECK:?\*\*\s*(?P<note>.*?)\s*$")
_FENCE_RE = re.compile(r"^```(?P<lang>[a-zA-Z]*)\s*$")
_ASSIGN_RE = re.compile(r"^(?P<key>[a-z_][a-z0-9_]*)\s*=\s*(?P<value>.+?)\s*$")
_RULE_ID_RE = re.compile(r"^R\d+\.\d+$")


def _parse_scalar(token: str, *, ctx: str) -> ScalarValue:
    token = token.strip()
    if not token:
        raise RuleSpecError(f"{ctx}: empty value")
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        return token[1:-1].replace('\\"', '"')
    if token == "true":
        return True
    if token == "false":
        return False
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        pass
    raise RuleSpecError(
        f"{ctx}: cannot parse value {token!r} "
        "(expected int, float, true/false, or a double-quoted string)"
    )


def _split_list_items(body: str, *, ctx: str) -> list[str]:
    """Split a bracket body on commas, ignoring commas inside quoted strings."""
    items: list[str] = []
    current: list[str] = []
    in_string = False
    escaped = False
    for ch in body:
        if escaped:
            current.append(ch)
            escaped = False
        elif ch == "\\" and in_string:
            current.append(ch)
            escaped = True
        elif ch == '"':
            in_string = not in_string
            current.append(ch)
        elif ch == "," and not in_string:
            items.append("".join(current))
            current = []
        else:
            current.append(ch)
    if in_string:
        raise RuleSpecError(f"{ctx}: unterminated string in list")
    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return [item.strip() for item in items if item.strip()]


def _parse_value(raw: str, *, ctx: str) -> ParamValue:
    raw = raw.strip()
    if raw.startswith("["):
        if not raw.endswith("]"):
            raise RuleSpecError(f"{ctx}: unterminated list")
        return tuple(_parse_scalar(item, ctx=ctx) for item in _split_list_items(raw[1:-1], ctx=ctx))
    return _parse_scalar(raw, ctx=ctx)


def _parse_param_block(lines: Sequence[str], *, ctx: str) -> dict[str, ParamValue]:
    params: dict[str, ParamValue] = {}
    buffer: list[str] = []
    depth = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        buffer.append(stripped)
        depth += stripped.count("[") - stripped.count("]")
        if depth > 0:
            continue  # multi-line list still open
        joined = " ".join(buffer)
        buffer = []
        match = _ASSIGN_RE.match(joined)
        if not match:
            raise RuleSpecError(f"{ctx}: cannot parse params line {joined!r}")
        key = match.group("key")
        if key in params:
            raise RuleSpecError(f"{ctx}: duplicate parameter {key!r}")
        params[key] = _parse_value(match.group("value"), ctx=f"{ctx}.{key}")
    if buffer:
        raise RuleSpecError(f"{ctx}: unterminated value {' '.join(buffer)!r}")
    return params


@dataclass(frozen=True)
class RuleBook:
    """All rules parsed from a rules file, addressable by ID."""

    path: Path | None
    spec_version: str
    meta: Mapping[str, ParamValue]
    rules: Mapping[str, Rule]
    checksum: str

    # -- lookup ------------------------------------------------------------------------

    def __getitem__(self, rule_id: str) -> Rule:
        try:
            return self.rules[rule_id]
        except KeyError:
            raise RuleNotFoundError(f"no such rule: {rule_id}") from None

    def __contains__(self, rule_id: object) -> bool:
        return rule_id in self.rules

    def __iter__(self) -> Iterator[Rule]:
        return iter(self.rules.values())

    def __len__(self) -> int:
        return len(self.rules)

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(self.rules)

    def hard_rules(self) -> tuple[Rule, ...]:
        return tuple(r for r in self.rules.values() if r.is_hard)

    def section(self, number: int) -> tuple[Rule, ...]:
        return tuple(r for r in self.rules.values() if r.section == number)

    def enforced_by(self, module: str) -> tuple[Rule, ...]:
        return tuple(r for r in self.rules.values() if module in r.enforced_by)

    def rule_checks(self) -> tuple[tuple[str, str], ...]:
        """Every open RULE-CHECK note, as ``(rule_id, note)`` — the author review queue."""
        return tuple((r.id, note) for r in self.rules.values() for note in r.rule_checks)

    # -- typed accessors ---------------------------------------------------------------

    def _param(self, rule_id: str, key: str) -> ParamValue:
        return self[rule_id].require(key)

    def int_(self, rule_id: str, key: str) -> int:
        value = self._param(rule_id, key)
        # bool is a subclass of int; a flag where a count belongs is a spec bug.
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuleParamError(f"{rule_id}.{key}: expected int, got {type(value).__name__}")
        return value

    def float_(self, rule_id: str, key: str) -> float:
        value = self._param(rule_id, key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuleParamError(f"{rule_id}.{key}: expected float, got {type(value).__name__}")
        return float(value)

    def bool_(self, rule_id: str, key: str) -> bool:
        value = self._param(rule_id, key)
        if not isinstance(value, bool):
            raise RuleParamError(f"{rule_id}.{key}: expected bool, got {type(value).__name__}")
        return value

    def str_(self, rule_id: str, key: str) -> str:
        value = self._param(rule_id, key)
        if not isinstance(value, str):
            raise RuleParamError(f"{rule_id}.{key}: expected str, got {type(value).__name__}")
        return value

    def str_list(self, rule_id: str, key: str) -> tuple[str, ...]:
        value = self._param(rule_id, key)
        if not isinstance(value, tuple) or not all(isinstance(v, str) for v in value):
            raise RuleParamError(f"{rule_id}.{key}: expected list of str")
        return value  # type: ignore[return-value]

    def int_list(self, rule_id: str, key: str) -> tuple[int, ...]:
        value = self._param(rule_id, key)
        if not isinstance(value, tuple) or not all(
            isinstance(v, int) and not isinstance(v, bool) for v in value
        ):
            raise RuleParamError(f"{rule_id}.{key}: expected list of int")
        return value  # type: ignore[return-value]

    # -- provenance --------------------------------------------------------------------

    @property
    def fingerprint(self) -> str:
        """Stamped onto every draft so a send is traceable to the rules that cleared it."""
        return f"{self.spec_version}+{self.checksum[:12]}"


def parse_rules_text(text: str, *, path: Path | None = None) -> RuleBook:
    """Parse rules-file text into a :class:`RuleBook`. Raises on any malformation."""
    lines = text.splitlines()
    meta: dict[str, ParamValue] = {}
    rules: dict[str, Rule] = {}

    section_num = 0
    section_title = ""

    cur: dict[str, Any] | None = None
    fence_lang: str | None = None
    fence_lines: list[str] = []
    fence_owner: dict[str, Any] | None = None

    def flush_rule() -> None:
        nonlocal cur
        if cur is None:
            return
        rule = Rule(
            id=cur["id"],
            section=cur["section"],
            section_title=cur["section_title"],
            title=cur["title"],
            severity=cur["severity"],
            enforced_by=tuple(cur["enforced_by"]),
            source=cur["source"],
            prose=" ".join(cur["prose"]).strip(),
            params=dict(cur["params"]),
            rule_checks=tuple(cur["rule_checks"]),
            line_no=cur["line_no"],
        )
        if rule.severity is None:  # pragma: no cover - guarded at parse time
            raise RuleSpecError(f"{rule.id}: missing **Severity:**")
        rules[rule.id] = rule
        cur = None

    for lineno, line in enumerate(lines, start=1):
        fence = _FENCE_RE.match(line)
        if fence and fence_lang is None:
            fence_lang = fence.group("lang")
            fence_lines = []
            fence_owner = cur
            continue
        if fence_lang is not None:
            if line.strip() == "```":
                if fence_lang == "params":
                    owner = fence_owner
                    if owner is None:
                        raise RuleSpecError(f"line {lineno}: params block outside any rule")
                    if owner["params"]:
                        raise RuleSpecError(f"{owner['id']}: more than one params block")
                    owner["params"] = _parse_param_block(fence_lines, ctx=owner["id"])
                elif fence_lang == "meta":
                    meta.update(_parse_param_block(fence_lines, ctx="meta"))
                fence_lang = None
                fence_lines = []
                fence_owner = None
            else:
                fence_lines.append(line)
            continue

        section_match = _SECTION_RE.match(line)
        if section_match:
            flush_rule()
            section_num = int(section_match.group("num"))
            section_title = section_match.group("title")
            continue

        rule_match = _RULE_RE.match(line)
        if rule_match:
            flush_rule()
            rule_id = rule_match.group("id")
            if rule_id in rules:
                raise RuleSpecError(f"duplicate rule id {rule_id} at line {lineno}")
            cur = {
                "id": rule_id,
                "section": section_num,
                "section_title": section_title,
                "title": rule_match.group("title"),
                "severity": None,
                "enforced_by": [],
                "source": "",
                "prose": [],
                "params": {},
                "rule_checks": [],
                "line_no": lineno,
            }
            continue

        if cur is None:
            continue

        field_match = _META_FIELD_RE.match(line)
        if field_match:
            key = field_match.group("key").strip().lower()
            value = field_match.group("value").strip()
            if key == "severity":
                try:
                    cur["severity"] = Severity(value.lower())
                except ValueError:
                    raise RuleSpecError(
                        f"{cur['id']}: unknown severity {value!r} (line {lineno})"
                    ) from None
            elif key == "enforced by":
                cur["enforced_by"] = [p.strip() for p in value.split(",") if p.strip()]
            elif key == "source":
                cur["source"] = value
            continue

        check_match = _RULE_CHECK_RE.match(line)
        if check_match:
            cur["rule_checks"].append(check_match.group("note"))
            continue

        stripped = line.strip()
        if stripped.startswith(">"):
            # continuation of a RULE-CHECK blockquote
            if cur["rule_checks"]:
                cur["rule_checks"][-1] += " " + stripped.lstrip("> ").strip()
            continue
        if stripped and not stripped.startswith(("|", "---")):
            cur["prose"].append(stripped)

    if fence_lang is not None:
        raise RuleSpecError("unterminated code fence in rules file")
    flush_rule()

    if not rules:
        raise RuleSpecError("rules file contains no rules")

    for rule in rules.values():
        if rule.severity is None:
            raise RuleSpecError(f"{rule.id}: missing **Severity:**")
        if not rule.enforced_by:
            raise RuleSpecError(f"{rule.id}: missing **Enforced by:**")
        if not rule.source:
            raise RuleSpecError(f"{rule.id}: missing **Source:** — every rule cites its origin")

    spec_version = meta.get("spec_version")
    if not isinstance(spec_version, str):
        raise RuleSpecError("rules file meta block must declare a string spec_version")

    return RuleBook(
        path=path,
        spec_version=spec_version,
        meta=meta,
        rules=rules,
        checksum=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def default_rules_path() -> Path:
    """``$PITCHLINE_RULES_PATH`` if set, else ``PITCH_RULES.md`` in the repo root."""
    override = os.environ.get("PITCHLINE_RULES_PATH")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parent.parent / "PITCH_RULES.md"


def load_rulebook(path: Path | str | None = None) -> RuleBook:
    """Load, parse and validate a rules file."""
    resolved = Path(path) if path is not None else default_rules_path()
    try:
        text = resolved.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RuleSpecError(
            f"rules file not found at {resolved}. PITCH_RULES.md is the normative spec; "
            "Pitchline refuses to run without it."
        ) from None
    book = parse_rules_text(text, path=resolved)
    validate(book)
    return book


# --------------------------------------------------------------------------------------
# Required-parameter manifest
# --------------------------------------------------------------------------------------

_INT, _FLOAT, _BOOL, _STR, _STRS, _INTS = "int", "float", "bool", "str", "list[str]", "list[int]"

#: Every parameter the codebase reads, with its expected type. Import fails if the rules
#: file drops one — swapping in a revised PITCH_RULES.md can never silently disable a gate.
REQUIRED_PARAMS: Final[Mapping[str, Mapping[str, str]]] = {
    "R0.1": {
        "baseline_reply_rate": _FLOAT,
        "ceiling_reply_rate_low": _FLOAT,
        "ceiling_reply_rate_high": _FLOAT,
        "min_sends_for_rate_significance": _INT,
    },
    "R1.1": {"max_campaign_targets": _INT, "warn_campaign_targets": _INT},
    "R1.2": {
        "dimensions": _STRS,
        "score_scale_min": _INT,
        "score_scale_max": _INT,
        "min_composite_score": _FLOAT,
        "min_stage_score": _INT,
        "min_sector_score": _INT,
        "require_rationale_per_dimension": _BOOL,
        "require_evidence_per_dimension": _BOOL,
    },
    "R1.3": {
        "min_evidence_snippets": _INT,
        "required_evidence_areas": _STRS,
        "min_snippets_per_required_area": _INT,
        "cache_ttl_days": _INT,
        "max_evidence_age_days": _INT,
        "recent_activity_max_age_days": _INT,
        "forbid_refetch_inside_ttl": _BOOL,
    },
    "R1.4": {
        "partner_level_roles": _STRS,
        "generic_mailbox_locals": _STRS,
        "require_named_individual": _BOOL,
        "forbid_firm_level_targets": _BOOL,
        "forbid_generic_mailboxes": _BOOL,
        "dedupe_key": _STRS,
    },
    "R1.5": {
        "suppress_direct_conflict": _BOOL,
        "allow_override": _BOOL,
        "override_requires_human": _BOOL,
        "override_requires_reason": _BOOL,
        "model_may_override": _BOOL,
        "enforce_at_dispatch": _BOOL,
    },
    "R2.1": {
        "max_words": _INT,
        "word_count_method": _STR,
        "exclude_footer_from_count": _BOOL,
        "max_subject_chars": _INT,
        "max_paragraphs": _INT,
    },
    "R2.2": {
        "slots": _STRS,
        "problem_precedes_approach": _BOOL,
        "model_may_author_slot_text": _BOOL,
        "max_problem_words": _INT,
    },
    "R2.3": {
        "required_sentence_index": _INT,
        "marker_types": _STRS,
        "marker_must_be_registered": _BOOL,
        "min_markers": _INT,
    },
    "R2.4": {
        "novelty_scale_min": _INT,
        "novelty_scale_max": _INT,
        "min_novelty_score": _FLOAT,
        "max_compose_retries": _INT,
        "route_to_human_after_retries": _BOOL,
    },
    "R2.5": {
        "allowed_ask_types": _STRS,
        "forbid_specific_time_request": _BOOL,
        "forbid_calendar_link_first_touch": _BOOL,
        "forbid_funding_ask": _BOOL,
        "modal_positive_reply": _STR,
        "max_ask_sentences": _INT,
    },
    "R2.6": {
        "max_unsourced_claims": _INT,
        "require_claim_map": _BOOL,
        "min_personalization_hooks": _INT,
        "max_personalization_hooks": _INT,
        "hook_requires_evidence_id": _BOOL,
        "evidence_must_be_stored": _BOOL,
    },
    "R3.1": {
        "max_embedded_images": _INT,
        "max_attachments": _INT,
        "allow_html_part": _BOOL,
        "mime_type": _STR,
        "forbid_tracking_pixel": _BOOL,
    },
    "R3.2": {
        "require_dedicated_domain": _BOOL,
        "forbid_primary_domain": _BOOL,
        "forbid_freemail_senders": _BOOL,
        "freemail_domains": _STRS,
    },
    "R3.3": {
        "steady_state_daily_cap": _INT,
        "warmup_daily_caps": _INTS,
        "warmup_index_basis": _STR,
        "min_seconds_between_sends": _INT,
        "max_consecutive_sends_per_mailbox": _INT,
        "cap_override_allowed": _BOOL,
    },
    "R3.4": {
        "deny_terms": _STRS,
        "max_spam_term_hits": _INT,
        "case_insensitive": _BOOL,
        "max_exclamation_marks": _INT,
        "max_all_caps_words": _INT,
        "max_caps_acronym_length": _INT,
    },
    "R3.5": {
        "max_links_first_touch": _INT,
        "max_links_followup": _INT,
        "forbid_url_shorteners": _BOOL,
    },
    "R3.6": {
        "rolling_window_sends": _INT,
        "min_window_reply_rate": _FLOAT,
        "max_window_bounce_rate": _FLOAT,
        "decline_ratio_vs_baseline": _FLOAT,
        "consecutive_bad_windows_to_alarm": _INT,
        "pause_campaign_on_alarm": _BOOL,
        "require_human_resume": _BOOL,
    },
    "R4.1": {
        "max_followups_per_target": _INT,
        "max_total_touches_per_target": _INT,
        "plan_sequence_at_first_compose": _BOOL,
    },
    "R4.2": {"followup_gap_business_days": _INTS, "min_gap_business_days": _INT},
    "R4.3": {
        "require_new_information": _BOOL,
        "allow_bump_only": _BOOL,
        "allow_update_reuse": _BOOL,
        "generate_without_update": _BOOL,
        "max_update_age_days": _INT,
    },
    "R4.4": {
        "stop_on_any_reply": _BOOL,
        "stop_on_pass": _BOOL,
        "pass_suppression_permanent": _BOOL,
        "pass_suppression_scope": _STR,
        "stop_on_hard_bounce": _BOOL,
        "ooo_reschedules": _BOOL,
        "ooo_reschedule_days": _INT,
    },
    "R4.5": {
        "allowed_weekdays_iso": _INTS,
        "window_start_hour": _INT,
        "window_end_hour": _INT,
        "timezone_basis": _STR,
        "defer_on_unknown_timezone": _BOOL,
    },
    "R5.1": {
        "require_physical_postal_address": _BOOL,
        "require_optout_mechanism": _BOOL,
        "require_accurate_from_header": _BOOL,
        "optout_honored_immediately": _BOOL,
        "footer_exempt_from_word_count": _BOOL,
    },
    "R5.2": {
        "check_before_every_send": _BOOL,
        "check_at_dispatch_time": _BOOL,
        "scopes": _STRS,
        "queue_state_cannot_bypass": _BOOL,
        "approval_cannot_bypass": _BOOL,
    },
    "R5.3": {
        "require_source_on_every_record": _BOOL,
        "require_ingested_at": _BOOL,
        "forbid_authenticated_scraping": _BOOL,
        "forbid_linkedin_contact_scraping": _BOOL,
        "allowed_source_types": _STRS,
    },
    "R6.1": {
        "require_per_email_approval": _BOOL,
        "require_approved_by": _BOOL,
        "require_approved_at": _BOOL,
        "allow_batch_approval": _BOOL,
        "model_may_approve": _BOOL,
        "edit_invalidates_approval": _BOOL,
        "dry_run_exempt": _BOOL,
    },
}

_CHECKERS = {
    _INT: "int_",
    _FLOAT: "float_",
    _BOOL: "bool_",
    _STR: "str_",
    _STRS: "str_list",
    _INTS: "int_list",
}


def validate(book: RuleBook) -> None:
    """Assert the manifest is satisfied, reporting *every* problem in one exception."""
    problems: list[str] = []
    for rule_id, params in REQUIRED_PARAMS.items():
        if rule_id not in book:
            problems.append(f"{rule_id}: rule missing from {book.path or 'rules text'}")
            continue
        for key, kind in params.items():
            try:
                getattr(book, _CHECKERS[kind])(rule_id, key)
            except RuleSpecError as exc:
                problems.append(str(exc))
    for rule in book:
        if not _RULE_ID_RE.match(rule.id):
            problems.append(f"{rule.id}: malformed rule id")
    if problems:
        raise RuleSpecError(
            f"{book.path or 'rules text'} failed validation:\n  - " + "\n  - ".join(problems)
        )


# --------------------------------------------------------------------------------------
# The loaded rulebook and its typed constants
# --------------------------------------------------------------------------------------

RULES: Final[RuleBook] = load_rulebook()

RULES_PATH: Final[Path | None] = RULES.path
SPEC_VERSION: Final[str] = RULES.spec_version
RULES_CHECKSUM: Final[str] = RULES.checksum
RULES_FINGERPRINT: Final[str] = RULES.fingerprint

# §0 — objective function -------------------------------------------------------------
BASELINE_REPLY_RATE: Final[float] = RULES.float_("R0.1", "baseline_reply_rate")
CEILING_REPLY_RATE_LOW: Final[float] = RULES.float_("R0.1", "ceiling_reply_rate_low")
CEILING_REPLY_RATE_HIGH: Final[float] = RULES.float_("R0.1", "ceiling_reply_rate_high")
MIN_SENDS_FOR_RATE_SIGNIFICANCE: Final[int] = RULES.int_("R0.1", "min_sends_for_rate_significance")

# §1 — universe and list construction --------------------------------------------------
MAX_CAMPAIGN_TARGETS: Final[int] = RULES.int_("R1.1", "max_campaign_targets")
WARN_CAMPAIGN_TARGETS: Final[int] = RULES.int_("R1.1", "warn_campaign_targets")

FIT_DIMENSIONS: Final[tuple[str, ...]] = RULES.str_list("R1.2", "dimensions")
SCORE_SCALE_MIN: Final[int] = RULES.int_("R1.2", "score_scale_min")
SCORE_SCALE_MAX: Final[int] = RULES.int_("R1.2", "score_scale_max")
MIN_COMPOSITE_FIT_SCORE: Final[float] = RULES.float_("R1.2", "min_composite_score")
MIN_STAGE_SCORE: Final[int] = RULES.int_("R1.2", "min_stage_score")
MIN_SECTOR_SCORE: Final[int] = RULES.int_("R1.2", "min_sector_score")

# RULE-CHECK (R1.3): the source quantifies effort ("thirty minutes of homework"), not
# snippet counts. We require coverage of all three named areas AND the total floor —
# the stricter reading — rather than either alone.
MIN_EVIDENCE_SNIPPETS: Final[int] = RULES.int_("R1.3", "min_evidence_snippets")
REQUIRED_EVIDENCE_AREAS: Final[tuple[str, ...]] = RULES.str_list("R1.3", "required_evidence_areas")
MIN_SNIPPETS_PER_REQUIRED_AREA: Final[int] = RULES.int_("R1.3", "min_snippets_per_required_area")
EVIDENCE_CACHE_TTL_DAYS: Final[int] = RULES.int_("R1.3", "cache_ttl_days")
MAX_EVIDENCE_AGE_DAYS: Final[int] = RULES.int_("R1.3", "max_evidence_age_days")
RECENT_ACTIVITY_MAX_AGE_DAYS: Final[int] = RULES.int_("R1.3", "recent_activity_max_age_days")

PARTNER_LEVEL_ROLES: Final[tuple[str, ...]] = RULES.str_list("R1.4", "partner_level_roles")
GENERIC_MAILBOX_LOCALS: Final[tuple[str, ...]] = RULES.str_list("R1.4", "generic_mailbox_locals")
FORBID_FIRM_LEVEL_TARGETS: Final[bool] = RULES.bool_("R1.4", "forbid_firm_level_targets")
DEDUPE_KEY: Final[tuple[str, ...]] = RULES.str_list("R1.4", "dedupe_key")

SUPPRESS_DIRECT_CONFLICT: Final[bool] = RULES.bool_("R1.5", "suppress_direct_conflict")
CONFLICT_OVERRIDE_ALLOWED: Final[bool] = RULES.bool_("R1.5", "allow_override")
CONFLICT_OVERRIDE_REQUIRES_HUMAN: Final[bool] = RULES.bool_("R1.5", "override_requires_human")
CONFLICT_OVERRIDE_REQUIRES_REASON: Final[bool] = RULES.bool_("R1.5", "override_requires_reason")
MODEL_MAY_OVERRIDE_CONFLICT: Final[bool] = RULES.bool_("R1.5", "model_may_override")
ENFORCE_CONFLICT_AT_DISPATCH: Final[bool] = RULES.bool_("R1.5", "enforce_at_dispatch")

# §2 — message construction ------------------------------------------------------------
MAX_PITCH_WORDS: Final[int] = RULES.int_("R2.1", "max_words")
WORD_COUNT_METHOD: Final[str] = RULES.str_("R2.1", "word_count_method")
FOOTER_EXEMPT_FROM_WORD_COUNT: Final[bool] = RULES.bool_("R2.1", "exclude_footer_from_count")
MAX_SUBJECT_CHARS: Final[int] = RULES.int_("R2.1", "max_subject_chars")
MAX_PARAGRAPHS: Final[int] = RULES.int_("R2.1", "max_paragraphs")

PITCH_SLOTS: Final[tuple[str, ...]] = RULES.str_list("R2.2", "slots")
PROBLEM_PRECEDES_APPROACH: Final[bool] = RULES.bool_("R2.2", "problem_precedes_approach")
MODEL_MAY_AUTHOR_SLOT_TEXT: Final[bool] = RULES.bool_("R2.2", "model_may_author_slot_text")
MAX_PROBLEM_WORDS: Final[int] = RULES.int_("R2.2", "max_problem_words")

CREDIBILITY_SENTENCE_INDEX: Final[int] = RULES.int_("R2.3", "required_sentence_index")
CREDIBILITY_MARKER_TYPES: Final[tuple[str, ...]] = RULES.str_list("R2.3", "marker_types")
CREDIBILITY_MARKER_MUST_BE_REGISTERED: Final[bool] = RULES.bool_("R2.3", "marker_must_be_registered")
MIN_CREDIBILITY_MARKERS: Final[int] = RULES.int_("R2.3", "min_markers")

NOVELTY_SCALE_MIN: Final[int] = RULES.int_("R2.4", "novelty_scale_min")
NOVELTY_SCALE_MAX: Final[int] = RULES.int_("R2.4", "novelty_scale_max")
# RULE-CHECK (R2.4): the source states the "I've seen ten of these this week" test
# qualitatively and sets no number. 4.0/5 is the stricter reading of "genuinely different".
MIN_NOVELTY_SCORE: Final[float] = RULES.float_("R2.4", "min_novelty_score")
MAX_COMPOSE_RETRIES: Final[int] = RULES.int_("R2.4", "max_compose_retries")

ALLOWED_ASK_TYPES: Final[tuple[str, ...]] = RULES.str_list("R2.5", "allowed_ask_types")
FORBID_SPECIFIC_TIME_REQUEST: Final[bool] = RULES.bool_("R2.5", "forbid_specific_time_request")
FORBID_FUNDING_ASK: Final[bool] = RULES.bool_("R2.5", "forbid_funding_ask")
MODAL_POSITIVE_REPLY: Final[str] = RULES.str_("R2.5", "modal_positive_reply")
MAX_ASK_SENTENCES: Final[int] = RULES.int_("R2.5", "max_ask_sentences")

MAX_UNSOURCED_CLAIMS: Final[int] = RULES.int_("R2.6", "max_unsourced_claims")
REQUIRE_CLAIM_MAP: Final[bool] = RULES.bool_("R2.6", "require_claim_map")
MIN_PERSONALIZATION_HOOKS: Final[int] = RULES.int_("R2.6", "min_personalization_hooks")
MAX_PERSONALIZATION_HOOKS: Final[int] = RULES.int_("R2.6", "max_personalization_hooks")
HOOK_REQUIRES_EVIDENCE_ID: Final[bool] = RULES.bool_("R2.6", "hook_requires_evidence_id")

# §3 — deliverability ------------------------------------------------------------------
MAX_EMBEDDED_IMAGES: Final[int] = RULES.int_("R3.1", "max_embedded_images")
MAX_ATTACHMENTS: Final[int] = RULES.int_("R3.1", "max_attachments")
ALLOW_HTML_PART: Final[bool] = RULES.bool_("R3.1", "allow_html_part")
MIME_TYPE: Final[str] = RULES.str_("R3.1", "mime_type")
FORBID_TRACKING_PIXEL: Final[bool] = RULES.bool_("R3.1", "forbid_tracking_pixel")

REQUIRE_DEDICATED_DOMAIN: Final[bool] = RULES.bool_("R3.2", "require_dedicated_domain")
FORBID_FREEMAIL_SENDERS: Final[bool] = RULES.bool_("R3.2", "forbid_freemail_senders")
FREEMAIL_DOMAINS: Final[tuple[str, ...]] = RULES.str_list("R3.2", "freemail_domains")

STEADY_STATE_DAILY_CAP: Final[int] = RULES.int_("R3.3", "steady_state_daily_cap")
# RULE-CHECK (R3.3): the source establishes deliverability decay at campaign scale but
# publishes no ramp table; this schedule is a conservative standard warmup.
WARMUP_DAILY_CAPS: Final[tuple[int, ...]] = RULES.int_list("R3.3", "warmup_daily_caps")
MIN_SECONDS_BETWEEN_SENDS: Final[int] = RULES.int_("R3.3", "min_seconds_between_sends")
MAX_CONSECUTIVE_SENDS_PER_MAILBOX: Final[int] = RULES.int_("R3.3", "max_consecutive_sends_per_mailbox")
DAILY_CAP_OVERRIDE_ALLOWED: Final[bool] = RULES.bool_("R3.3", "cap_override_allowed")

SPAM_DENY_TERMS: Final[tuple[str, ...]] = RULES.str_list("R3.4", "deny_terms")
MAX_SPAM_TERM_HITS: Final[int] = RULES.int_("R3.4", "max_spam_term_hits")
SPAM_MATCH_CASE_INSENSITIVE: Final[bool] = RULES.bool_("R3.4", "case_insensitive")
MAX_EXCLAMATION_MARKS: Final[int] = RULES.int_("R3.4", "max_exclamation_marks")
MAX_ALL_CAPS_WORDS: Final[int] = RULES.int_("R3.4", "max_all_caps_words")
MAX_CAPS_ACRONYM_LENGTH: Final[int] = RULES.int_("R3.4", "max_caps_acronym_length")

MAX_LINKS_FIRST_TOUCH: Final[int] = RULES.int_("R3.5", "max_links_first_touch")
MAX_LINKS_FOLLOWUP: Final[int] = RULES.int_("R3.5", "max_links_followup")
FORBID_URL_SHORTENERS: Final[bool] = RULES.bool_("R3.5", "forbid_url_shorteners")

ROLLING_WINDOW_SENDS: Final[int] = RULES.int_("R3.6", "rolling_window_sends")
MIN_WINDOW_REPLY_RATE: Final[float] = RULES.float_("R3.6", "min_window_reply_rate")
MAX_WINDOW_BOUNCE_RATE: Final[float] = RULES.float_("R3.6", "max_window_bounce_rate")
DECLINE_RATIO_VS_BASELINE: Final[float] = RULES.float_("R3.6", "decline_ratio_vs_baseline")
CONSECUTIVE_BAD_WINDOWS_TO_ALARM: Final[int] = RULES.int_("R3.6", "consecutive_bad_windows_to_alarm")
PAUSE_CAMPAIGN_ON_ALARM: Final[bool] = RULES.bool_("R3.6", "pause_campaign_on_alarm")

# §4 — cadence -------------------------------------------------------------------------
# RULE-CHECK (R4.1): the source says "don't send one email and give up" without naming a
# touch count; two follow-ups is the stricter reading.
MAX_FOLLOWUPS_PER_TARGET: Final[int] = RULES.int_("R4.1", "max_followups_per_target")
MAX_TOTAL_TOUCHES_PER_TARGET: Final[int] = RULES.int_("R4.1", "max_total_touches_per_target")

FOLLOWUP_GAP_BUSINESS_DAYS: Final[tuple[int, ...]] = RULES.int_list("R4.2", "followup_gap_business_days")
MIN_GAP_BUSINESS_DAYS: Final[int] = RULES.int_("R4.2", "min_gap_business_days")

REQUIRE_NEW_INFORMATION: Final[bool] = RULES.bool_("R4.3", "require_new_information")
ALLOW_BUMP_ONLY_FOLLOWUP: Final[bool] = RULES.bool_("R4.3", "allow_bump_only")
ALLOW_UPDATE_REUSE: Final[bool] = RULES.bool_("R4.3", "allow_update_reuse")
GENERATE_FOLLOWUP_WITHOUT_UPDATE: Final[bool] = RULES.bool_("R4.3", "generate_without_update")
MAX_UPDATE_AGE_DAYS: Final[int] = RULES.int_("R4.3", "max_update_age_days")

STOP_ON_ANY_REPLY: Final[bool] = RULES.bool_("R4.4", "stop_on_any_reply")
PASS_SUPPRESSION_PERMANENT: Final[bool] = RULES.bool_("R4.4", "pass_suppression_permanent")
PASS_SUPPRESSION_SCOPE: Final[str] = RULES.str_("R4.4", "pass_suppression_scope")
OOO_RESCHEDULE_DAYS: Final[int] = RULES.int_("R4.4", "ooo_reschedule_days")

ALLOWED_SEND_WEEKDAYS_ISO: Final[tuple[int, ...]] = RULES.int_list("R4.5", "allowed_weekdays_iso")
SEND_WINDOW_START_HOUR: Final[int] = RULES.int_("R4.5", "window_start_hour")
SEND_WINDOW_END_HOUR: Final[int] = RULES.int_("R4.5", "window_end_hour")
SEND_TIMEZONE_BASIS: Final[str] = RULES.str_("R4.5", "timezone_basis")
# RULE-CHECK (R4.5): the source asserts "timing and deliverability are real" without a
# window. Deferring on unknown recipient timezone is the stricter reading of a guess.
DEFER_ON_UNKNOWN_TIMEZONE: Final[bool] = RULES.bool_("R4.5", "defer_on_unknown_timezone")

# §5 — legal ---------------------------------------------------------------------------
REQUIRE_PHYSICAL_POSTAL_ADDRESS: Final[bool] = RULES.bool_("R5.1", "require_physical_postal_address")
REQUIRE_OPTOUT_MECHANISM: Final[bool] = RULES.bool_("R5.1", "require_optout_mechanism")
OPTOUT_HONORED_IMMEDIATELY: Final[bool] = RULES.bool_("R5.1", "optout_honored_immediately")

CHECK_SUPPRESSION_BEFORE_EVERY_SEND: Final[bool] = RULES.bool_("R5.2", "check_before_every_send")
CHECK_SUPPRESSION_AT_DISPATCH: Final[bool] = RULES.bool_("R5.2", "check_at_dispatch_time")
SUPPRESSION_SCOPES: Final[tuple[str, ...]] = RULES.str_list("R5.2", "scopes")
APPROVAL_CANNOT_BYPASS_SUPPRESSION: Final[bool] = RULES.bool_("R5.2", "approval_cannot_bypass")

REQUIRE_SOURCE_ON_EVERY_RECORD: Final[bool] = RULES.bool_("R5.3", "require_source_on_every_record")
FORBID_AUTHENTICATED_SCRAPING: Final[bool] = RULES.bool_("R5.3", "forbid_authenticated_scraping")
FORBID_LINKEDIN_CONTACT_SCRAPING: Final[bool] = RULES.bool_("R5.3", "forbid_linkedin_contact_scraping")
ALLOWED_SOURCE_TYPES: Final[tuple[str, ...]] = RULES.str_list("R5.3", "allowed_source_types")

# §6 — human in the loop ---------------------------------------------------------------
REQUIRE_PER_EMAIL_APPROVAL: Final[bool] = RULES.bool_("R6.1", "require_per_email_approval")
REQUIRE_APPROVED_BY: Final[bool] = RULES.bool_("R6.1", "require_approved_by")
REQUIRE_APPROVED_AT: Final[bool] = RULES.bool_("R6.1", "require_approved_at")
ALLOW_BATCH_APPROVAL: Final[bool] = RULES.bool_("R6.1", "allow_batch_approval")
MODEL_MAY_APPROVE: Final[bool] = RULES.bool_("R6.1", "model_may_approve")
EDIT_INVALIDATES_APPROVAL: Final[bool] = RULES.bool_("R6.1", "edit_invalidates_approval")
DRY_RUN_EXEMPT_FROM_APPROVAL: Final[bool] = RULES.bool_("R6.1", "dry_run_exempt")


# --------------------------------------------------------------------------------------
# Small derived helpers — rule semantics, kept next to the rules they read
# --------------------------------------------------------------------------------------


def is_partner_level(role: str | None) -> bool:
    """R1.4 — is this role inside the campaign universe?"""
    if not role:
        return False
    return role.strip().lower().replace(" ", "_").replace("-", "_") in PARTNER_LEVEL_ROLES


def is_generic_mailbox(email: str | None) -> bool:
    """R1.4 — reject shared inboxes; targets are named individuals."""
    if not email or "@" not in email:
        return True
    local = email.split("@", 1)[0].strip().lower()
    local = re.split(r"[+.]", local)[0]
    return local in GENERIC_MAILBOX_LOCALS


def is_freemail_sender(email: str | None) -> bool:
    """R3.2 — sending identities live on the dedicated domain, never a free provider."""
    if not email or "@" not in email:
        return True
    return email.rsplit("@", 1)[1].strip().lower() in FREEMAIL_DOMAINS


def daily_cap_for_mailbox_age(age_days: int) -> int:
    """R3.3 — warmup ramp indexed by mailbox age; clamps to the steady-state ceiling."""
    if age_days < 0:
        raise ValueError("mailbox age cannot be negative")
    if age_days < len(WARMUP_DAILY_CAPS):
        return min(WARMUP_DAILY_CAPS[age_days], STEADY_STATE_DAILY_CAP)
    return STEADY_STATE_DAILY_CAP


def max_links_for_touch(touch_number: int) -> int:
    """R3.5 — touch 1 carries no links at all; later touches at most one."""
    if touch_number < 1:
        raise ValueError("touch numbers start at 1")
    return MAX_LINKS_FIRST_TOUCH if touch_number == 1 else MAX_LINKS_FOLLOWUP


def is_within_send_window(local_dt: datetime) -> bool:
    """R4.5 — Tue–Thu, 07:00–10:00, in the *recipient's* local time.

    The caller is responsible for converting to recipient-local time; passing a naive or
    sender-local datetime is a caller bug, not something this function can detect.
    """
    if local_dt.isoweekday() not in ALLOWED_SEND_WEEKDAYS_ISO:
        return False
    return SEND_WINDOW_START_HOUR <= local_dt.hour < SEND_WINDOW_END_HOUR
