from pydantic import BaseModel, Field


class ContactResponse(BaseModel):
    id: str
    userId: str
    name: str
    phone: str
    priority: int


class ContactCreate(BaseModel):
    name: str
    phone: str
    priority: int | None = None


class ContactUpdate(BaseModel):
    priority: int | None = None
    name: str | None = None
    phone: str | None = None


class DeleteResponse(BaseModel):
    ok: bool = True
