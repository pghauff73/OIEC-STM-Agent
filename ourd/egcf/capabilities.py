from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from ..models import AuthorityManifest
from .errors import CapabilityError
from .ids import utc_now
from .models import CapabilityGrant, CapabilitySpec
from .store import EGCFStore


CAPABILITY_ORDER = {"C0": 0, "C1": 1, "C2": 2, "C3": 3, "C4": 4, "C5": 5}


CORE_CAPABILITIES = {
    "registry.read": "C0",
    "filesystem.read": "C0",
    "analysis.reason": "C1",
    "analysis.model": "C1",
    "analysis.experiment": "C1",
    "analysis.debug": "C1",
    "analysis.performance": "C1",
    "analysis.security": "C1",
    "analysis.geometry": "C1",
    "analysis.grammar": "C1",
    "analysis.vision": "C1",
    "analysis.cad": "C1",
    "evidence.analyse": "C1",
    "governance.read": "C1",
    "governance.propose": "C1",
    "registry.propose": "C1",
    "registry.qualify": "C1",
    "workflow.plan": "C1",
    "eon.plan": "C1",
    "verification.run": "C1",
    "simulation.run": "C2",
    "simulation.robotics": "C2",
    "agent.local": "C2",
    "filesystem.write": "C3",
    "process.execute": "C3",
    "workflow.execute": "C3",
    "registry.admin": "C3",
    "governance.write": "C3",
    "network.write": "C4",
    "git.remote.write": "C4",
    "database.write": "C4",
    "deployment.write": "C4",
    "human.contact": "C4",
    "governance.admin": "C5",
    "secret.rotate": "C5",
    "hardware.control": "C5",
}


class CapabilityResolver:
    def __init__(self, store: EGCFStore):
        self.store = store
        self.bootstrap()

    def bootstrap(self) -> None:
        for name, level in CORE_CAPABILITIES.items():
            facet = name.split(".", 1)[0]
            self.store.register(
                CapabilitySpec(
                    name=name,
                    level=level,
                    facet=facet,
                    description=f"EGCF capability {name}",
                )
            )

    def specs(self) -> list[CapabilitySpec]:
        return [record for record in self.store.find("capability-spec") if isinstance(record, CapabilitySpec)]

    def describe(self, name: str) -> CapabilitySpec:
        matches = [spec for spec in self.specs() if spec.name == name]
        if not matches:
            raise CapabilityError(f"unknown capability: {name}")
        return matches[-1]

    def requirement_level(self, capabilities: Iterable[str], declared_level: str = "C0") -> str:
        if declared_level not in CAPABILITY_ORDER:
            raise CapabilityError(f"invalid capability level: {declared_level}")
        level = declared_level
        for capability in capabilities:
            capability_level = self.describe(capability).level
            if CAPABILITY_ORDER[capability_level] > CAPABILITY_ORDER[level]:
                level = capability_level
        return level

    def grant_from_authority(self, authority: AuthorityManifest) -> CapabilityGrant:
        unknown_semantic = sorted(set(authority.semantic_capabilities) - set(CORE_CAPABILITIES))
        if unknown_semantic:
            raise CapabilityError(f"authority contains unknown semantic capabilities: {unknown_semantic}")
        capabilities = {
            name for name, level in CORE_CAPABILITIES.items() if CAPABILITY_ORDER[level] <= CAPABILITY_ORDER["C1"]
        }
        mapped = {
            "workspace.list": "filesystem.read",
            "workspace.read": "filesystem.read",
            "workspace.search": "filesystem.read",
            "git.status": "filesystem.read",
            "git.diff": "filesystem.read",
            "python.unittest": "verification.run",
            "python.py_compile": "verification.run",
            "ctest.run": "verification.run",
            "cmake.build": "process.execute",
            "package.install": "process.execute",
        }
        for capability in authority.read_capabilities + authority.command_capabilities:
            if capability in mapped:
                capabilities.add(mapped[capability])
        ceiling = authority.semantic_capability_ceiling
        capabilities.update(
            capability
            for capability in authority.semantic_capabilities
            if capability in CORE_CAPABILITIES
        )
        if not authority.read_only:
            capabilities.update({"filesystem.write", "process.execute", "workflow.execute"})
        return CapabilityGrant(
            subject=authority.task_id,
            capability_ceiling=ceiling,
            capabilities=sorted(capability for capability in capabilities if capability in CORE_CAPABILITIES),
            scope=list(authority.allowed_paths),
            resources={"forbidden_paths": authority.forbidden_paths},
            expires_at=authority.expires_at,
            budget={"retries": authority.max_retries_per_action},
            approval_modes=[
                "automatic",
                *( ["human"] if authority.allow_interactive_l2 else [] ),
            ],
            issuer=authority.operator,
            authority_hash=authority.authority_hash,
            use_limit=20,
        )

    @staticmethod
    def _expired(grant: CapabilityGrant) -> bool:
        if not grant.expires_at:
            return False
        expiry = datetime.fromisoformat(grant.expires_at.replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return expiry <= datetime.now(timezone.utc)

    def check(
        self,
        grant: CapabilityGrant,
        *,
        required_level: str,
        required_capabilities: Iterable[str],
    ) -> Dict[str, Any]:
        if self._expired(grant):
            raise CapabilityError("capability grant has expired")
        if required_level not in CAPABILITY_ORDER or grant.capability_ceiling not in CAPABILITY_ORDER:
            raise CapabilityError("invalid capability level in requirement or grant")
        missing = sorted(set(required_capabilities) - set(grant.capabilities))
        level_allowed = CAPABILITY_ORDER[required_level] <= CAPABILITY_ORDER[grant.capability_ceiling]
        allowed = level_allowed and not missing and grant.use_count < grant.use_limit
        result = {
            "allowed": allowed,
            "required_level": required_level,
            "capability_ceiling": grant.capability_ceiling,
            "required_capabilities": sorted(set(required_capabilities)),
            "granted_capabilities": sorted(set(grant.capabilities)),
            "missing_capabilities": missing,
            "use_count": grant.use_count,
            "use_limit": grant.use_limit,
            "reason": "authorized" if allowed else "capability requirement exceeds grant",
        }
        if not allowed:
            raise CapabilityError(result["reason"] + f": {result}")
        return result

    def request(
        self,
        subject: str,
        capabilities: Iterable[str],
        scope: Iterable[str],
        justification: str,
    ) -> Dict[str, Any]:
        requested = sorted(set(capabilities))
        required_level = self.requirement_level(requested)
        return {
            "status": "PROPOSED",
            "subject": subject,
            "capabilities": requested,
            "capability_level": required_level,
            "scope": list(scope),
            "justification": justification,
            "created_at": utc_now(),
            "approval_required": True,
        }

    def grant(self, record: CapabilityGrant, *, administrative: bool) -> str:
        if not administrative:
            raise CapabilityError("capability grant requires external administrative authority")
        return self.store.register(record)

    def revoke(self, grant_id: str, *, administrative: bool, reason: str) -> Dict[str, Any]:
        if not administrative:
            raise CapabilityError("capability revoke requires external administrative authority")
        grant = self.store.get(grant_id)
        if not isinstance(grant, CapabilityGrant):
            raise CapabilityError(f"not a capability grant: {grant_id}")
        return {
            "grant_id": grant_id,
            "status": "REVOKED",
            "reason": reason,
            "revoked_at": utc_now(),
        }
