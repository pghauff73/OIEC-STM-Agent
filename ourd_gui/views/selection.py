from __future__ import annotations

import tkinter as tk
from dataclasses import asdict
from tkinter import ttk
from typing import Callable

from ..selection_trace import SelectionCandidateView, SelectionTrace
from ..widgets.graph_view import GraphEdge, GraphNode, GraphView
from ..widgets.property_grid import PropertyGrid


class SelectionTraceView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_object_selected: Callable[[str], None] | None = None,
        on_show_evidence: Callable[[tuple[str, ...]], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.on_object_selected = on_object_selected
        self.on_show_evidence = on_show_evidence
        self.trace: SelectionTrace | None = None
        self._candidate_by_node: dict[str, SelectionCandidateView] = {}
        self._selected_candidate: SelectionCandidateView | None = None
        self._selected_object_id = ""
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        self.summary = ttk.Label(toolbar, text="No selection trace loaded")
        self.summary.pack(side="left", fill="x", expand=True, padx=6, pady=4)
        ttk.Button(toolbar, text="Explain Selection", command=self._select_winner).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Compare Candidates", command=self._compare_candidates).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Show Rejections", command=self._select_first_rejection).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Show Evidence", command=self._show_selected_evidence).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Open Qualification", command=self._open_qualification).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Open Command", command=self._open_command).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Copy ID", command=self._copy_id).pack(side="left", padx=2)
        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True)
        self.graph = GraphView(paned, on_select=self._graph_selected)
        self.details = PropertyGrid(paned)
        paned.add(self.graph, weight=4)
        paned.add(self.details, weight=2)

    def set_trace(self, trace: SelectionTrace | None) -> None:
        self.trace = trace
        self._candidate_by_node.clear()
        self._selected_candidate = None
        self._selected_object_id = ""
        if trace is None:
            self.summary.configure(text="No selection trace loaded")
            self.graph.set_graph([], [])
            self.details.set_properties({})
            return
        nodes = [
            GraphNode(
                node_id="intent",
                label=trace.command_id,
                layer=0,
                order=0,
                status="neutral",
                subtitle="Intent / Command",
                object_id=trace.intent_id or trace.invocation_id,
            ),
            GraphNode(
                node_id="capability",
                label=trace.required_capability_level or "Capability",
                layer=1,
                order=0,
                status="qualified",
                subtitle=", ".join(trace.required_capabilities) or "No facets recorded",
            ),
        ]
        edges = [GraphEdge("intent", "capability")]
        for index, candidate in enumerate(trace.candidates):
            node_id = f"candidate:{index}"
            self._candidate_by_node[node_id] = candidate
            status = "selected" if candidate.selected else "excluded" if candidate.rejection_reasons else "qualified"
            score = candidate.score_components
            subtitle = (
                f"{status.upper()} | q={score.get('qualification_strength', 0)} "
                f"tests={score.get('expected_correctness', 0)}"
            )
            if candidate.rejection_reasons:
                subtitle = candidate.rejection_reasons[0]
            nodes.append(
                GraphNode(
                    node_id=node_id,
                    label=candidate.algorithm_id,
                    layer=2,
                    order=index,
                    status=status,
                    subtitle=subtitle,
                    object_id=candidate.definition_id,
                    data={"candidate_index": index},
                )
            )
            edges.append(GraphEdge("capability", node_id))
            if candidate.selected:
                nodes.append(
                    GraphNode(
                        node_id="selected",
                        label=candidate.algorithm_id,
                        layer=3,
                        order=0,
                        status="selected",
                        subtitle="SELECTED",
                        object_id=candidate.definition_id,
                    )
                )
                edges.append(GraphEdge(node_id, "selected", "winner"))
        self.graph.set_graph(nodes, edges)
        self.summary.configure(
            text=(
                f"{trace.command_id} | {len(trace.candidates)} algorithms | "
                f"selected {trace.selected_algorithm_id}"
            )
        )
        self._select_winner()

    def _graph_selected(self, node: GraphNode) -> None:
        candidate = self._candidate_by_node.get(node.node_id)
        if candidate is not None:
            self._selected_candidate = candidate
            self._selected_object_id = candidate.definition_id
            self.details.set_properties(asdict(candidate))
            if candidate.definition_id and self.on_object_selected is not None:
                self.on_object_selected(candidate.definition_id)
            return
        if self.trace is not None:
            self._selected_candidate = None
            self._selected_object_id = node.object_id
            properties = {
                "node": node.label,
                "selection_id": self.trace.selection_id,
                "command_id": self.trace.command_id,
                "intent_id": self.trace.intent_id,
                "invocation_id": self.trace.invocation_id,
                "source_snapshot_hash": self.trace.source_snapshot_hash,
                "diagnostics": [asdict(item) for item in self.trace.diagnostics],
            }
            self.details.set_properties(properties)
        if node.object_id and self.on_object_selected is not None:
            self.on_object_selected(node.object_id)

    def _select_winner(self) -> None:
        if self.trace is None:
            return
        for node_id, candidate in self._candidate_by_node.items():
            if candidate.selected:
                self.graph.select(node_id)
                return

    def _select_first_rejection(self) -> None:
        for node_id, candidate in self._candidate_by_node.items():
            if candidate.rejection_reasons:
                self.graph.select(node_id)
                return

    def _show_selected_evidence(self) -> None:
        if self.trace is None or self.on_show_evidence is None:
            return
        candidate = self._selected_candidate or next(
            (item for item in self.trace.candidates if item.selected), None
        )
        self.on_show_evidence(candidate.evidence_ids if candidate else self.trace.evidence_ids)

    def _compare_candidates(self) -> None:
        if self.trace is None:
            return
        by_identity = {
            (candidate.algorithm_id, candidate.algorithm_digest): candidate
            for candidate in self.trace.candidates
        }
        rows = []
        for rank, identity in enumerate(self.trace.ranking, start=1):
            algorithm_id, separator, digest = identity.partition("@")
            candidate = by_identity.get((algorithm_id, digest)) if separator else None
            if candidate is None:
                candidate = next(
                    (item for item in self.trace.candidates if item.algorithm_id == identity),
                    None,
                )
            if candidate is None:
                rows.append({"rank": rank, "identity": identity, "status": "missing"})
                continue
            rows.append(
                {
                    "rank": rank,
                    "algorithm_id": candidate.algorithm_id,
                    "selected": candidate.selected,
                    "qualified": candidate.qualified,
                    "status": candidate.status,
                    "scores": dict(candidate.score_components),
                    "rejection_reasons": list(candidate.rejection_reasons),
                    "capability_level": candidate.capability_level,
                    "risk_floor": candidate.risk_floor,
                    "rollback_class": candidate.rollback_class,
                    "evidence_count": len(candidate.evidence_ids),
                }
            )
        if not rows:
            rows = [
                {
                    "algorithm_id": candidate.algorithm_id,
                    "selected": candidate.selected,
                    "qualified": candidate.qualified,
                    "scores": dict(candidate.score_components),
                    "rejection_reasons": list(candidate.rejection_reasons),
                }
                for candidate in self.trace.candidates
            ]
        self.details.set_properties(
            {
                "selected_algorithm": self.trace.selected_algorithm_id,
                "tie_break": self.trace.tie_break,
                "candidates": rows,
            }
        )

    def _open_qualification(self) -> None:
        if self.on_object_selected is None:
            return
        candidate = self._selected_candidate
        if candidate is None:
            return
        if candidate.qualification_ids:
            self.on_object_selected(candidate.qualification_ids[0])

    def _open_command(self) -> None:
        if (
            self.trace is not None
            and self.trace.command_definition_id
            and self.on_object_selected is not None
        ):
            self.on_object_selected(self.trace.command_definition_id)

    def _copy_id(self) -> None:
        identifier = self._selected_object_id
        if not identifier and self.trace is not None:
            identifier = self.trace.selection_id
        if not identifier:
            return
        self.clipboard_clear()
        self.clipboard_append(identifier)
