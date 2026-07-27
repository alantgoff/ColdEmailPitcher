"""Module 4 — pitch and sequence generation.

Slot filling, not free generation. The founder writes the copy; the model chooses which
variant fits this investor and writes exactly one personalization hook (R2.2, R2.6). That
keeps the hallucination surface to a single sentence and makes A/B tests meaningful,
because two drafts differ by a known variant key rather than by model temperature.
"""

from pitchline.compose.library import (
    VariantLibraryError,
    active_variants,
    seed_default_library,
    variants_payload,
)
from pitchline.compose.pitch import (
    ComposeError,
    HumanFixRequired,
    compose_first_touch,
    render_body,
)
from pitchline.compose.sequence import (
    NoUnusedUpdateError,
    end_sequence,
    generate_followup,
    plan_sequence,
    due_followups,
)

__all__ = [
    "VariantLibraryError",
    "active_variants",
    "seed_default_library",
    "variants_payload",
    "ComposeError",
    "HumanFixRequired",
    "compose_first_touch",
    "render_body",
    "NoUnusedUpdateError",
    "end_sequence",
    "generate_followup",
    "plan_sequence",
    "due_followups",
]
