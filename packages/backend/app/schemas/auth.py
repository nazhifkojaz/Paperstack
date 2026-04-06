import uuid
from pydantic import BaseModel, ConfigDict
from typing import Optional

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: Optional[str] = None

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class UserResponse(BaseModel):
    id: uuid.UUID
    email: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    storage_provider: str
    model_config = ConfigDict(from_attributes=True)
