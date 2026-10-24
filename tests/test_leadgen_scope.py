import asyncio

from qdrant_client import QdrantClient, models

from core.retrieval.qdrant_client import QdrantRetriever
from core.tools.defaults import build_default_tool_registry


def test_routes_expose_lead_features_without_legacy_features():
    from api.main import app

    paths = app.openapi()['paths']
    assert any(path.startswith('/api/leads/') for path in paths)
    assert any(path.startswith('/api/email-verification/') for path in paths)
    assert any(path.startswith('/api/velit-batch/') for path in paths)
    assert '/api/agent/run' in paths
    assert not any(path.startswith(('/api/learning/', '/api/campus/', '/api/image/')) for path in paths)
    assert '/api/blocks/extract/image-metadata' not in paths


def test_tools_keep_research_and_enrichment_without_legacy_tools():
    names = {tool.name for tool in build_default_tool_registry().all_tools()}
    assert {'web_search', 'linkedin_research', 'lead_quality_check', 'file_analyze', 'rag_search'} <= names
    assert 'image_generate' not in names
    assert not any(name.startswith(('todo_', 'aurika_')) for name in names)


def test_lead_sheet_setup_does_not_create_task_worksheets():
    from types import SimpleNamespace
    from core.services.todo_sheet_store import TodoSheetStore

    store = TodoSheetStore(sheet_id='test-sheet')
    requested = []
    worksheet = SimpleNamespace(row_values=lambda index: list(store.LEAD_HEADERS))
    spreadsheet = SimpleNamespace(title='Aryan Leads')
    store._init_clients = lambda: None
    store._gspread_client = SimpleNamespace(open_by_key=lambda sheet_id: spreadsheet)
    store._ensure_worksheet = lambda sheet, title: requested.append(title) or worksheet
    result = store.ensure_store()
    assert requested == [store.leads_worksheet_name]
    assert result['leads_worksheet'] == store.leads_worksheet_name
    assert result['lead_headers'] == store.LEAD_HEADERS
    assert 'tasks_worksheet' not in result


def test_retrieval_preserves_business_metadata_and_deduplicates_documents():
    class Embeddings:
        async def embed(self, text):
            return [1.0, 0.0, 0.0]

    client = QdrantClient(location=':memory:')
    try:
        client.create_collection('knowledge', vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE))
        client.upsert('knowledge', points=[
            models.PointStruct(id=1, vector=[1.0, 0.0, 0.0], payload={
                'content': 'Solar installer in Jaipur.', 'metadata': {'company_name': 'Example Solar', 'industry': 'solar'}}),
            models.PointStruct(id=2, vector=[1.0, 0.0, 0.0], payload={
                'content': 'Solar installer in Jaipur.', 'metadata': {'company_name': 'Example Solar', 'industry': 'solar'}}),
        ])
        retriever = QdrantRetriever.__new__(QdrantRetriever)
        retriever.client = client
        retriever.collection_name = 'knowledge'
        retriever.embedding_service = Embeddings()
        retriever.top_k = 5
        results = asyncio.run(retriever.search('solar installer', {}))
        assert len(results) == 1
        assert results[0]['metadata']['company_name'] == 'Example Solar'
        assert results[0]['score'] > 0.99
    finally:
        client.close()
