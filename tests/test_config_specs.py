from config.loader import ConfigLoader


def test_load_agent_spec():
    loader = ConfigLoader()
    spec = loader.load_agent_spec("research_assistant")
    assert spec.agent_id == "research_assistant"
    assert "web_search" in spec.allowed_tools


def test_load_workflow_spec():
    loader = ConfigLoader()
    spec = loader.load_workflow_spec("research_pipeline")
    assert spec.workflow_id == "research_pipeline"
    assert spec.start_at == "research_agent"
    assert spec.get_node("research_agent") is not None


def test_lead_workflows_keep_all_referenced_agents_and_tools():
    from core.tools.defaults import build_default_tool_registry

    loader = ConfigLoader()
    registry = build_default_tool_registry()
    for workflow_id in ("lead_generation_directory_pipeline", "lead_generation_split_pipeline", "velit_lead_generation_pipeline", "research_pipeline"):
        workflow = loader.load_workflow_spec(workflow_id)
        for node in workflow.nodes:
            if node.node_type == "agent":
                agent = loader.load_agent_spec(node.config['agent_id'])
                for name in agent.allowed_tools:
                    assert registry.get(name) is not None, f"{agent.agent_id} needs {name}"
            elif node.node_type == "tool":
                assert registry.get(node.config['tool_name']) is not None


def test_catalog_contains_lead_and_research_features_only():
    loader = ConfigLoader()
    agents = {item['agent_id'] for item in loader.list_agent_specs()}
    workflows = {item['workflow_id'] for item in loader.list_workflow_specs()}
    assert {'lead_gen_agent', 'research_assistant', 'email_writer_agent'} <= agents
    assert not agents.intersection({'campus_kernel_agent', 'customer_support_agent', 'task_manager_agent', 'script_writer_agent'})
    assert not workflows.intersection({'campus_learning_agent', 'learning_tutor', 'task_manager_pipeline', 'email_auto_ticketing_v1'})
