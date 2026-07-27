"""Module 5 — the hard gate every draft passes before it can reach a human.

A draft that fails returns *structured* reasons (code, rule id, observed vs allowed) so
compose can act on them mechanically rather than re-prompting and hoping.
"""

from pitchline.guardrails.linters import (
    GuardrailError,
    GuardrailFailure,
    LintReport,
    lint_draft,
    assert_passes,
)

__all__ = ["GuardrailError", "GuardrailFailure", "LintReport", "lint_draft", "assert_passes"]
