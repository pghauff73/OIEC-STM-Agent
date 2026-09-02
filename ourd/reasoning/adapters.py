from __future__ import annotations

import ast
import itertools
import re
from dataclasses import asdict, dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation, localcontext
from typing import Any, Iterable, Mapping, Sequence

from .models import stable_hash


ADAPTER_STATUSES = {"PASS", "FAIL", "INCONCLUSIVE", "UNAVAILABLE"}


@dataclass(frozen=True)
class AdapterResult:
    schema_version: int = 1
    adapter: str = ""
    claim: str = ""
    status: str = "INCONCLUSIVE"
    result: str = ""
    evidence_id: str = ""
    details: tuple[str, ...] = ()
    tolerance: str = ""
    counterexample: tuple[tuple[str, str], ...] = ()
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.adapter or not self.claim:
            raise ValueError("adapter and claim must be non-empty")
        if self.status not in ADAPTER_STATUSES:
            raise ValueError(f"invalid adapter status: {self.status}")
        object.__setattr__(self, "details", tuple(sorted({str(value) for value in self.details})))
        object.__setattr__(
            self,
            "counterexample",
            tuple(sorted((str(key), str(value)) for key, value in self.counterexample)),
        )
        material = asdict(self)
        material.pop("evidence_id", None)
        material.pop("signature", None)
        evidence_id = f"adapter-evidence:{stable_hash(material)}"
        if self.evidence_id and self.evidence_id != evidence_id:
            raise ValueError("adapter evidence ID mismatch")
        object.__setattr__(self, "evidence_id", evidence_id)
        signature = stable_hash({**material, "evidence_id": evidence_id})
        if self.signature and self.signature != signature:
            raise ValueError("adapter result signature mismatch")
        object.__setattr__(self, "signature", signature)


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError("booleans are not numeric adapter values")
    return Decimal(str(value))


def _evaluate(node: ast.AST, variables: Mapping[str, Decimal]) -> Any:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, variables)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return _decimal(node.value)
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise ValueError(f"unknown variable: {node.id}")
        return variables[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate(node.operand, variables)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _evaluate(node.left, variables)
        right = _evaluate(node.right, variables)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            if right != right.to_integral_value() or abs(right) > 32:
                raise ValueError("adapter exponents must be integral and bounded")
            return left ** int(right)
    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, variables)
        for operator, comparator in zip(node.ops, node.comparators):
            right = _evaluate(comparator, variables)
            if isinstance(operator, ast.Eq):
                passed = left == right
            elif isinstance(operator, ast.NotEq):
                passed = left != right
            elif isinstance(operator, ast.Lt):
                passed = left < right
            elif isinstance(operator, ast.LtE):
                passed = left <= right
            elif isinstance(operator, ast.Gt):
                passed = left > right
            elif isinstance(operator, ast.GtE):
                passed = left >= right
            else:
                raise ValueError("unsupported comparison operator")
            if not passed:
                return False
            left = right
        return True
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        values = [bool(_evaluate(value, variables)) for value in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not bool(_evaluate(node.operand, variables))
    raise ValueError(f"unsupported adapter expression node: {type(node).__name__}")


def evaluate_decimal_expression(
    expression: str,
    *,
    variables: Mapping[str, Any] | None = None,
    precision: int = 50,
) -> AdapterResult:
    claim = f"evaluate {expression}"
    try:
        tree = ast.parse(expression, mode="eval")
        values = {str(key): _decimal(value) for key, value in (variables or {}).items()}
        with localcontext() as context:
            context.prec = max(16, min(200, int(precision)))
            result = _evaluate(tree, values)
    except (SyntaxError, ValueError, InvalidOperation, DivisionByZero, ZeroDivisionError) as exc:
        return AdapterResult(
            adapter="decimal-arithmetic-v1",
            claim=claim,
            status="INCONCLUSIVE",
            result=f"{type(exc).__name__}: {exc}",
        )
    return AdapterResult(
        adapter="decimal-arithmetic-v1",
        claim=claim,
        status="PASS",
        result=str(result),
    )


def symbolic_equivalence(left: str, right: str) -> AdapterResult:
    claim = f"{left} == {right}"
    if not all(
        re.fullmatch(r"[A-Za-z0-9_+\-*/^(). ]+", expression or "")
        and "__" not in expression
        for expression in (left, right)
    ):
        return AdapterResult(
            adapter="sympy-equivalence-v1",
            claim=claim,
            status="INCONCLUSIVE",
            result="expression rejected by the bounded symbolic grammar",
        )
    try:
        import sympy  # type: ignore
    except ImportError:
        return AdapterResult(
            adapter="sympy-equivalence-v1",
            claim=claim,
            status="UNAVAILABLE",
            result="SymPy is not installed",
        )
    try:
        symbols = {
            name: sympy.Symbol(name)
            for name in sorted(set(re.findall(r"[A-Za-z_]\w*", f"{left} {right}")))
        }
        left_value = sympy.sympify(left.replace("^", "**"), locals=symbols)
        right_value = sympy.sympify(right.replace("^", "**"), locals=symbols)
        residual = sympy.simplify(left_value - right_value)
    except Exception as exc:
        return AdapterResult(
            adapter="sympy-equivalence-v1",
            claim=claim,
            status="INCONCLUSIVE",
            result=f"{type(exc).__name__}: {exc}",
        )
    equivalent = residual == 0
    return AdapterResult(
        adapter="sympy-equivalence-v1",
        claim=claim,
        status="PASS" if equivalent else "FAIL",
        result=str(residual),
    )


def numerical_residual_check(
    left: str,
    right: str,
    *,
    points: Sequence[Mapping[str, Any]],
    tolerance: str = "1e-12",
) -> AdapterResult:
    claim = f"numerical residual for {left} == {right}"
    threshold = _decimal(tolerance)
    if threshold < 0:
        raise ValueError("numerical tolerance must be non-negative")
    failures = []
    try:
        left_tree = ast.parse(left, mode="eval")
        right_tree = ast.parse(right, mode="eval")
        for point in points:
            variables = {str(key): _decimal(value) for key, value in point.items()}
            residual = abs(_evaluate(left_tree, variables) - _evaluate(right_tree, variables))
            if residual > threshold:
                failures.append((point, residual))
    except (SyntaxError, ValueError, InvalidOperation, DivisionByZero, ZeroDivisionError) as exc:
        return AdapterResult(
            adapter="numerical-residual-v1",
            claim=claim,
            status="INCONCLUSIVE",
            result=f"{type(exc).__name__}: {exc}",
            tolerance=str(threshold),
        )
    if failures:
        point, residual = failures[0]
        return AdapterResult(
            adapter="numerical-residual-v1",
            claim=claim,
            status="FAIL",
            result=f"residual {residual} exceeds tolerance",
            tolerance=str(threshold),
            counterexample=tuple((str(key), str(value)) for key, value in point.items()),
        )
    return AdapterResult(
        adapter="numerical-residual-v1",
        claim=claim,
        status="PASS",
        result=f"{len(points)} points within tolerance",
        tolerance=str(threshold),
    )


def dimensional_equivalence(
    left_dimensions: Mapping[str, int],
    right_dimensions: Mapping[str, int],
    *,
    equation: str = "equation",
) -> AdapterResult:
    left = tuple(sorted((str(key), int(value)) for key, value in left_dimensions.items() if value))
    right = tuple(sorted((str(key), int(value)) for key, value in right_dimensions.items() if value))
    return AdapterResult(
        adapter="dimensional-analysis-v1",
        claim=f"dimensions match for {equation}",
        status="PASS" if left == right else "FAIL",
        result=f"left={left}; right={right}",
    )


def finite_domain_check(
    predicate: str,
    *,
    domains: Mapping[str, Sequence[Any]],
    max_combinations: int = 10_000,
) -> AdapterResult:
    claim = f"finite-domain predicate: {predicate}"
    names = tuple(sorted(domains))
    combinations = 1
    for name in names:
        combinations *= len(domains[name])
    if combinations > max(1, int(max_combinations)):
        return AdapterResult(
            adapter="finite-domain-v1",
            claim=claim,
            status="INCONCLUSIVE",
            result="finite domain exceeds the configured combination bound",
        )
    try:
        tree = ast.parse(predicate, mode="eval")
        for values in itertools.product(*(domains[name] for name in names)):
            assignment = {name: _decimal(value) for name, value in zip(names, values)}
            if not bool(_evaluate(tree, assignment)):
                return AdapterResult(
                    adapter="finite-domain-v1",
                    claim=claim,
                    status="FAIL",
                    result="counterexample found",
                    counterexample=tuple(
                        (name, str(value)) for name, value in zip(names, values)
                    ),
                )
    except (SyntaxError, ValueError, InvalidOperation, DivisionByZero, ZeroDivisionError) as exc:
        return AdapterResult(
            adapter="finite-domain-v1",
            claim=claim,
            status="INCONCLUSIVE",
            result=f"{type(exc).__name__}: {exc}",
        )
    return AdapterResult(
        adapter="finite-domain-v1",
        claim=claim,
        status="PASS",
        result=f"all {combinations} assignments passed",
    )


__all__ = [
    "ADAPTER_STATUSES",
    "AdapterResult",
    "dimensional_equivalence",
    "evaluate_decimal_expression",
    "finite_domain_check",
    "numerical_residual_check",
    "symbolic_equivalence",
]
