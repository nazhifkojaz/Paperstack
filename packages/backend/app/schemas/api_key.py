from datetime import datetime
from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    provider: str = Field(..., pattern=r"^(openai|anthropic|gemini|glm)$")
    api_key: str = Field(..., min_length=1)


class ApiKeyResponse(BaseModel):
    provider: str
    key_preview: str
    created_at: datetime
