import asyncio
import yaml

from config.loader import ConfigLoader
from core.adapters.base import BaseLLMAdapter, LLMResponse
from core.orchestration.engine import WorkflowEngine
from core.tools.registry import ToolRegistry


class FakeAdapter(BaseLLMAdapter):
    def __init__(self):
        super().__init__(api_key="x", model_name="fake-model")
        self.last_prompt = ""
        self.last_system_prompt = ""

    async def generate(self, prompt: str, system_prompt=None, temperature: float = 0.7, max_tokens: int = 4096):
        return LLMResponse(text="ok", input_tokens=1, output_tokens=1, model=self.model_name, latency_ms=1)

    async def generate_with_vision(self, prompt: str, images, system_prompt=None, temperature: float = 0.7):
        return LLMResponse(text="vision", input_tokens=1, output_tokens=1, model=self.model_name, latency_ms=1)

    async def generate_json(self, prompt: str, system_prompt=None, temperature: float = 0.3):
        self.last_prompt = prompt
        self.last_system_prompt = system_prompt or ""
        return {
            "industry": "solar",
            "priority": "high",
            "confidence": 0.93,
        }

    async def embed(self, text: str):
        return [0.1, 0.2]


class StubAgentFactory:
    def __init__(self, adapter):
        self.base_adapter = adapter
        self.retriever = None
        self.todo_store = None
        self.tool_registry = ToolRegistry()


def test_classification_workflow_uses_profile_dimensions(tmp_path):
    profiles = tmp_path / 'profiles'
    workflows = tmp_path / 'workflows'
    profiles.mkdir()
    workflows.mkdir()
    (profiles / 'lead_priority.yaml').write_text(yaml.safe_dump({
        'profile_id': 'lead_priority',
        'dimensions': [
            {'name': 'industry', 'field_type': 'enum', 'allowed_values': ['solar', 'other'], 'required': True},
            {'name': 'priority', 'field_type': 'enum', 'allowed_values': ['high', 'low'], 'required': True},
            {'name': 'confidence', 'field_type': 'number', 'required': True},
        ],
    }), encoding='utf-8')
    (workflows / 'lead_priority.yaml').write_text(yaml.safe_dump({
        'workflow_id': 'lead_priority', 'start_at': 'classify_lead',
        'nodes': [{
            'node_id': 'classify_lead', 'node_type': 'classification',
            'config': {'profile_id': 'lead_priority'},
            'input_map': {'conversation_text': 'input.conversation_text', 'company_name': 'input.company_name'},
            'output_map': {'outputs.classification': 'result'}, 'transitions': [],
        }],
    }), encoding='utf-8')
    adapter = FakeAdapter()
    engine = WorkflowEngine(
        config_loader=ConfigLoader(workflow_specs_dir=str(workflows), workflow_profiles_dir=str(profiles)),
        agent_factory=StubAgentFactory(adapter),
    )

    result = asyncio.run(
        engine.run(
            workflow_id="lead_priority",
            payload={
                "conversation_text": "Solar installer requesting pricing for a commercial project.",
                "company_name": "Example Solar",
            },
        )
    )

    classification = result["state"]["outputs"]["classification"]
    assert classification["industry"] == "solar"
    assert classification["priority"] == "high"
    assert "industry" in adapter.last_system_prompt
    assert "Example Solar" in adapter.last_prompt
