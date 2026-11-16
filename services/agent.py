"""callagent's agent — a universal AgentDefinition over the shared services.

The product shell (Twilio consent flow, tier gate, rate limiting, call
recording in ``services/voice_agent.py``) stays in the product; the *brain*
is the same ``shared.agent_runtime.universal.create_agent`` factory every
other agent (assistant-core/JARVIS, vertical receptionists, tutors) uses:

    from services.agent import get_agent

    agent = get_agent(tenant_id="acme")      # UniversalAgent
    result = await agent.chat("I need a plumber", session_id="call:CA123")

Capabilities: chat + rag_kb (voice KB) + voice + booking +
missed_call_recovery + web_widget + billing_guard — all wired to the same
shared.* services via the capability registry.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from shared.agent_runtime.universal import (
    AGENT_DEFINITIONS,
    UniversalAgent,
    create_agent,
    define_agent,
    get_agent_definition,
)

__all__ = ["get_callagent_definition", "get_agent"]


def get_callagent_definition():
    """The callagent agent definition (registered once)."""
    if "callagent" not in AGENT_DEFINITIONS:
        define_agent(
            "callagent",
            "CallAgent Receptionist",
            kind="receptionist",
            greeting="Thanks for calling {business_name}.",
            capabilities=(
                "chat",
                "rag_kb",
                "voice",
                "booking",
                "missed_call_recovery",
                "web_widget",
                "billing_guard",
            ),
            trade_id="home_maintenance",
            metadata={"services": ["booking", "pricing", "faq", "callback"]},
        )
    return get_agent_definition("callagent")


@lru_cache(maxsize=16)
def _build(tenant_id: str, data_dir: str, dry_run: bool) -> UniversalAgent:
    return create_agent(
        get_callagent_definition(),
        data_dir=data_dir,
        tenant_id=tenant_id,
        assistant_id="callagent",
        business_name=os.getenv("CALLAGENT_BUSINESS_NAME", "CallAgent"),
        dry_run=dry_run,
    )


def get_agent(
    tenant_id: str = "default",
    data_dir: str | None = None,
    dry_run: bool | None = None,
) -> UniversalAgent:
    """Get (cached) the universal agent for a tenant."""
    if data_dir is None:
        data_dir = os.getenv("CALLAGENT_AGENT_DATA_DIR", "./data/agent")
    if dry_run is None:
        dry_run = os.getenv("APP_ENV") != "production"
    return _build(tenant_id, data_dir, dry_run)


async def answer_call_speech(transcript: str, *, tenant_id: str, call_sid: str | None = None) -> Any:
    """Generate the spoken answer for a call turn via the universal agent.

    Returns the LocalAgentResult; callers fall back to their template
    response when the agent is in dry-run or errored.
    """
    agent = get_agent(tenant_id=tenant_id)
    return await agent.chat(
        transcript,
        session_id=f"call:{call_sid}" if call_sid else None,
        system_prompt=agent.system_prompt(),
    )
