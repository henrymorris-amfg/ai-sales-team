from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Finding:
    rule_id: str
    entity_type: str
    entity_id: str
    owner_id: Optional[int]
    severity: str
    confidence: float
    summary: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    suggested_action: str = ""


@dataclass
class Deal:
    id: int
    title: str
    owner_id: Optional[int]
    status: str
    pipeline_id: Optional[int]
    pipeline_name: str
    stage_id: Optional[int]
    stage_name: str
    value: Optional[float]
    next_activity_date: Optional[str]
    last_activity_date: Optional[str]
    expected_close_date: Optional[str]
    org_id: Optional[int]
    person_id: Optional[int]
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Person:
    id: int
    name: str
    owner_id: Optional[int]
    emails: List[str]
    org_id: Optional[int]
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Organisation:
    id: int
    name: str
    owner_id: Optional[int]
    website: Optional[str]
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Activity:
    id: int
    subject: str
    type: Optional[str]
    owner_id: Optional[int]
    due_date: Optional[str]
    done: bool
    deal_id: Optional[int]
    person_id: Optional[int]
    org_id: Optional[int]
    lead_id: Optional[str]
    raw: Dict[str, Any] = field(default_factory=dict)
