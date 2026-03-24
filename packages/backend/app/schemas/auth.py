import uuid
from pydantic import BaseModel
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
    github_id: int
    github_login: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    repo_created: bool

    class Config:
        from_attributes = True
