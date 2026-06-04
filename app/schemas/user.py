from pydantic import BaseModel, EmailStr, Field


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    emergencyPhrase: str | None = None
    isAdmin: bool = False


class AuthRegister(BaseModel):
    name: str
    email: EmailStr
    password: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = ""
    name: str | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    emergencyPhrase: str | None = None


class ErrorResponse(BaseModel):
    error: str = Field(..., examples=["Not authenticated"])
