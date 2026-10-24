from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional

@dataclass
class AgentStepLog:
    timestamp: str
    trace_id: str
    session_id: str
    agent_id: str
    step: int
    event: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "step": self.step,
            "event": self.event,
            "payload": self.payload,
        }

    @classmethod
    def create(
        cls,
        trace_id: str,
        session_id: str,
        agent_id: str,
        step: int,
        event: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> "AgentStepLog":
        return cls(
            timestamp=datetime.now().isoformat(),
            trace_id=trace_id,
            session_id=session_id,
            agent_id=agent_id,
            step=step,
            event=event,
            payload=payload or {},
        )
