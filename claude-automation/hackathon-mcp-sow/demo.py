"""
End-to-end demo of the SOW MCP server pipeline against NTT-SOW.pdf.

Without ANTHROPIC_API_KEY: uses a hand-built NTT SowDocument (from the PDF)
  and generates the engagement tracker (no LLM needed).
With ANTHROPIC_API_KEY: runs the full pipeline — parse_sow → generate_mop
  → generate_engagement_tracker.
"""

import json
import os
import sys
from pathlib import Path

SOW_PDF = Path(__file__).parent / "NTT-SOW.pdf"

# ── Build NTT SowDocument from the PDF (used when no API key is set) ──────────

NTT_DOC_DICT = {
    "customer": "NTT",
    "project_title": "Platform9 Private Cloud Director SaaS - Platinum Deployment and VM Migrations",
    "prepared_by": "Platform9 Strategic Customer Engineering - Customer Operations",
    "datacenters": [
        {"name": "Chennai", "role": "canary", "hypervisor_count": 4},
        {"name": "Mumbai", "role": "production", "hypervisor_count": 125},
        {"name": "Bengaluru", "role": "production", "hypervisor_count": 125},
    ],
    "phases": ["Canary", "Production", "MaaS", "Pilot Migration", "Full Migration", "Training"],
    "integrations": [
        "NetApp AFF C80 (fibre channel, all-flash)",
        "Commvault backup/restore",
        "Nagios / Checkmk via Prometheus",
        "IPAM / DHCP / DNS",
        "Microsoft AD (SSO/IDP)",
        "PCD API (workflow automation consultancy)",
    ],
    "vm_count": 1000,
    "hypervisor_count": 250,
    "migration_tool": "vJailbreak",
    "scope_sections": [
        {
            "id": "3.1",
            "title": "Assessment, Design & Build PCD — Canary Environment",
            "activities": [
                "Evaluate existing VMware environments, network topology, storage architecture, and compute resources",
                "Identify process gaps, integration requirements, and security/compliance considerations",
                "Recommend hardware allocation, node sizing, and network bandwidth for scalability",
                "Design, install, configure, and validate PCD in Chennai Canary DC with SaaS control plane (≤4 nodes)",
                "Use Canary as validation & testing bed for platform upgrades and configuration changes",
                "Enable systems integration testing with storage and backup/restore systems",
                "Produce and certify operational runbooks for production deployments",
            ],
            "deliverables": [
                {"id": "D-3.1-1", "section_id": "3.1", "title": "Infrastructure Assessment Report", "type": "report", "owner": "Platform9", "estimated_hours": 8.0},
                {"id": "D-3.1-2", "section_id": "3.1", "title": "Canary Environment Build MOP", "type": "mop", "owner": "Platform9", "estimated_hours": 24.0},
                {"id": "D-3.1-3", "section_id": "3.1", "title": "Canary Validation Report", "type": "report", "owner": "Platform9", "estimated_hours": 4.0},
            ],
        },
        {
            "id": "3.2",
            "title": "Assessment, Design & Implementation of Key Integrations",
            "activities": [
                "Integrate PCD with NetApp AFF C80 (fibre channel) for VM data disk and Image Library storage",
                "Integrate PCD with Commvault backup/restore infrastructure",
                "Configure monitoring integration with Nagios and/or Checkmk via Prometheus",
                "Integrate with customer IPAM, DHCP, and DNS solution",
                "Integrate SSO with Microsoft AD (IDP)",
                "Provide PCD API consultancy to enable customer workflow automation",
            ],
            "deliverables": [
                {"id": "D-3.2-1", "section_id": "3.2", "title": "Storage Integration MOP (NetApp AFF C80)", "type": "mop", "owner": "Platform9", "estimated_hours": 16.0},
                {"id": "D-3.2-2", "section_id": "3.2", "title": "Commvault Integration MOP", "type": "mop", "owner": "Platform9", "estimated_hours": 8.0},
                {"id": "D-3.2-3", "section_id": "3.2", "title": "Monitoring Integration Runbook", "type": "runbook", "owner": "Platform9", "estimated_hours": 6.0},
                {"id": "D-3.2-4", "section_id": "3.2", "title": "SSO / AD Integration MOP", "type": "mop", "owner": "Platform9", "estimated_hours": 6.0},
            ],
        },
        {
            "id": "3.3",
            "title": "Design & Build Production PCD Cluster — Mumbai & Bengaluru",
            "activities": [
                "Design and install a single PCD cluster spanning Mumbai and Bengaluru production DCs",
                "Onboard up to 250 hypervisor nodes into the PCD platform",
                "Implement all integrations as defined in section 3.2",
                "Configure HA, security policies, and performance optimisations",
            ],
            "deliverables": [
                {"id": "D-3.3-1", "section_id": "3.3", "title": "Production PCD Build MOP", "type": "mop", "owner": "Platform9", "estimated_hours": 40.0},
                {"id": "D-3.3-2", "section_id": "3.3", "title": "Production Environment Runbook", "type": "runbook", "owner": "Platform9", "estimated_hours": 16.0},
                {"id": "D-3.3-3", "section_id": "3.3", "title": "HA & Security Configuration Report", "type": "report", "owner": "Platform9", "estimated_hours": 8.0},
            ],
        },
        {
            "id": "3.4",
            "title": "Build Metal as a Service (MaaS) Infrastructure — All Environments",
            "activities": [
                "Define MaaS architecture: network boot workflows, ILO/IPMI integrations, security configurations",
                "Build MaaS automation pipelines to provision and onboard physical servers as PCD hypervisors",
                "Convert existing ESXi nodes to PCD hypervisors via remote network boot (ILO/IPMI)",
                "Deliver comprehensive MaaS operational documentation (provisioning, onboarding, troubleshooting)",
                "Provide knowledge transfer so customer can independently operate MaaS post-deployment",
            ],
            "deliverables": [
                {"id": "D-3.4-1", "section_id": "3.4", "title": "MaaS Architecture Design Document", "type": "report", "owner": "Platform9", "estimated_hours": 12.0},
                {"id": "D-3.4-2", "section_id": "3.4", "title": "MaaS Build & Provisioning MOP", "type": "mop", "owner": "Platform9", "estimated_hours": 24.0},
                {"id": "D-3.4-3", "section_id": "3.4", "title": "ESXi-to-PCD Conversion Runbook", "type": "runbook", "owner": "Platform9", "estimated_hours": 8.0},
            ],
        },
        {
            "id": "3.5",
            "title": "Perform Pilot VM Migrations",
            "activities": [
                "Execute pilot migrations of up to 10 VMs from VMware into the PCD Canary environment using vJailbreak",
                "Validate migration SOP accuracy, efficiency, and repeatability",
                "Test application functionality, performance, and compatibility post-migration",
                "Characterise expected downtime for warm vs cold migration strategies",
                "Incorporate lessons learned and refine the full-scale migration plan",
                "Identify operational gaps prior to initiating large-scale production migrations",
            ],
            "deliverables": [
                {"id": "D-3.5-1", "section_id": "3.5", "title": "Pilot Migration MOP (vJailbreak)", "type": "mop", "owner": "Platform9", "estimated_hours": 16.0},
                {"id": "D-3.5-2", "section_id": "3.5", "title": "Pilot Migration Validation Report", "type": "report", "owner": "Platform9", "estimated_hours": 4.0},
                {"id": "D-3.5-3", "section_id": "3.5", "title": "Refined Full-Scale Migration Plan", "type": "runbook", "owner": "Joint", "estimated_hours": 8.0},
            ],
        },
    ],
    "assumptions": [],
    "out_of_scope": [],
    "deliverables": [],
}


def run_demo() -> None:
    import dacite
    from sow_mcp.models import SowDocument
    from sow_mcp.generators.engagement_tracker import generate_engagement_tracker
    from sow_mcp.output_writer import OutputWriter

    has_api_key = bool(os.getenv("ANTHROPIC_API_KEY"))

    # ── Step 1: get SowDocument ───────────────────────────────────────────────
    if has_api_key and SOW_PDF.exists():
        print(f"[parse_sow] Parsing {SOW_PDF.name} via Claude...")
        from sow_mcp.parser import parse_sow
        doc = parse_sow(str(SOW_PDF))
        print(f"  → extracted {len(doc.scope_sections)} scope sections")
    else:
        print("[parse_sow] ANTHROPIC_API_KEY not set — using hand-built NTT SowDocument")
        doc = dacite.from_dict(SowDocument, NTT_DOC_DICT, config=dacite.Config(strict=False))

    print(f"\n  Customer      : {doc.customer}")
    print(f"  Project       : {doc.project_title}")
    print(f"  Datacenters   : {', '.join(f'{d.name} ({d.role})' for d in doc.datacenters)}")
    print(f"  VM count      : {doc.vm_count}")
    print(f"  Hypervisors   : {doc.hypervisor_count}")
    print(f"  Migration tool: {doc.migration_tool}")
    print(f"  Integrations  : {', '.join(doc.integrations)}")
    print(f"  Phases        : {' → '.join(doc.phases)}")
    print(f"  Scope sections: {len(doc.scope_sections)}")
    for s in doc.scope_sections:
        print(f"    {s.id}  {s.title}  ({len(s.deliverables)} deliverables)")

    writer = OutputWriter(doc.customer)

    # ── Step 2: engagement tracker (no LLM) ──────────────────────────────────
    print("\n[generate_engagement_tracker] Building Excel workbook...")
    xlsx = generate_engagement_tracker(doc)
    tracker_path = writer.write_bytes(f"{doc.customer}_engagement_tracker.xlsx", xlsx)
    print(f"  → {tracker_path}")

    # ── Step 3: MOP (LLM required) ────────────────────────────────────────────
    if has_api_key:
        from sow_mcp.generators.mop import generate_mop
        print("\n[generate_mop] Generating MOP for all sections via Claude...")
        mop_md = generate_mop(doc)
        mop_path = writer.write_text(f"{doc.customer}_MOP.md", mop_md)
        print(f"  → {mop_path}")
        print(f"\n--- MOP preview (first 1500 chars) ---\n")
        print(mop_md[:1500])
    else:
        print("\n[generate_mop] Skipped — set ANTHROPIC_API_KEY to generate MOP")

    # ── Step 4: SowDocument JSON ──────────────────────────────────────────────
    json_path = writer.write_text(
        f"{doc.customer}_sow.json", json.dumps(doc.to_dict(), indent=2)
    )
    print(f"\n[SowDocument JSON] → {json_path}")
    print("\nDone. Output directory:", writer.dir)


if __name__ == "__main__":
    run_demo()
