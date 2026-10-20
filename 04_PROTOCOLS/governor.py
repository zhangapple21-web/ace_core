"""Deprecated duplicate Governor boundary — superseded, kept for archaeology.

Why this file is no longer an entry point
-----------------------------------------
This module was a byte-identical second copy of ``core/governor.py``, and both
copies duplicated a governance role that ACE already owns:

* ``core/governance/knowledge_governor.py::Governor`` is the wired runtime
  Governor.  It records admission decisions in the canonical
  ``08_GOVERNANCE/governor/knowledge_governor_records.jsonl``.
* ``core/governance/governor_protocol.py`` owns the approval predicate.
* ``core/constitution_hierarchy.py::resolve_conflict`` owns rule precedence.

This copy had no production consumer, and it could not work on this host anyway:
``check_path_traversal`` denies any path containing ``:``, so every Windows
absolute path was refused, while its ``INVARIANTS`` table still named files that
are not invariants (``roundtable.py``, ``ops_005_self_loop.py``,
``bootstrap.py``).  Its ``approve`` path also wrote to
``02_MEMORY/governor_logs``, a third log location that exists in no runtime.

Leaving two answers to "may this change proceed" is exactly the kind of parallel
authority this guard removes.  Fail closed, like ``04_PROTOCOLS/heartbeat.py``.
Use the wired Governor instead.
"""

raise RuntimeError("governor_duplicate_deprecated:use core/governance/knowledge_governor.py")