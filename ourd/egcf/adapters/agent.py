from typing import Any, Dict

from ..capabilities import CAPABILITY_ORDER
from ..context import narrow_scope
from ..errors import EGCFError
from .codex import CodexAdapter


class AgentAdapter(CodexAdapter):
    name = "agent"

    def execute(self, plan_node: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        parent = dict(kwargs.get("parent_grant", {}))
        child = dict(kwargs.get("child_grant", {}))
        if not parent or not child:
            raise EGCFError("agent adapter requires explicit parent and child grants")
        parent_level = str(parent.get("capability_ceiling", "C0"))
        child_level = str(child.get("capability_ceiling", "C5"))
        if CAPABILITY_ORDER[child_level] > CAPABILITY_ORDER[parent_level]:
            raise EGCFError("child agent capability ceiling broadens parent grant")
        parent_capabilities = set(parent.get("capabilities", []))
        child_capabilities = set(child.get("capabilities", []))
        if not child_capabilities.issubset(parent_capabilities):
            raise EGCFError("child agent capabilities broaden parent grant")
        child_scope = narrow_scope(parent.get("scope", []), child.get("scope", []))
        result = kwargs.get("agent_result")
        if result is None:
            raise EGCFError("agent adapter requires a host-provided bounded result")
        return {
            "result": result,
            "child_grant": {**child, "scope": child_scope},
            "approval": False,
            "consensus_is_authority": False,
            "authority_transfer": False,
        }
