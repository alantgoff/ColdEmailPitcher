"""Phase 0 gate: the rules file parses into typed constants, and refuses to half-load."""

from __future__ import annotations

import pytest

from pitchline import rules
from pitchline.rules import (
    RuleParamError,
    RuleSpecError,
    Severity,
    load_rulebook,
    parse_rules_text,
)

MINIMAL = """
```meta
spec_version = "9.9.9"
```

## §1 — Section one

### R1.1 — A rule

- **Severity:** hard
- **Enforced by:** targeting.campaign_cap
- **Source:** "quoted passage"

Prose about the rule.

```params
max_campaign_targets = 400
warn_campaign_targets = 250
flag = true
ratio = 0.5
name = "value"
list_of_ints = [1, 2, 3]
list_of_strs = ["a", "b"]
```
"""


def test_the_shipped_rules_file_parses():
    book = load_rulebook()
    assert len(book) >= 20
    assert book.spec_version
    assert all(rule.source for rule in book), "every rule cites its source passage"
    assert all(rule.enforced_by for rule in book), "every rule names its enforcing module"


def test_constants_are_typed_and_match_the_file():
    assert isinstance(rules.MAX_PITCH_WORDS, int) and rules.MAX_PITCH_WORDS == 150
    assert isinstance(rules.MAX_CAMPAIGN_TARGETS, int) and rules.MAX_CAMPAIGN_TARGETS == 400
    assert isinstance(rules.WARN_CAMPAIGN_TARGETS, int) and rules.WARN_CAMPAIGN_TARGETS == 250
    assert isinstance(rules.STEADY_STATE_DAILY_CAP, int) and rules.STEADY_STATE_DAILY_CAP == 40
    assert isinstance(rules.BASELINE_REPLY_RATE, float) and rules.BASELINE_REPLY_RATE == 0.04
    assert (rules.CEILING_REPLY_RATE_LOW, rules.CEILING_REPLY_RATE_HIGH) == (0.13, 0.17)
    assert isinstance(rules.SPAM_DENY_TERMS, tuple) and len(rules.SPAM_DENY_TERMS) > 20
    assert rules.ALLOWED_SEND_WEEKDAYS_ISO == (2, 3, 4)  # Tue-Thu
    assert (rules.SEND_WINDOW_START_HOUR, rules.SEND_WINDOW_END_HOUR) == (7, 10)
    assert rules.MAX_EMBEDDED_IMAGES == 0
    assert rules.MAX_LINKS_FIRST_TOUCH == 0
    assert rules.MAX_UNSOURCED_CLAIMS == 0


def test_every_referenced_rule_id_exists():
    for rule_id in rules.REQUIRED_PARAMS:
        assert rule_id in rules.RULES, f"{rule_id} referenced by code but missing from the file"


def test_parser_handles_every_value_type():
    book = parse_rules_text(MINIMAL)
    rule = book["R1.1"]
    assert rule.severity is Severity.HARD
    assert rule.enforced_by == ("targeting.campaign_cap",)
    assert book.int_("R1.1", "max_campaign_targets") == 400
    assert book.bool_("R1.1", "flag") is True
    assert book.float_("R1.1", "ratio") == 0.5
    assert book.str_("R1.1", "name") == "value"
    assert book.int_list("R1.1", "list_of_ints") == (1, 2, 3)
    assert book.str_list("R1.1", "list_of_strs") == ("a", "b")


def test_a_bool_is_not_an_int():
    """`true` where a count belongs is a spec bug, not a 1."""
    book = parse_rules_text(MINIMAL)
    with pytest.raises(RuleParamError):
        book.int_("R1.1", "flag")


def test_missing_required_param_fails_validation_loudly():
    broken = MINIMAL.replace("warn_campaign_targets = 250\n", "")
    book = parse_rules_text(broken)
    with pytest.raises(RuleSpecError) as exc:
        rules.validate(book)
    assert "warn_campaign_targets" in str(exc.value)


def test_validation_reports_every_problem_at_once():
    book = parse_rules_text(MINIMAL)
    with pytest.raises(RuleSpecError) as exc:
        rules.validate(book)
    message = str(exc.value)
    assert message.count("\n  - ") > 5, "one exception should list every missing rule"


def test_a_rule_without_a_source_is_rejected():
    no_source = MINIMAL.replace('- **Source:** "quoted passage"\n', "")
    with pytest.raises(RuleSpecError, match="Source"):
        parse_rules_text(no_source)


def test_a_missing_rules_file_is_fatal(tmp_path):
    with pytest.raises(RuleSpecError, match="refuses to run without it"):
        load_rulebook(tmp_path / "nope.md")


def test_open_rule_checks_are_discoverable():
    """Where we took the stricter reading, the author can find it."""
    checks = rules.RULES.rule_checks()
    assert checks, "expected RULE-CHECK notes where the source is silent"
    assert all(rule_id in rules.RULES for rule_id, _ in checks)


def test_fingerprint_changes_with_the_file():
    a = parse_rules_text(MINIMAL)
    b = parse_rules_text(MINIMAL.replace("max_campaign_targets = 400", "max_campaign_targets = 300"))
    assert a.fingerprint != b.fingerprint


def test_derived_helpers_read_the_rules():
    assert rules.is_partner_level("general_partner") is True
    assert rules.is_partner_level("associate") is False
    assert rules.is_generic_mailbox("info@fund.vc") is True
    assert rules.is_generic_mailbox("ana.okafor@fund.vc") is False
    assert rules.is_freemail_sender("someone@gmail.com") is True
    assert rules.daily_cap_for_mailbox_age(0) == rules.WARMUP_DAILY_CAPS[0]
    assert rules.daily_cap_for_mailbox_age(999) == rules.STEADY_STATE_DAILY_CAP
    assert rules.max_links_for_touch(1) == 0
    assert rules.max_links_for_touch(2) == rules.MAX_LINKS_FOLLOWUP
