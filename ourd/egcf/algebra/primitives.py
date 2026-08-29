from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from ..errors import EGCFError


@dataclass(frozen=True)
class PrimitiveSpec:
    name: str
    category: str
    commutative: bool = False
    associative: bool = False


_PRIMITIVES = (
    PrimitiveSpec("IDENTITY", "data"),
    PrimitiveSpec("CONST", "data"),
    PrimitiveSpec("ADD", "arithmetic", commutative=True, associative=True),
    PrimitiveSpec("SUBTRACT", "arithmetic"),
    PrimitiveSpec("MULTIPLY", "arithmetic", commutative=True, associative=True),
    PrimitiveSpec("DIVIDE", "arithmetic"),
    PrimitiveSpec("NEGATE", "arithmetic"),
    PrimitiveSpec("ABS", "arithmetic"),
    PrimitiveSpec("MIN", "arithmetic", commutative=True, associative=True),
    PrimitiveSpec("MAX", "arithmetic", commutative=True, associative=True),
    PrimitiveSpec("CLAMP", "arithmetic"),
    PrimitiveSpec("COMPARE_EQ", "predicate", commutative=True),
    PrimitiveSpec("COMPARE_NE", "predicate", commutative=True),
    PrimitiveSpec("COMPARE_LT", "predicate"),
    PrimitiveSpec("COMPARE_LE", "predicate"),
    PrimitiveSpec("COMPARE_GT", "predicate"),
    PrimitiveSpec("COMPARE_GE", "predicate"),
    PrimitiveSpec("SELECT", "control"),
    PrimitiveSpec("INVOKE", "execution"),
    PrimitiveSpec("OBSERVE", "reasoning"),
    PrimitiveSpec("GENERATE", "reasoning"),
    PrimitiveSpec("PREDICT", "reasoning"),
    PrimitiveSpec("COMPARE", "reasoning", commutative=True),
    PrimitiveSpec("VERIFY", "reasoning"),
    PrimitiveSpec("FALSIFY", "reasoning"),
    PrimitiveSpec("PRUNE", "reasoning"),
    PrimitiveSpec("BACKTRACK", "reasoning"),
    PrimitiveSpec("SYNTHESIZE", "reasoning"),
    PrimitiveSpec("BRANCH", "control"),
    PrimitiveSpec("ITERATE", "control"),
    PrimitiveSpec("TERMINATE", "control"),
)

PRIMITIVES: Dict[str, PrimitiveSpec] = {item.name: item for item in _PRIMITIVES}

ALIASES = {
    "+": "ADD",
    "ADD": "ADD",
    "SUM": "ADD",
    "-": "SUBTRACT",
    "SUB": "SUBTRACT",
    "SUBTRACT": "SUBTRACT",
    "*": "MULTIPLY",
    "MUL": "MULTIPLY",
    "MULTIPLY": "MULTIPLY",
    "/": "DIVIDE",
    "DIV": "DIVIDE",
    "DIVIDE": "DIVIDE",
    "==": "COMPARE_EQ",
    "!=": "COMPARE_NE",
    "<": "COMPARE_LT",
    "<=": "COMPARE_LE",
    ">": "COMPARE_GT",
    ">=": "COMPARE_GE",
}


def normalize_primitive(value: str) -> PrimitiveSpec:
    key = str(value).strip().upper()
    key = ALIASES.get(key, key)
    try:
        return PRIMITIVES[key]
    except KeyError as exc:
        raise EGCFError(f"unknown SAA primitive: {value!r}") from exc


def primitive_names() -> tuple[str, ...]:
    return tuple(sorted(PRIMITIVES))
