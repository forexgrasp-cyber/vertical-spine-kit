"""CallAgent universal agent definition and factory.

Registers the "callagent" AgentDefinition with capabilities:
- chat, rag_kb, voice, booking, missed_call_recovery, web_widget, billing_guard

Uses shared.agent_runtime.universal.create_agent for the single canonical agent core.
"""

from __future__ import annotations

from functools import lru_cache

from shared.agent_runtime.universal import AgentDefinition, create_agent
from shared.vertical_app.spec import get_vertical_spec as get_spec


# ---- CallAgent AgentDefinition ----------------------------------------------

CALLAGENT_CAPABILITIES = (
    "chat",
    "rag_kb",
    "voice",
    "booking",
    "missed_call_recovery",
    "web_widget",
    "billing_guard",
)

CALLAGENT_DEFINITION = AgentDefinition(
    slug="callagent",
    name="CallAgent",
    kind="receptionist",
    capabilities=CALLAGENT_CAPABILITIES,
    # Vertical spec provides the receptionist prompt, services, emergency keywords
    vertical="contractor",  # contractor receptionist as base
    # No memory/persona — receptionist is stateless per call; tenant config in VerticalServices
)


# ---- Factory -----------------------------------------------------------------


@lru_cache(maxsize=32)
def get_agent(tenant_id: str = "default"):
    """Get or create the UniversalAgent for a tenant (cached).

    The agent is stateless per call; tenant-specific config (greetings,
    services, emergency keywords) comes from VerticalServices at request time.
    """
    return create_agent(CALLAGENT_DEFINITION)


__all__ = [
    "CALLAGENT_DEFINITION",
    "CALLAGENT_CAPABILITIES",
    "get_agent",
]