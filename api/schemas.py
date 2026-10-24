"""Shared attachment schema for document and lead-research tools."""
from pydantic import BaseModel


class DocumentPayload(BaseModel):
    base64: str
    mimeType: str
    filename: str
    extension: str = ""
