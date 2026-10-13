"""Capability contracts: the executable part of "how this work is done".

Purpose
-------
ACE already knows which models may serve a task type, and how many tokens they
may spend. It has never had a place that says what *doing that task well* means,
in a form a machine can check before the work lands.

``core/miner_pool/task_profiles.py`` answers "who may serve this task".
This module answers "what does a satisfactory attempt look like, and what is
forbidden regardless of outcome". The profile decides the route; the contract
decides whether the attempt was honest.

Stolen, deliberately and with attribution — what taste-skill
(Leonxlnx/taste-skill, MIT) got right, and why its form transfers even though
its content is frontend and therefore useless here:

  * **Named dials instead of taste.** It splits "make it look good" into
    DESIGN_VARIANCE / MOTION_INTENSITY / VISUAL_DENSITY, each 1-10. The insight
    is that an unmeasurable quality can become enforceable once it is split into
    a few dials with declared defaults. ACE's equivalent axes are autonomy,
    evidence rigour, and blast radius — a task is characterised by how much it
    may decide alone, how hard its evidence must be, and how far a mistake
    reaches.
  * **Hard bans over preferences.** It carries an explicit em-dash ban and a
    pre-flight that must pass honestly or nothing ships. A preference is
    advice; a ban is a gate. This module's bans are the defects ACE actually
    hit, not hypothetical ones.
  * **Pre-flight as checklist, not description.** "I verified it" is a claim;
    a checklist item that must be signed is evidence. Every contract's
    ``preflight`` is machine-checkable, and a missing signature is a refusal.

What is deliberately NOT here: no scheduler, no router, no second TaskPool, no
prompt text. A contract describes and constrains; it never executes. It is read
by the free-zone stages and by verify tooling, and by nothing that grants
authority — satisfying a contract is necessary for good work, never sufficient
to promote it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

CONTRACT_VERSION = "ace.capability_contract.v1"

#: Minimum number of independent evidence groups before work that claims
#: external corroboration may be considered corroborated at all. Two, because
#: one group is always ACE agreeing with itself.
MIN_INDEPENDENT_GROUPS = 2


@dataclass(frozen=True)
class Bans:
    """Hard prohibitions. Each one exists because ACE hit the real defect.

    A ban is not a preference: a checklist item can be satisfied by a
    well-written excuse, and a dial can be argued either way. A ban cannot.
    """

    #: Banned when a gate/selection step may return the same answer repeatedly
    #: while the record shows it deliberated. Seeded by the inquiry pipeline
    #: defect: _generate_question returned objections[0] on every round, so
    #: round 2 and 3 were verbatim copies of round 1.
    no_repeat_selection_without_new_input: bool = False

    #: Banned when one write path silently registers another operation's
    #: unregistered changes as its own. Seeded by _ledger_close absorbing every
    #: outstanding counter delta into the transition's consume row, which made
    #: the write-port drift gate unreachable.
    no_unattributed_absorption: bool = False

    #: Banned when a sweep stops because its newest candidates are done while
    #: older work remains. Seeded by the external reviewer reporting
    #: NO_TASK_WAITING with 63 tasks unreviewed.
    no_starve_the_backlog: bool = False

    #: Banned when a seat that returned failure-shaped output is recorded as a
    #: successful attempt. Seeded by the degenerate AMD reply filed as a review.
    no_filler_as_content: bool = False

    #: Banned when a claim is reported as supported by evidence the record does
    #: not actually contain. Seeded by every unblinded reviewer assertion.
    no_unsupported_support: bool = False


@dataclass(frozen=True)
class Dials:
    """Three named axes, 1-10, each with a declared floor and ceiling.

    The point of a declared range rather than a single number is that moving a
    dial is a decision someone can review. A value outside its range is refused
    rather than silently clamped, so a typo cannot quietly weaken a gate.
    """

    autonomy: int
    evidence_rigour: int
    blast_radius: int

    def __post_init__(self) -> None:
        for name, value in (("autonomy", self.autonomy),
                            ("evidence_rigour", self.evidence_rigour),
                            ("blast_radius", self.blast_radius)):
            if not 1 <= int(value) <= 10:
                raise ValueError(f"dial {name} must be 1-10, got {value}")

    def snapshot(self) -> dict[str, int]:
        return {
            "autonomy": self.autonomy,
            "evidence_rigour": self.evidence_rigour,
            "blast_radius": self.blast_radius,
        }


@dataclass(frozen=True)
class CapabilityContract:
    """One task type's executable contract."""

    task_type: str
    summary: str
    dials: Dials
    bans: Bans = field(default_factory=Bans)
    #: Pre-flight items. Every one must be signed truthfully or the work does
    #: not land. Each is a short imperative a reviewer can answer yes/no to.
    preflight: tuple[str, ...] = ()
    #: What this capability must never do, in plain words, for the human reader.
    side_effects: str = ""
    contract_version: str = CONTRACT_VERSION

    def validate_dials(self) -> None:
        self.dials.__post_init__()


#: The roster. One entry per task type in task_profiles, so a task type without
#: a contract is a detectable gap rather than a silent one. Ordering is stable
#: for readable diffs.
CONTRACTS: dict[str, CapabilityContract] = {}


def _register(contract: CapabilityContract) -> CapabilityContract:
    CONTRACTS[contract.task_type] = contract
    return contract


def contract_for_task(task_type: str) -> CapabilityContract | None:
    """The contract for a task type, or None when ACE has no opinion yet."""
    return CONTRACTS.get(str(task_type).strip())


def list_contracted_types() -> list[str]:
    return sorted(CONTRACTS)


# --------------------------------------------------------------------------
# Escalation bands. Where a dial sits decides whether failure escalates or the
# attempt is simply retried. Bands are read by the free-zone stages; nothing
# here routes work.
# --------------------------------------------------------------------------

HIGH_AUTONOMY = Dials(autonomy=8, evidence_rigour=4, blast_radius=2)
LOW_AUTONOMY = Dials(autonomy=3, evidence_rigour=6, blast_radius=3)
EVIDENCE_FIRST = Dials(autonomy=4, evidence_rigour=9, blast_radius=5)
CONTAINED = Dials(autonomy=6, evidence_rigour=5, blast_radius=1)

ALL_BANS = Bans(
    no_repeat_selection_without_new_input=True,
    no_unattributed_absorption=True,
    no_starve_the_backlog=True,
    no_filler_as_content=True,
    no_unsupported_support=True,
)

_register(CapabilityContract(
    task_type="free_exploration",
    summary="Open-ended probing where the answer is unknown and may be 'I do not know'.",
    dials=Dials(autonomy=7, evidence_rigour=3, blast_radius=1),
    bans=ALL_BANS,
    preflight=(
        "the question is stated before any seat speaks",
        "every seat is pinned and cannot fall through to a paid provider",
        "a seat that answered nothing is recorded as unavailable, not as a view",
        "no seat's claim is stored as a finding about ACE",
    ),
    side_effects="none; output is sandbox material only",
))

_register(CapabilityContract(
    task_type="hypothesis_generation",
    summary="Produce candidate explanations for an observed fact.",
    dials=Dials(autonomy=7, evidence_rigour=4, blast_radius=2),
    bans=ALL_BANS,
    preflight=(
        "the observation being explained is quoted, not paraphrased from memory",
        "each candidate is labelled as a hypothesis, never as a cause",
        "at least one candidate the model cannot assess is retained",
    ),
    side_effects="none; candidates enter the existing Candidate path, not the TaskPool",
))

_register(CapabilityContract(
    task_type="cross_validation",
    summary="Independent re-derivation of a claim by a reader who did not produce it.",
    dials=Dials(autonomy=4, evidence_rigour=9, blast_radius=4),
    bans=ALL_BANS,
    preflight=(
        "the reader is a different model on an unrelated provider from the claim's author",
        "the reader is given the evidence as stored, not the conclusion",
        "the reader's verdict is one of supported/contradicted/cannot_assess",
        "a cannot_assess outcome is kept as a finding, not discarded",
    ),
    side_effects="none; an independent read is a never a production fact",
))

_register(CapabilityContract(
    task_type="reasoning",
    summary="Structured inference from stated premises toward a checkable step.",
    dials=Dials(autonomy=5, evidence_rigour=7, blast_radius=3),
    bans=ALL_BANS,
    preflight=(
        "every premise used is quoted from the record",
        "the inference states which premise would have to be false to break it",
        "no premise is supplied by the model itself",
    ),
    side_effects="read-only over the task record",
))

_register(CapabilityContract(
    task_type="synthesis",
    summary="Merge several independent reads into one map of agreement and dispute.",
    dials=Dials(autonomy=5, evidence_rigour=7, blast_radius=3),
    bans=ALL_BANS,
    preflight=(
        "each contributor's position is preserved, not averaged away",
        "disagreements are named rather than resolved by majority",
        "the synthesis does not claim agreement the contributors did not state",
    ),
    side_effects="none; a synthesis is a reading of the transcript",
))

_register(CapabilityContract(
    task_type="classification",
    summary="Assign a record to a declared category with a stated basis.",
    dials=Dials(autonomy=3, evidence_rigour=6, blast_radius=4),
    bans=ALL_BANS,
    preflight=(
        "the category list is declared before the assignment",
        "the basis for the assignment is recorded next to it",
        "an unclassifiable record is marked so rather than forced into a bucket",
    ),
    side_effects="may set a label; never changes lifecycle state by itself",
))

_register(CapabilityContract(
    task_type="extraction",
    summary="Pull a specific value from a record without interpreting it.",
    dials=Dials(autonomy=2, evidence_rigour=8, blast_radius=2),
    bans=ALL_BANS,
    preflight=(
        "the extracted value is quoted verbatim with its source location",
        "an absent value is reported as absent, never inferred",
        "no value is carried over from a similar record",
    ),
    side_effects="none",
))

_register(CapabilityContract(
    task_type="fast_response",
    summary="Cheap first pass whose answer may be revised by a later stage.",
    dials=Dials(autonomy=3, evidence_rigour=2, blast_radius=1),
    bans=ALL_BANS,
    preflight=(
        "the response is marked provisional",
        "no downstream stage consumes it as final",
    ),
    side_effects="none",
))

_register(CapabilityContract(
    task_type="strategic",
    summary="Decide direction, including whether to proceed at all.",
    dials=Dials(autonomy=8, evidence_rigour=6, blast_radius=7),
    bans=ALL_BANS,
    preflight=(
        "the decision names what would make it wrong",
        "a decision that cannot be reviewed by anyone but its author is refused",
        "no decision grants authority it was not given",
        "the record states which gates remain in force afterwards",
    ),
    side_effects="advisory; execution still requires the existing gates",
))

_register(CapabilityContract(
    task_type="execution",
    summary="Carry out an already-approved change to the runtime.",
    dials=Dials(autonomy=6, evidence_rigour=5, blast_radius=9),
    bans=ALL_BANS,
    preflight=(
        "the approval that authorises this change is cited by id",
        "the change is reversible or its rollback is stated",
        "no unrelated change is bundled in",
        "the failure semantics are preserved: a refused step stays refused",
    ),
    side_effects="mutates runtime state; requires the existing approval gate",
))

_register(CapabilityContract(
    task_type="coding",
    summary="Write or modify code against a stated requirement.",
    dials=Dials(autonomy=6, evidence_rigour=5, blast_radius=8),
    bans=ALL_BANS,
    preflight=(
        "the requirement is quoted before the code is written",
        "a test that fails without the change is named",
        "no test is weakened or deleted to make the change pass",
        "the diff contains only what the requirement asked for",
    ),
    side_effects="mutates the workspace; requires the existing gates",
))

_register(CapabilityContract(
    task_type="grok_research_shadow",
    summary="Shadow research whose output is compared against another reader.",
    dials=Dials(autonomy=4, evidence_rigour=7, blast_radius=1),
    bans=ALL_BANS,
    preflight=(
        "shadow_only is honoured; no result reaches the task record uncompared",
        "the comparison is against an independent reader's output",
    ),
    side_effects="none; shadow mode never writes to the primary record",
))

_register(CapabilityContract(
    task_type="grok_coding_shadow",
    summary="Shadow code generation whose output is compared against another writer.",
    dials=Dials(autonomy=4, evidence_rigour=6, blast_radius=2),
    bans=ALL_BANS,
    preflight=(
        "shadow_only is honoured; no code reaches the workspace uncompared",
        "the comparison is against an independent writer's output",
    ),
    side_effects="none; shadow mode never writes to the workspace",
))


# --------------------------------------------------------------------------
# Enforcement: a preflight is signed, or the work does not land.
# --------------------------------------------------------------------------

def sign_preflight(contract: CapabilityContract, item_text: str,
                   evidence: str, actor: str) -> dict[str, Any]:
    """One signed preflight item.

    An empty ``evidence`` string is refused. That single rule is the whole point
    of the mechanism: "I checked" is a claim, and a signed item with no evidence
    is exactly the unverifiable self-attestation the contracts exist to refuse.
    """
    item = str(item_text).strip()
    basis = str(evidence).strip()
    if not item:
        raise ValueError("preflight item must be non-empty")
    if not basis:
        raise ValueError("a preflight signature requires evidence, not a claim")
    if item not in set(contract.preflight):
        raise ValueError(f"preflight item is not in this contract: {item[:60]}")
    if not str(actor).strip():
        raise ValueError("preflight signature requires an actor")
    return {
        "item": item,
        "evidence": basis[:500],
        "actor": str(actor).strip(),
        "contract_version": contract.contract_version,
        "task_type": contract.task_type,
    }


def audit_preflight(contract: CapabilityContract,
                    signatures: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Check a sign-off set against the contract. Returns a verdict plus gaps.

    ``complete`` is not a judgement — it is arithmetic. An item is covered only
    when a real signature names it, so a missing signature surfaces as a named
    gap rather than as a lower score.
    """
    required = list(contract.preflight)
    signed: dict[str, dict[str, Any]] = {}
    extras: set[str] = set()
    for entry in signatures or []:
        if not isinstance(entry, Mapping):
            continue
        item = str(entry.get("item", "")).strip()
        # A signature with no evidence is ignored rather than counted: a forged
        # signature and a real one must not produce the same verdict.
        if not item or not str(entry.get("evidence", "")).strip():
            continue
        if item not in set(required):
            # Kept as an extra so a sign-off aimed at the wrong contract is
            # visible, rather than silently vanishing into the same bucket.
            extras.add(item)
            continue
        signed[item] = dict(entry)

    missing = [item for item in required if item not in signed]
    return {
        "contract_version": contract.contract_version,
        "task_type": contract.task_type,
        "required": required,
        "signed": sorted(signed),
        "missing": missing,
        "extras": sorted(extras),
        "complete": not missing,
        "dials": contract.dials.snapshot(),
    }


def violations(contract: CapabilityContract) -> list[str]:
    """The bans this contract enforces, as human-readable names."""
    active = [
        name for name in (
            "no_repeat_selection_without_new_input",
            "no_unattributed_absorption",
            "no_starve_the_backlog",
            "no_filler_as_content",
            "no_unsupported_support",
        )
        if getattr(contract.bans, name)
    ]
    return active


def ungoverned_task_types() -> list[str]:
    """Task types the pool can route but ACE has no contract for.

    A gap here is detectable, not silent: a routable capability with no declared
    expectations is exactly the hole this module exists to close. This is the
    check that keeps the roster honest as task types are added.
    """
    from .miner_pool.task_profiles import list_task_types

    routable = {str(t).strip() for t in list_task_types()}
    contracted = set(CONTRACTS)
    return sorted(routable - contracted)


__all__ = [
    "CONTRACT_VERSION",
    "MIN_INDEPENDENT_GROUPS",
    "Bans",
    "Dials",
    "CapabilityContract",
    "CONTRACTS",
    "contract_for_task",
    "list_contracted_types",
    "sign_preflight",
    "audit_preflight",
    "violations",
    "ungoverned_task_types",
]