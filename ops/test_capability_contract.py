"""Capability contracts: enforceable, and honest about being enforced.

The value of this module is not that it describes good work — descriptions are
free. It is that it refuses work whose pre-flight is unsigned, refuses a
signature with no evidence, and names the task types ACE routes but has not
contracted. These tests pin those refusals, because a contract that accepts
anything is decoration.

The five bans are each seeded by a defect ACE actually hit on 2026-10-11/12:
    repeat-selection      <- inquiry pipeline asked objections[0] three times
    unattributed absorption <- _ledger_close hid unregistered counter changes
    backlog starvation    <- external reviewer stopped with 63 tasks unseen
    filler as content     <- a degenerate AMD reply filed as a review
    unsupported support   <- every unblinded reviewer assertion
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from core.capability_contract import (  # noqa: E402
    ALL_BANS,
    CONTRACTS,
    Bans,
    CapabilityContract,
    Dials,
    audit_preflight,
    contract_for_task,
    list_contracted_types,
    sign_preflight,
    ungoverned_task_types,
    violations,
)


# ---------------------------------------------------------------- the roster

def test_every_routable_task_type_has_a_contract():
    """A routable capability with no contract is the hole this module closes."""
    assert ungoverned_task_types() == [], (
        "task types the pool can route but ACE has not contracted: "
        f"{ungoverned_task_types()}"
    )
    assert len(list_contracted_types()) >= 13


def test_contracts_expose_the_shape_a_reader_needs():
    for task_type in list_contracted_types():
        contract = contract_for_task(task_type)
        assert contract.summary.strip()
        assert contract.preflight, f"{task_type} has no pre-flight"
        assert contract.side_effects.strip()
        dials = contract.dials.snapshot()
        for axis, value in dials.items():
            assert 1 <= value <= 10, f"{task_type}.{axis} is {value}"


@pytest.mark.parametrize("axis,value", [
    ("autonomy", 11), ("evidence_rigour", 11), ("blast_radius", 11),
    ("autonomy", 0), ("evidence_rigour", -1), ("blast_radius", 99),
])
def test_a_dial_outside_its_range_is_refused_not_clamped(axis, value):
    """A typo must not quietly weaken a gate, so the range is enforced."""
    fields = {"autonomy": 5, "evidence_rigour": 5, "blast_radius": 5}
    fields[axis] = value
    with pytest.raises(ValueError, match=f"dial {axis} must be 1-10"):
        Dials(**fields)


def test_blast_radius_tracks_how_far_a_mistake_reaches():
    """Execution and coding touch the runtime, so they carry the largest radius.

    The dial exists so that reading a contract tells you how much damage a wrong
    answer does without reading the implementation.
    """
    radii = {t: contract_for_task(t).dials.blast_radius
             for t in ("execution", "coding", "strategic", "free_exploration")}
    assert radii["execution"] > radii["free_exploration"]
    assert radii["coding"] > radii["free_exploration"]
    assert radii["execution"] >= 8


def test_cross_validation_demands_the_highest_evidence_rigour():
    """Independence is the product of that task, so its evidence dial is the max."""
    best = max(
        (contract_for_task(t).dials.evidence_rigour for t in list_contracted_types()),
    )
    assert contract_for_task("cross_validation").dials.evidence_rigour == best


# --------------------------------------------------------------------- bans

def test_every_contract_enforces_all_five_bans():
    """The bans are seeded by real defects, not per-task preferences.

    A task type that may weaken one is a task type that may reintroduce the
    defect the ban names, so the bans are not negotiable per contract.
    """
    for task_type in list_contracted_types():
        assert violations(contract_for_task(task_type)) == [
            "no_repeat_selection_without_new_input",
            "no_unattributed_absorption",
            "no_starve_the_backlog",
            "no_filler_as_content",
            "no_unsupported_support",
        ], task_type


def test_ban_names_correspond_to_real_defects():
    """A ban nobody can trace to a failure is decoration. These are traceable."""
    traced = {
        "no_repeat_selection_without_new_input": "inquiry_pipeline objections[0]",
        "no_unattributed_absorption": "task.py _ledger_close absorb",
        "no_starve_the_backlog": "external_reviewer NO_TASK_WAITING",
        "no_filler_as_content": "degenerate AMD reply filed as review",
        "no_unsupported_support": "unblinded reviewer assertion",
    }
    assert set(traced) == {
        name for name in ALL_BANS.__dataclass_fields__ if getattr(ALL_BANS, name)
    }


# --------------------------------------------------------------- pre-flight

def test_a_preflight_signature_requires_evidence_not_a_claim():
    contract = contract_for_task("cross_validation")
    with pytest.raises(ValueError, match="requires evidence, not a claim"):
        sign_preflight(contract, contract.preflight[0], "   ", "reviewer")
    with pytest.raises(ValueError, match="requires an actor"):
        sign_preflight(contract, contract.preflight[0], "read the diff", "  ")


def test_a_signature_for_an_item_not_in_the_contract_is_refused():
    contract = contract_for_task("cross_validation")
    with pytest.raises(ValueError, match="is not in this contract"):
        sign_preflight(contract, "I felt good about it", "vibes", "reviewer")


def test_an_incomplete_preflight_names_the_missing_items():
    contract = contract_for_task("cross_validation")
    signed = sign_preflight(
        contract, contract.preflight[0],
        "compared opencoder vs deepseek output", "main_steward",
    )
    verdict = audit_preflight(contract, [signed])
    assert verdict["complete"] is False
    assert verdict["missing"] == list(contract.preflight[1:])
    assert verdict["required"] == list(contract.preflight)


def test_a_complete_preflight_is_complete_by_arithmetic_not_judgement():
    contract = contract_for_task("free_exploration")
    signatures = [
        sign_preflight(contract, item, f"verified at line {i}", "operator")
        for i, item in enumerate(contract.preflight)
    ]
    verdict = audit_preflight(contract, signatures)
    assert verdict["complete"] is True
    assert verdict["missing"] == []


def test_a_falsified_signature_cannot_pass_as_a_real_one():
    """An unsigned or evidence-free entry is ignored, not counted.

    This is what separates a checklist from a claim: an item is covered only by
    a real signature, so padding the set with noise cannot complete a preflight.
    """
    contract = contract_for_task("free_exploration")
    good = sign_preflight(
        contract, contract.preflight[0], "seat specs pinned in source", "operator"
    )
    verdict = audit_preflight(contract, [
        good,
        {"item": contract.preflight[1], "evidence": "   ", "actor": "ghost"},
        {"item": "an item this contract does not list", "evidence": "x", "actor": "ghost"},
        "not even a mapping",
    ])
    assert verdict["signed"] == [contract.preflight[0]]
    assert verdict["missing"] == list(contract.preflight[1:])
    assert verdict["complete"] is False
    assert set(verdict["extras"]) == {"an item this contract does not list"}


# ----------------------------------------------------------- read-only shape

def test_a_contract_grants_no_authority_of_its_own():
    """Satisfying a contract is necessary for good work, never sufficient.

    A contract that carried an approval flag, a promotion right, or an admission
    bypass would be a second gate. Its fields are read-only descriptions.
    """
    forbidden = {
        "approved", "promote", "authority", "grant", "bypass",
        "admission", "execute", "create_task", "promotion",
    }
    for task_type in list_contracted_types():
        contract = contract_for_task(task_type)
        assert not (forbidden & set(contract.__dataclass_fields__)), (
            f"{task_type} carries an authority-shaped field"
        )
        assert contract.dials.autonomy <= 10


def test_adding_a_new_task_type_is_a_detectable_gap(monkeypatch):
    """A routable capability nobody contracted must show up as a hole."""
    from core.miner_pool import task_profiles

    monkeypatch.setattr(task_profiles, "list_task_types",
                        lambda: list(CONTRACTS) + ["brand_new_capability"])
    assert ungoverned_task_types() == ["brand_new_capability"]


def test_contract_module_does_not_import_the_pool():
    """No import cycle: the contract describes, it never routes or executes."""
    import core.capability_contract as module

    source = open(module.__file__, encoding="utf-8").read()
    assert "from .miner_pool.miner_pool" not in source
    assert "MinerPool(" not in source
    assert "pool.chat(" not in source