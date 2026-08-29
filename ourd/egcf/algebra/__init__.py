"""Searchable Algebra of Algorithms structural canonicalization layer."""

from .graph import CANONICALIZER_VERSION, canonicalize_structure, validate_structure
from .ir import canonicalize_many, canonicalize_mapping, operand_from_mapping, structure_from_mapping
from .models import (
    AlgorithmNodeSpec,
    AlgorithmStructureSpec,
    CanonicalAlgorithmIR,
    ControlEdgeSpec,
    OperandRef,
    PortSpec,
    StateSpec,
    attribute_items,
)
from .primitives import PrimitiveSpec, normalize_primitive, primitive_names

__all__ = [
    "AlgorithmNodeSpec",
    "AlgorithmStructureSpec",
    "CANONICALIZER_VERSION",
    "CanonicalAlgorithmIR",
    "ControlEdgeSpec",
    "OperandRef",
    "PortSpec",
    "PrimitiveSpec",
    "StateSpec",
    "attribute_items",
    "canonicalize_many",
    "canonicalize_mapping",
    "canonicalize_structure",
    "normalize_primitive",
    "operand_from_mapping",
    "primitive_names",
    "structure_from_mapping",
    "validate_structure",
]
