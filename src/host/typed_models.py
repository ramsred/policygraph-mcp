from __future__ import annotations
from typing import List
from pydantic import BaseModel, Field

# ---------- SharePoint ----------

class SharePointSearchHit(BaseModel):
    doc_id: str
    title: str
    snippet: str

class SharePointSearchResult(BaseModel):
    query: str
    results: List[SharePointSearchHit] = Field(default_factory=list)

class SharePointDoc(BaseModel):
    doc_id: str
    content: str


# ---------- ServiceNow ----------

class ServiceNowTicketHit(BaseModel):
    ticket_id: str
    title: str
    snippet: str

class ServiceNowSearchResult(BaseModel):
    query: str
    results: List[ServiceNowTicketHit] = Field(default_factory=list)

class ServiceNowTicket(BaseModel):
    ticket_id: str
    content: str


# ---------- Policy KB ----------

class PolicyKBSearchHit(BaseModel):
    policy_id: str
    title: str
    snippet: str

class PolicyKBSearchResult(BaseModel):
    query: str
    results: List[PolicyKBSearchHit] = Field(default_factory=list)

class PolicyDoc(BaseModel):
    policy_id: str
    content: str