import base64
from pathlib import Path
from typing import Dict, Any, Optional

from core.adapters.base import BaseLLMAdapter, LLMResponse


class FileAnalyzer:
    
    SUPPORTED_MIME_TYPES = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".pdf": "application/pdf"
    }
    
    def __init__(self, adapter: BaseLLMAdapter):
        self.adapter = adapter
    
    async def analyze(
        self,
        document: Dict[str, Any],
        instruction: str,
        user_query: Optional[str] = None
    ) -> LLMResponse:
        prompt = self._build_analysis_prompt(instruction, user_query)
        
        images = [document]
        
        return await self.adapter.generate_with_vision(
            prompt=prompt,
            images=images
        )
    
    async def extract_text(self, document: Dict[str, Any]) -> str:
        instruction = "Extract all text from this document. Preserve structure and formatting."
        response = await self.analyze(document, instruction)
        return response.text
    async def analyze_from_path(
        self,
        file_path: str,
        instruction: str
    ) -> LLMResponse:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        with open(path, "rb") as f:
            data = f.read()
        
        base64_data = base64.b64encode(data).decode("utf-8")
        mime_type = self.SUPPORTED_MIME_TYPES.get(path.suffix.lower(), "image/png")
        
        document = {
            "base64": base64_data,
            "mimeType": mime_type,
            "filename": path.name
        }
        
        return await self.analyze(document, instruction)
    
    def _build_analysis_prompt(
        self,
        instruction: str,
        user_query: Optional[str] = None
    ) -> str:
        if user_query:
            return f"""{instruction}

User's question: "{user_query}"

Analyze the document and respond to the user's question."""
        
        return instruction
