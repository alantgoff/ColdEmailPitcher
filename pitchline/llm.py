"""LLM access layer: versioned prompts, forced-structured output, two clients.

Two clients implement the same protocol:

``AnthropicClient``
    The real thing. Forces a tool call whose input schema *is* the Pydantic schema, so a
    malformed response is a validation error rather than a parsing adventure.

``HeuristicClient``
    A deterministic offline implementation of every prompt key. It exists so the whole
    pipeline — targeting, composition, novelty scoring, reply classification — runs and is
    testable without an API key or a cent of spend, in the same spirit as Scout's hard caps
    on external API cost. It is the default when ``ANTHROPIC_API_KEY`` is unset.

Both stamp ``model`` and ``prompt_version`` onto whatever they produce, so every generated
row is traceable (see ``LLMProvenanceMixin``).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from pitchline import textutil as tu
from pitchline.schemas import (
    DimensionScore,
    FitScoreResult,
    HookProposal,
    NoveltyVerdict,
    ReplyClassification,
    VariantSelection,
)

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = os.environ.get("PITCHLINE_MODEL", "claude-sonnet-5")
OFFLINE_MODEL_NAME = "heuristic-offline-v1"


class LLMError(RuntimeError):
    """The model could not be made to produce a valid structured response."""


# --------------------------------------------------------------------------------------
# Versioned prompt objects
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Prompt:
    key: str
    version: str
    system: str
    template: str

    @property
    def qualified(self) -> str:
        return f"{self.key}@{self.version}"

    @property
    def template_hash(self) -> str:
        return hashlib.sha256((self.system + self.template).encode("utf-8")).hexdigest()[:16]

    def render(self, variables: Mapping[str, Any]) -> str:
        payload = json.dumps(variables, indent=2, default=str, ensure_ascii=False)
        return f"{self.template}\n\n<input>\n{payload}\n</input>"


PROMPTS: dict[str, Prompt] = {
    "fit_score_v1": Prompt(
        key="fit_score_v1",
        version="1.0.0",
        system=(
            "You are a VC associate triaging whether a specific investor is a real fit for a "
            "specific startup. You are rigorous and unflattering: a mediocre fit is a 2, not a 4. "
            "You cite evidence ids for every claim and never assert a fact that is not in the "
            "supplied evidence."
        ),
        template=(
            "Score the investor against the startup on six dimensions, 0-5 each:\n"
            "stage, sector, check_size, geography, thesis_recency, portfolio_conflict.\n\n"
            "portfolio_conflict is scored 5 when the fund holds nothing competitive and 0 when it "
            "holds a direct competitor; list any competing portfolio companies in "
            "conflict_companies.\n\n"
            "Each dimension needs a one-line rationale and the evidence_ids that support it. "
            "If no evidence supports a dimension, score it low and say so — do not infer."
        ),
    ),
    "novelty_v1": Prompt(
        key="novelty_v1",
        # 1.1.0: the offline scorer changed from cliche-phrase matching to measuring
        # genericness directly. Scores from 1.0.0 are not comparable, and a draft's
        # prompt_version is how you tell which scorer cleared it.
        version="1.1.0",
        system=(
            "You are a general partner at a seed fund reading the 400th cold pitch of the month. "
            "You are impatient and pattern-matching."
        ),
        template=(
            "Score this cold email 0-5 on the question: would you think 'I've seen ten of these "
            "this week'?\n\n"
            "0 = indistinguishable from every other pitch in the inbox.\n"
            "5 = a genuinely specific problem framing and a non-obvious approach.\n\n"
            "Penalise vague category language, borrowed positioning ('X for Y'), and claims with "
            "no concrete detail. Reward a specific problem, a specific mechanism, and numbers. "
            "List the exact cliche phrases you saw."
        ),
    ),
    "hook_v1": Prompt(
        key="hook_v1",
        version="1.0.0",
        system=(
            "You write one sentence connecting a specific investor's public activity to a startup. "
            "You never state anything the supplied evidence does not support."
        ),
        template=(
            "Choose the single strongest evidence snippet and write ONE sentence referencing it, "
            "under 30 words, no flattery, no links. Return the evidence_id you used. If nothing "
            "supports a specific, non-generic sentence, pick the closest snippet and keep the "
            "sentence narrow."
        ),
    ),
    "variant_select_v1": Prompt(
        key="variant_select_v1",
        version="1.0.0",
        system=(
            "You select from a founder's pre-written pitch components. You never write new copy; "
            "you only choose which existing variant best matches this investor."
        ),
        template=(
            "Pick exactly one variant key for each slot (credibility, problem, approach, ask) "
            "given the investor's stage, sector and thesis. Return the keys verbatim."
        ),
    ),
    "reply_classify_v1": Prompt(
        key="reply_classify_v1",
        version="1.0.0",
        system="You classify replies to cold investor outreach. You are conservative.",
        template=(
            "Classify the reply as exactly one of: interested, deck_request, not_now, pass, "
            "auto_reply, ooo, bounce, unsubscribe, unknown.\n\n"
            "deck_request: they asked for the deck or more materials.\n"
            "interested: they want to talk but did not specifically ask for the deck.\n"
            "not_now: door open, wrong time or wrong stage today.\n"
            "pass: a decline. Treat any clear no as a pass.\n"
            "unsubscribe: they asked not to be contacted again.\n"
            "ooo: automatic out-of-office.\n"
            "auto_reply: any other automated acknowledgement.\n"
            "bounce: a delivery failure notice."
        ),
    ),
}


def prompt_for(key: str) -> Prompt:
    try:
        return PROMPTS[key]
    except KeyError:
        raise LLMError(f"unknown prompt key {key!r}") from None


# --------------------------------------------------------------------------------------
# Client protocol
# --------------------------------------------------------------------------------------


class LLMClient(Protocol):
    name: str
    model: str

    def run(self, prompt_key: str, schema: type[T], variables: Mapping[str, Any]) -> T: ...


def _stamp(prompt_key: str) -> str:
    return prompt_for(prompt_key).qualified


# --------------------------------------------------------------------------------------
# Anthropic client
# --------------------------------------------------------------------------------------


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Dereference ``$defs``/``$ref`` so the schema is a single self-contained object."""
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node and node["$ref"].startswith("#/$defs/"):
                target = defs[node["$ref"].split("/")[-1]]
                merged = {k: v for k, v in node.items() if k != "$ref"}
                return {**walk(json.loads(json.dumps(target))), **merged}
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


class AnthropicClient:
    """Structured output via forced tool use."""

    name = "anthropic"

    def __init__(self, model: str | None = None, *, max_retries: int = 2) -> None:
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on install extras
            raise LLMError(
                "the anthropic SDK is not installed; run `pip install anthropic` or set "
                "PITCHLINE_LLM=offline"
            ) from exc
        self._sdk = anthropic
        self._client = anthropic.Anthropic()
        self.model = model or DEFAULT_MODEL
        self._max_retries = max_retries

    def run(self, prompt_key: str, schema: type[T], variables: Mapping[str, Any]) -> T:
        prompt = prompt_for(prompt_key)
        tool = {
            "name": "emit_result",
            "description": f"Return the {schema.__name__} result.",
            "input_schema": _inline_refs(schema.model_json_schema()),
        }
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            message = self._client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=prompt.system,
                tools=[tool],
                tool_choice={"type": "tool", "name": "emit_result"},
                messages=[{"role": "user", "content": prompt.render(variables)}],
            )
            for block in message.content:
                if getattr(block, "type", None) == "tool_use":
                    try:
                        return schema.model_validate(block.input)
                    except ValidationError as exc:
                        last_error = exc
                        break
            else:
                last_error = LLMError("model returned no tool_use block")
        raise LLMError(f"{prompt.qualified}: no valid response after retries: {last_error}")


# --------------------------------------------------------------------------------------
# Offline heuristic client
# --------------------------------------------------------------------------------------

_STAGE_ORDER = ["pre_seed", "seed", "series_a", "series_b", "growth"]

_CLICHES = (
    "ai-powered", "ai powered", "revolutionary", "revolutionize", "revolutionise",
    "disrupt", "disruptive", "game-changing", "game changing", "next-generation",
    "next generation", "one-stop shop", "cutting-edge", "cutting edge",
    "state-of-the-art", "world-class", "best-in-class", "paradigm shift", "synergy",
    "seamless", "supercharge", "holistic", "turnkey", "frictionless", "unlock value",
    "the uber for", "the airbnb for", "end-to-end platform", "leading provider",
)

#: Abstraction that says nothing. The source's complaint is "generic, vague, or
#: derivative" — cliches cover derivative, these cover generic and vague.
_VAGUE_TERMS = (
    "solutions", "innovative", "the future of", "technology company", "great restaurants",
    "modern consumer", "combined experience", "connects", "connecting", "empowering",
    "leading provider", "best in class", "next level", "robust", "value-add", "synergies",
    "wide range of", "high quality", "customer-centric", "data-driven approach",
    "passionate about", "our platform", "we are building the future", "transforming the way",
    "reimagining", "at scale", "seamlessly", "unparalleled", "cutting edge",
)
#: A number that carries a unit or timeframe. Bare digits are not specificity — but the
#: unit does not always sit flush against the number ("30 finance hours a month", "1 in 5
#: sites"), and requiring adjacency made the detector miss real figures and fail good
#: drafts. Up to two words may intervene.
_UNITS = (
    r"days?|hours?|minutes?|weeks?|months?|years?|sites?|stores?|locations?|customers?|"
    r"orders?|visits?|patients?|trials?|brands?|partners?|people|staff|cities|corridors?|"
    r"restaurants?|kitchens?|units?|nights?|deliveries|meals?|am|pm"
)
_QUANTIFIED_RE = re.compile(
    r"(?i)("
    r"\$\s?\d[\d,.]*\s?[kmb]?"                      # $2.1M
    r"|\d[\d,.]*\s?%"                                 # 7.5%
    r"|\b\d[\d,.]*\s+in\s+\d+\b"                    # 1 in 5
    r"|\b\d[\d,.]*\s+(?:\w+\s+){0,2}(?:" + _UNITS + r")\b"   # 30 finance hours
    # A rate: any number followed shortly by "a month" / "per week". Catches phrasings the
    # unit list will never enumerate ("34 delivery nights a month").
    r"|\b\d[\d,.]*\b(?=[^.]{0,32}?\b(?:a|per)\s+(?:day|week|month|quarter|year|night|hour)\b)"
    r"|\b\d{1,2}[:.]?\d{0,2}\s?(?:am|pm)\b"           # 4:30AM
    r")"
)
#: "the Uber for X" — borrowed positioning.
_BORROWED_RE = re.compile(
    r"(?i)\b(uber|airbnb|stripe|shopify|netflix|amazon|tesla)\s+(for|of)\s+\w+"
)


def _named_entities(text: str) -> list[str]:
    """Capitalised words that are not sentence-openers — a proxy for concrete names."""
    found: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        words = sentence.split()
        for word in words[1:]:
            stripped = word.strip(".,;:!?\"'()")
            if len(stripped) > 2 and stripped[0].isupper() and not stripped.isupper():
                found.append(stripped)
    return sorted(set(found))


_BOUNCE_RE = re.compile(
    r"(?i)(delivery status notification|undeliverable|mail delivery (failed|subsystem)|"
    r"address not found|user unknown|550[ -]5\.|recipient address rejected|"
    r"message could not be delivered)"
)
_OOO_RE = re.compile(
    r"(?i)(out of (the )?office|on (annual |parental )?leave|away from my desk|"
    r"currently travel(l)?ing|on vacation|auto(matic)?[- ]?reply.*(back|return)|"
    r"i am away|limited access to email)"
)
_AUTO_RE = re.compile(
    r"(?i)(this is an automated|do not reply to this|no-?reply@|we have received your|"
    r"your message has been received|ticket #\d+)"
)
_UNSUB_RE = re.compile(
    r"(?i)(unsubscribe|remove me from|take me off (your|this) list|stop emailing me|"
    r"do not (contact|email) me( again)?|opt me out)"
)
_DECK_RE = re.compile(
    r"(?i)(send (me |over |through )?(the |your |a )?(deck|deck\?|pitch deck|materials|"
    r"one[- ]pager|overview)|share (the |your )?deck|happy to (take a )?look at (the |your )?deck|"
    r"can you (send|share).*(deck|more info|materials)|do you have a deck)"
)
_INTEREST_RE = re.compile(
    r"(?i)(happy to (chat|talk|connect)|let'?s (set up|schedule|find)|"
    r"would love to (chat|learn more|hear more)|are you free|book (some )?time|"
    r"(sounds|this is) interesting|keen to learn more|when (are|is) (you|a) good time)"
)
_PASS_RE = re.compile(
    r"(?i)(we'?ll pass|going to pass|not a fit|isn'?t a fit|not for us|"
    r"outside (of )?(our|my) (thesis|focus|scope|mandate)|we don'?t invest in|"
    r"unfortunately.*(no|not)|afraid (this |it )?(is|isn'?t)|will have to decline|"
    r"not something (we|i) (do|invest)|no thanks|not interested)"
)
_NOT_NOW_RE = re.compile(
    r"(?i)(too early (for us|right now)|circle back|keep me posted|keep us posted|"
    r"reach out (again )?(when|once|after)|revisit (this )?(in|next|when)|"
    r"we'?re (currently )?(between funds|not deploying)|check back|later stage|"
    r"come back to (us|me) (when|once|after))"
)


class HeuristicClient:
    """Deterministic stand-in for every prompt key. No network, no spend, no randomness."""

    name = "offline"

    def __init__(self, model: str = OFFLINE_MODEL_NAME) -> None:
        self.model = model

    def run(self, prompt_key: str, schema: type[T], variables: Mapping[str, Any]) -> T:
        handler = {
            "fit_score_v1": self._fit_score,
            "novelty_v1": self._novelty,
            "hook_v1": self._hook,
            "variant_select_v1": self._variant_select,
            "reply_classify_v1": self._classify_reply,
        }.get(prompt_key)
        if handler is None:
            raise LLMError(f"offline client has no implementation for {prompt_key!r}")
        result = handler(dict(variables))
        if not isinstance(result, schema):
            raise LLMError(
                f"{prompt_key}: offline handler returned {type(result).__name__}, "
                f"expected {schema.__name__}"
            )
        return result

    # -- fit scoring (R1.2 / R1.5) ------------------------------------------------------

    def _fit_score(self, v: dict[str, Any]) -> FitScoreResult:
        profile: dict[str, Any] = v.get("profile", {})
        investor: dict[str, Any] = v.get("investor", {})
        evidence: list[dict[str, Any]] = v.get("evidence", [])

        by_area: dict[str, list[dict[str, Any]]] = {}
        for snippet in evidence:
            by_area.setdefault(snippet.get("area", "other"), []).append(snippet)

        def ids(*areas: str) -> list[int]:
            out: list[int] = []
            for area in areas:
                out.extend(int(s["id"]) for s in by_area.get(area, []) if s.get("id"))
            return out[:4]

        # stage
        inv_stages = {s.lower() for s in investor.get("stages") or []}
        target_stage = (profile.get("stage") or "").lower()
        if not inv_stages:
            stage_score, stage_why = 2, "no stated stage focus on record; scored as unknown"
        elif target_stage in inv_stages:
            stage_score, stage_why = 5, f"invests at {target_stage.replace('_', ' ')}"
        elif _stage_adjacent(target_stage, inv_stages):
            stage_score, stage_why = 3, f"adjacent stage focus ({', '.join(sorted(inv_stages))})"
        else:
            stage_score, stage_why = 0, f"stage focus is {', '.join(sorted(inv_stages))}"

        # sector
        profile_tokens = tu.tokens(
            " ".join(
                [*profile.get("sectors", []), *profile.get("keywords", []), profile.get("one_liner", "")]
            )
        )
        investor_tokens = tu.tokens(
            " ".join(
                [
                    *investor.get("sectors", []),
                    investor.get("thesis_summary") or "",
                    " ".join(s.get("raw_text", "")[:400] for s in evidence[:8]),
                ]
            )
        )
        # Score on the NUMBER of distinct sector concepts that match, not on the fraction of
        # the startup's vocabulary that matches. A ratio with the profile's token count in
        # the denominator punishes a founder for describing their space thoroughly: add ten
        # more accurate keywords and every investor's score falls. Counting matches is
        # stable against the length of either list.
        sector_tokens = {
            t for t in tu.tokens(" ".join(profile.get("sectors", []) + profile.get("keywords", [])))
            if len(t) > 3
        }
        matched_all = sorted(t for t in sector_tokens if t in investor_tokens)
        sector_score = _bucket(float(len(matched_all)), (1.0, 2.0, 3.0, 5.0, 7.0))
        matched = matched_all[:4]
        sector_why = (
            f"thesis and evidence mention {', '.join(matched)}" if matched
            else "no sector overlap found in stated thesis or evidence"
        )

        # check size
        check_score, check_why = _check_size_fit(profile, investor)

        # geography
        geo_score, geo_why = _geography_fit(profile, investor)

        # thesis recency
        recency_score, recency_why, recency_ids = _recency(evidence)

        # portfolio conflict (R1.5)
        conflicts, conflict_ids = _detect_conflicts(profile, investor, evidence)
        if conflicts:
            conflict_score = 0
            conflict_why = f"holds direct competitor(s): {', '.join(conflicts)}"
        else:
            conflict_score = 5
            conflict_why = "no competing portfolio company found in evidence"

        return FitScoreResult(
            stage=DimensionScore(score=stage_score, rationale=stage_why, evidence_ids=ids("thesis")),
            sector=DimensionScore(
                score=sector_score, rationale=sector_why, evidence_ids=ids("thesis", "portfolio")
            ),
            check_size=DimensionScore(score=check_score, rationale=check_why, evidence_ids=ids("thesis")),
            geography=DimensionScore(score=geo_score, rationale=geo_why, evidence_ids=[]),
            thesis_recency=DimensionScore(
                score=recency_score, rationale=recency_why, evidence_ids=recency_ids
            ),
            portfolio_conflict=DimensionScore(
                score=conflict_score, rationale=conflict_why, evidence_ids=conflict_ids
            ),
            conflict_companies=conflicts,
            summary=f"composite fit for {investor.get('full_name', 'investor')}",
        )

    # -- novelty (R2.4) -----------------------------------------------------------------

    def _novelty(self, v: dict[str, Any]) -> NoveltyVerdict:
        """R2.4 — "would a VC think 'I've seen ten of these this week'?"

        The first version of this scored cliche PHRASES and nothing else, so a pitch with
        no cliches and no content ("we are a technology company building innovative
        solutions") scored a perfect 5. That is precisely the email the source says gets
        ignored, and the gate waved it through — a gate that never fires on the failure
        mode it was built for.

        This scores genericness directly: concrete facts earn, abstraction costs.
        """
        subject, body = v.get("subject", "") or "", v.get("body", "") or ""
        text = f"{subject}\n{body}"
        lowered = text.lower()

        cliches = [c for c in _CLICHES if c in lowered]
        vague = [t for t in _VAGUE_TERMS if t in lowered]

        # A quantified fact is a number that carries a unit or a timeframe. A bare "2" is
        # not evidence of specificity; "87 days" and "7.5% year over year" are.
        quantified = _QUANTIFIED_RE.findall(text)
        # Named entities: capitalised words that are not sentence-openers.
        named = _named_entities(text)

        # Calibration note: the source frames this as what's WRONG with a pitch — "generic,
        # vague, or derivative pitches got ignored" — so the penalties carry the signal and
        # the base sits near the pass mark. An earlier version started low and made a draft
        # earn its way up, which failed genuinely specific copy that happened to contain
        # only one figure.
        score = 4.2
        score += min(0.8, 0.25 * len({q[0] for q in quantified}))
        score += min(0.5, 0.15 * len(named))
        score -= 0.9 * len(cliches)
        score -= 0.7 * len(vague)
        if not quantified:
            score -= 1.4
        if _BORROWED_RE.search(text):
            score -= 0.8
        if v.get("has_personalization_hook"):
            score += 0.3
        score = max(0.0, min(5.0, round(score, 2)))

        bits = []
        if quantified:
            bits.append(f"{len(quantified)} quantified claim(s)")
        else:
            bits.append("no quantified claim")
        if named:
            bits.append(f"{len(named)} named entity/entities")
        if cliches:
            bits.append(f"{len(cliches)} cliche(s)")
        if vague:
            bits.append(f"{len(vague)} vague phrase(s): {', '.join(vague[:3])}")
        return NoveltyVerdict(
            score=score,
            reason="; ".join(bits),
            cliches=(cliches + vague)[:8],
            resembles=("a generic category pitch" if score < 2.5 else ""),
        )

    # -- personalization hook (R2.6) ----------------------------------------------------

    def _hook(self, v: dict[str, Any]) -> HookProposal:
        """One sentence, quoting stored evidence verbatim so the citation resolves."""
        evidence: list[dict[str, Any]] = v.get("evidence", [])
        if not evidence:
            raise LLMError("no evidence available to build a personalization hook")
        profile = v.get("profile", {})
        profile_tokens = {
            t
            for t in tu.tokens(" ".join(profile.get("sectors", []) + profile.get("keywords", [])))
            if len(t) > 3
        }

        def rank(snippet: dict[str, Any]) -> tuple[float, str]:
            text_tokens = tu.tokens((snippet.get("raw_text") or "")[:800])
            area_bonus = {"thesis": 0.25, "recent_activity": 0.2, "portfolio": 0.1}.get(
                snippet.get("area", ""), 0.0
            )
            return (
                round(tu.overlap_ratio(profile_tokens, text_tokens) + area_bonus, 4),
                str(snippet.get("published_at") or snippet.get("fetched_at") or ""),
            )

        best = max(evidence, key=rank)
        area = best.get("area", "other")
        entities = [str(e).strip() for e in (best.get("entities") or []) if str(e).strip()]

        if entities:
            # Name the company. Concrete and checkable — the whole point of R2.6.
            entity = min(
                entities,
                key=lambda name: (-tu.overlap_ratio(tu.tokens(name), profile_tokens), name),
            )
            verb = "recent investment in" if area == "recent_activity" else "investment in"
            hook = (
                f"Your {verb} {entity} is why I am writing to you specifically rather than "
                "mass-mailing a list."
            )
        else:
            fragment = _salient_fragment(best.get("raw_text") or "", profile_tokens)
            if not fragment:
                raise LLMError("evidence snippet has no quotable content for a hook")
            # Only quote someone if the snippet is actually THEIR words. A directory entry
            # or a research summary is a third party describing the fund, and framing it as
            # "your stated thesis — '...'" attributes a sentence they never wrote. In a
            # system whose whole claim is verifiable sourcing, that framing is the lie even
            # when the citation resolves.
            first_party = best.get("source") in {"fund_site", "public_writing", "sec_form_d"}
            if first_party:
                lead = {
                    "thesis": "Your stated thesis",
                    "recent_activity": "Your recent note",
                }.get(area, "Your public writing")
                hook = (
                    f'{lead} — "{fragment}" — is why I am writing to you rather than '
                    "mass-mailing."
                )
            else:
                # Third-party descriptions are written ABOUT the fund ("Chicago venture firm
                # investing in restaurant and beverage companies"), so splicing them after
                # "you focus on" produces nonsense. Pull the object of the investing verb,
                # which is the part that is true of them in the second person.
                focus = _focus_phrase(fragment)
                hook = (
                    f"You back {focus}, which is why I am writing to you rather than "
                    "mass-mailing a list."
                )

        return HookProposal(
            hook_text=hook[:300],
            evidence_id=int(best["id"]),
            rationale=f"strongest token overlap with the startup's sector language ({area})",
        )

    # -- variant selection (R2.2) -------------------------------------------------------

    def _variant_select(self, v: dict[str, Any]) -> VariantSelection:
        investor = v.get("investor", {})
        variants: dict[str, list[dict[str, Any]]] = v.get("variants", {})
        investor_tokens = tu.tokens(
            " ".join([*investor.get("sectors", []), investor.get("thesis_summary") or ""])
        )
        investor_stages = {s.lower() for s in investor.get("stages") or []}
        # Stable per-investor assignment: deterministic across runs, but spread across the
        # list rather than collapsing every draft onto the alphabetically-first variant.
        # Without this, "reply rate by variant" would only ever have one arm.
        seed = int(
            hashlib.sha256(
                f"{investor.get('full_name', '')}|{investor.get('firm', '')}".encode("utf-8")
            ).hexdigest()[:8],
            16,
        )

        def pick(slot: str) -> str:
            options = variants.get(slot) or []
            if not options:
                raise LLMError(f"no active pitch variants for slot {slot!r}")

            def score(option: dict[str, Any]) -> float:
                tags = tu.tokens(" ".join(option.get("sectors", [])))
                stage_bonus = 0.5 if investor_stages & {s.lower() for s in option.get("stages", [])} else 0.0
                return round(tu.overlap_ratio(tags, investor_tokens) + stage_bonus, 4)

            best = max(score(option) for option in options)
            tied = sorted((o for o in options if score(o) == best), key=lambda o: o["key"])
            return tied[seed % len(tied)]["key"]

        return VariantSelection(
            credibility_key=pick("credibility"),
            problem_key=pick("problem"),
            approach_key=pick("approach"),
            ask_key=pick("ask"),
            rationale="selected by sector-tag overlap with the investor's stated thesis",
        )

    # -- reply classification (module 7) ------------------------------------------------

    def _classify_reply(self, v: dict[str, Any]) -> ReplyClassification:
        subject = v.get("subject", "") or ""
        body = v.get("body", "") or ""
        blob = f"{subject}\n{body}"
        # Order matters: a bounce that quotes the original email would otherwise match
        # whatever the original said.
        for label, pattern, confidence in (
            ("bounce", _BOUNCE_RE, 0.97),
            ("unsubscribe", _UNSUB_RE, 0.95),
            ("ooo", _OOO_RE, 0.9),
            ("deck_request", _DECK_RE, 0.88),
            ("pass", _PASS_RE, 0.85),
            ("not_now", _NOT_NOW_RE, 0.8),
            ("interested", _INTEREST_RE, 0.8),
            ("auto_reply", _AUTO_RE, 0.75),
        ):
            match = pattern.search(blob)
            if match:
                return ReplyClassification(
                    label=label,  # type: ignore[arg-type]
                    confidence=confidence,
                    reason=f"matched {label} pattern: {match.group(0)[:80]!r}",
                )
        return ReplyClassification(
            label="unknown", confidence=0.3, reason="no classifier pattern matched"
        )


# --------------------------------------------------------------------------------------
# Heuristic helpers
# --------------------------------------------------------------------------------------


def _salient_fragment(text: str, profile_tokens: set[str], *, max_words: int = 16) -> str:
    """The clause of an evidence snippet closest to what the startup does.

    Quoted verbatim into the hook, so the sentence in the email is literally the stored
    evidence — which is what makes the R2.6 citation meaningful rather than decorative.
    URLs are stripped: a first touch carries no links (R3.5).
    """
    cleaned = re.sub(r"\S+://\S+|\bwww\.\S+", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    sentences = tu.split_sentences(cleaned) or [cleaned]
    best = max(sentences, key=lambda s: tu.overlap_ratio(profile_tokens, tu.tokens(s)))
    words = best.split()
    # Trim a leading throat-clear so the quote starts on content.
    for opener in ("we ", "our ", "i ", "wrote about ", "posted ", "published ", "podcast "):
        if best.lower().startswith(opener):
            words = best.split()[len(opener.split()):]
            break
    fragment = " ".join(words[:max_words]).strip()
    # A quote cut mid-clause reads as careless and can change the meaning. If the sentence
    # was truncated, fall back to the last clean clause boundary rather than shipping
    # "...companies across North America, founded by".
    if len(words) > max_words:
        for boundary in (",", ";", ":"):
            if boundary in fragment:
                fragment = fragment.rsplit(boundary, 1)[0]
                break
    fragment = fragment.strip().strip(",;:. ")
    # Never end on a word that promises more.
    dangling = {"and", "or", "with", "for", "by", "of", "the", "a", "an", "in", "to", "that",
                "founded", "including", "across", "from", "at", "on"}
    parts = fragment.split()
    while parts and parts[-1].lower().strip(",.;:") in dangling:
        parts.pop()
    return " ".join(parts)


_FOCUS_RE = re.compile(
    r"(?i)\b(?:investing in|invests in|invest in|backs|backing|focused on|focus on|"
    r"partners with|supports)\s+(?P<object>.+)$"
)


def _focus_phrase(fragment: str) -> str:
    """The part of a third-party description that is true of the fund in second person."""
    match = _FOCUS_RE.search(fragment)
    phrase = match.group("object") if match else fragment
    # Drop a leading article so "You back the restaurant sector" reads naturally.
    phrase = re.sub(r"(?i)^(the|a|an)\s+", "", phrase).strip().strip(",;:. ")
    return phrase


def _bucket(value: float, thresholds: tuple[float, ...]) -> int:
    score = 0
    for threshold in thresholds:
        if value >= threshold:
            score += 1
    return min(score, 5)


def _stage_adjacent(stage: str, others: set[str]) -> bool:
    if stage not in _STAGE_ORDER:
        return False
    index = _STAGE_ORDER.index(stage)
    neighbours = {
        _STAGE_ORDER[i] for i in (index - 1, index + 1) if 0 <= i < len(_STAGE_ORDER)
    }
    return bool(neighbours & others)


def _check_size_fit(profile: dict[str, Any], investor: dict[str, Any]) -> tuple[int, str]:
    lo, hi = investor.get("check_size_min_usd"), investor.get("check_size_max_usd")
    want_lo, want_hi = profile.get("target_check_min_usd"), profile.get("target_check_max_usd")
    if lo is None and hi is None:
        return 2, "no published check size; scored as unknown"
    if want_lo is None and want_hi is None:
        return 3, "startup has no target check band set"
    lo = lo if lo is not None else 0.0
    hi = hi if hi is not None else float("inf")
    want_lo = want_lo if want_lo is not None else 0.0
    want_hi = want_hi if want_hi is not None else float("inf")
    if want_lo >= lo and want_hi <= hi:
        return 5, f"target check sits inside their {_usd(lo)}-{_usd(hi)} band"
    if max(lo, want_lo) <= min(hi, want_hi):
        return 3, f"partial overlap with their {_usd(lo)}-{_usd(hi)} band"
    return 0, f"target check is outside their {_usd(lo)}-{_usd(hi)} band"


def _geography_fit(profile: dict[str, Any], investor: dict[str, Any]) -> tuple[int, str]:
    want = (profile.get("geography") or "").strip().lower()
    have = " ".join(
        str(x).lower() for x in (investor.get("country"), investor.get("city")) if x
    ).strip()
    if not want or not have:
        return 3, "geography not stated on one side; scored as neutral"
    if want in have or have in want:
        return 5, f"both in {want}"
    if tu.tokens(want) & tu.tokens(have):
        return 4, f"partial geography match ({have})"
    return 1, f"investor is in {have}, startup in {want}"


def _recency(evidence: list[dict[str, Any]]) -> tuple[int, str, list[int]]:
    dated = [
        (_parse_dt(s.get("published_at") or s.get("fetched_at")), s)
        for s in evidence
        if s.get("published_at") or s.get("fetched_at")
    ]
    dated = [(d, s) for d, s in dated if d is not None]
    if not dated:
        return 1, "no dated evidence on file", []
    newest_dt, newest = max(dated, key=lambda pair: pair[0])
    age_days = (datetime.now(timezone.utc) - newest_dt).days
    if age_days <= 90:
        score = 5
    elif age_days <= 180:
        score = 4
    elif age_days <= 365:
        score = 3
    elif age_days <= 730:
        score = 2
    else:
        score = 1
    ids = [int(newest["id"])] if newest.get("id") else []
    return score, f"most recent public activity is {age_days} days old", ids


def _detect_conflicts(
    profile: dict[str, Any], investor: dict[str, Any], evidence: list[dict[str, Any]]
) -> tuple[list[str], list[int]]:
    """R1.5 — match the startup's named competitors against portfolio evidence."""
    competitors = [c.strip() for c in profile.get("competitors", []) if c and c.strip()]
    if not competitors:
        return [], []
    haystacks: list[tuple[str, int | None]] = [
        (" ".join(investor.get("portfolio_companies") or []), None)
    ]
    for snippet in evidence:
        # Recent-activity evidence counts as portfolio evidence for conflict purposes.
        # A fund's stake in a competitor is at least as likely to be phrased "led Wonder's
        # $700M round" in a news write-up as it is to appear in a tidy portfolio list, and
        # scanning only the tidy list let exactly that case through: Forerunner Ventures
        # backs Wonder, a named competitor, and R1.5 did not see it.
        if snippet.get("area") in {"portfolio", "recent_activity"} or snippet.get("kind") in {
            "portfolio_company",
            "investment",
        }:
            haystacks.append(
                (f"{snippet.get('title', '')} {snippet.get('raw_text', '')}", snippet.get("id"))
            )
            for entity in snippet.get("entities") or []:
                haystacks.append((str(entity), snippet.get("id")))

    found: list[str] = []
    ids: list[int] = []
    for competitor in competitors:
        # Case-SENSITIVE on purpose. Competitor names are proper nouns and appear
        # capitalised in portfolio data, while plenty of real company names are also
        # ordinary English words ("Wonder", "Salted", "Prime"). Matching case-insensitively
        # would suppress good investors because a blog post contained the word "wonder" —
        # and a silent false suppression is far harder to notice than a missed conflict,
        # because the target simply never appears in the list.
        pattern = re.compile(rf"(?<![\w-]){re.escape(competitor)}(?![\w-])")
        for text, eid in haystacks:
            if text and pattern.search(text):
                if competitor not in found:
                    found.append(competitor)
                if eid is not None and int(eid) not in ids:
                    ids.append(int(eid))
                break
    return found, ids[:4]


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _usd(value: float) -> str:
    if value in (0.0, float("inf")):
        return "any"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M".replace(".0M", "M")
    return f"${value / 1000:.0f}k"


# --------------------------------------------------------------------------------------
# Client selection
# --------------------------------------------------------------------------------------

_client: LLMClient | None = None


def get_client(force: str | None = None) -> LLMClient:
    """Return the configured client.

    ``PITCHLINE_LLM=anthropic|offline`` decides explicitly; otherwise the Anthropic client
    is used when ``ANTHROPIC_API_KEY`` is present and the offline client when it is not.
    Defaulting to offline is deliberate: an unconfigured install must never burn spend or
    silently produce different drafts than the test suite saw.
    """
    global _client
    mode = force or os.environ.get("PITCHLINE_LLM")
    if mode == "offline":
        return HeuristicClient()
    if mode == "anthropic":
        return AnthropicClient()
    if _client is None:
        _client = AnthropicClient() if os.environ.get("ANTHROPIC_API_KEY") else HeuristicClient()
    return _client


def set_client(client: LLMClient | None) -> None:
    """Test seam and CLI override."""
    global _client
    _client = client


def stamp(client: LLMClient, prompt_key: str) -> dict[str, str]:
    """Provenance fields for any row a model produced."""
    return {"model": client.model, "prompt_version": _stamp(prompt_key)}
