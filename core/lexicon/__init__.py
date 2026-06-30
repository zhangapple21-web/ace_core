"""
Lexicon 词库系统模块

三级分类体系：
- 一级：domain（领域）→ 51个领域，按用户意图组织
- 二级：type（类型）→ knowledge/pattern/principle/law/paradigm
- 三级：attribute（属性）→ verified/hypothesis/deprecated
"""

import sys as _sys
import importlib.util as _importlib_util
from pathlib import Path as _Path

from .lexicon_categories import (
    LexiconCategoryRegistry,
    DOMAINS,
    TYPES,
    ATTRIBUTES,
    get_categories,
    get_subcategories,
    add_category,
    categorize_concept,
    default_registry,
)

_lexicon_py_path = _Path(__file__).parent.parent / "lexicon.py"
if _lexicon_py_path.exists():
    _core_identity = _sys.modules.get("core.identity")
    if _core_identity is None:
        import core.identity as _core_identity_mod
        _core_identity = _core_identity_mod
    _sys.modules["core.lexicon.identity"] = _core_identity

    _code = compile(
        _lexicon_py_path.read_text(encoding="utf-8"),
        str(_lexicon_py_path),
        "exec",
    )
    _lex_globals = globals()
    _lex_globals["__name__"] = "core.lexicon"
    _lex_globals["__file__"] = str(_lexicon_py_path)
    exec(_code, _lex_globals)

    Lexicon = _lex_globals.get("Lexicon")
else:
    Lexicon = None

__all__ = [
    "Lexicon",
    "LexiconCategoryRegistry",
    "DOMAINS",
    "TYPES",
    "ATTRIBUTES",
    "get_categories",
    "get_subcategories",
    "add_category",
    "categorize_concept",
    "default_registry",
]
