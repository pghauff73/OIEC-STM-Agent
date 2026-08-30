"""Shared visual grammar and validation helpers for generated documentation SVGs."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from typing import Iterable


VISUAL_GRAMMAR_VERSION = 1


@dataclass(frozen=True)
class NodeRole:
    role: str
    shape: str
    meaning: str


@dataclass(frozen=True)
class EdgeRole:
    role: str
    style: str
    meaning: str


NODE_ROLES = (
    NodeRole("concept", "circle", "Concept or state"),
    NodeRole("process", "rounded-rectangle", "Process or transformation"),
    NodeRole("gate", "hexagon", "Gate or check"),
    NodeRole("decision", "diamond", "Uncertainty or decision"),
    NodeRole("evidence", "document", "Evidence artifact"),
    NodeRole("authority", "shield", "Authority or boundary"),
    NodeRole("canonical", "double-border", "Canonical knowledge"),
    NodeRole("object", "typed-symbol", "Source-bound relational object"),
)

EDGE_ROLES = (
    EdgeRole("contradiction", "red", "Contradiction or falsification"),
    EdgeRole("hypothesis", "dashed", "Hypothesis or unverified relation"),
    EdgeRole("verified", "solid", "Verified relation"),
    EdgeRole("dependency", "arrow", "Required ordering or dependency"),
)

NODE_ROLE_NAMES = {item.role for item in NODE_ROLES}
EDGE_ROLE_NAMES = {item.role for item in EDGE_ROLES}


def root_attributes(visual_role: str) -> str:
    return (
        f'data-visual-grammar="{VISUAL_GRAMMAR_VERSION}" '
        f'data-visual-role="{visual_role}"'
    )


def node_attributes(node_id: str, role: str, label: str) -> str:
    if role not in NODE_ROLE_NAMES:
        raise ValueError(f"unknown visual node role: {role}")
    escaped_label = (
        label.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return (
        f'data-doc-node="{node_id}" data-node-role="{role}" '
        f'aria-label="{escaped_label}" tabindex="0"'
    )


def edge_attributes(relation: str, verification: str = "verified") -> str:
    if verification not in EDGE_ROLE_NAMES:
        raise ValueError(f"unknown visual edge role: {verification}")
    return (
        f'data-relation="{relation}" data-verification="{verification}" '
        'aria-hidden="true"'
    )


def grammar_manifest() -> dict[str, object]:
    return {
        "version": VISUAL_GRAMMAR_VERSION,
        "nodes": [asdict(item) for item in NODE_ROLES],
        "edges": [asdict(item) for item in EDGE_ROLES],
    }


def validate_svg(svg: str, require_semantic_nodes: bool = True) -> None:
    root = ET.fromstring(svg)
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    if root.attrib.get("data-visual-grammar") != str(VISUAL_GRAMMAR_VERSION):
        raise ValueError("SVG does not declare the current visual grammar")
    if root.find("svg:title", namespace) is None or root.find("svg:desc", namespace) is None:
        raise ValueError("SVG requires title and description")
    nodes = ([root] if "data-doc-node" in root.attrib else []) + root.findall(
        ".//*[@data-doc-node]"
    )
    if require_semantic_nodes and not nodes:
        raise ValueError("SVG requires at least one semantic node")
    for node in nodes:
        if node.attrib.get("data-node-role") not in NODE_ROLE_NAMES:
            raise ValueError("SVG node uses an unknown semantic role")
        if node.attrib.get("tabindex") != "0":
            raise ValueError("SVG semantic nodes must be keyboard focusable")


def validate_all(svgs: Iterable[str]) -> None:
    for svg in svgs:
        validate_svg(svg)
