from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Datacenter:
    name: str
    role: str  # "canary" | "production"
    hypervisor_count: int | None = None


@dataclass
class Deliverable:
    id: str
    section_id: str
    title: str
    type: str   # "mop" | "runbook" | "report" | "training" | "configuration" | "tracker"
    owner: str  # "Platform9" | "Customer" | "Joint"
    estimated_hours: float | None = None


@dataclass
class ScopeSection:
    id: str
    title: str
    activities: list[str] = field(default_factory=list)
    deliverables: list[Deliverable] = field(default_factory=list)


@dataclass
class SowDocument:
    customer: str
    project_title: str
    prepared_by: str
    datacenters: list[Datacenter] = field(default_factory=list)
    phases: list[str] = field(default_factory=list)
    scope_sections: list[ScopeSection] = field(default_factory=list)
    integrations: list[str] = field(default_factory=list)
    vm_count: int | None = None
    hypervisor_count: int | None = None
    migration_tool: str | None = None
    assumptions: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    deliverables: list[Deliverable] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocChunk:
    filename: str
    text: str
    source_path: str | None = None
    source_url: str | None = None
