"""Platform9 PCD MCP server — generic deployment tooling."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

# All paths resolved from the package root so the server works regardless of
# the process cwd (Claude Desktop sets cwd to a system directory).
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DOCS_DIR = _PACKAGE_ROOT / "docs"
_SOW_DOCS_DIR = _PACKAGE_ROOT / "SOW-docs"

import dacite
from mcp.server.fastmcp import FastMCP

from .docs_reader import read_docs_dir, read_file
from .generators.automation_builder import build_automation as _build_automation
from .generators.engagement_tracker import generate_engagement_tracker as _gen_tracker
from .generators.issues_tracker import generate_issues_tracker_from_text
from .generators.procedure_doc import (
    edit_procedure_doc as _edit_procedure,
    generate_procedure_doc as _gen_procedure,
)
from .generators.query_answerer import answer_query as _answer_query
from .models import SowDocument
from .output_writer import OutputWriter
from .parser import parse_sow as _parse_sow_file

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)

mcp = FastMCP("pcd-mcp-server")

_SOW_EXTENSIONS = {".pdf", ".docx", ".doc"}


def _load_sow(sow_doc_json: str) -> SowDocument:
    return dacite.from_dict(
        data_class=SowDocument,
        data=json.loads(sow_doc_json),
        config=dacite.Config(strict=False),
    )


def _resolve_sow_pdf(sow_filename: str) -> Path | str:
    """Locate a SOW file in SOW-docs/.

    Returns a Path when a file is unambiguously identified.
    Returns a str (user-facing message) when input is needed or nothing is found.
    """
    _SOW_DOCS_DIR.mkdir(parents=True, exist_ok=True)

    candidates = sorted(
        p for p in _SOW_DOCS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in _SOW_EXTENSIONS
    )

    if not candidates:
        return (
            f"No SOW documents found in {_SOW_DOCS_DIR}.\n"
            f"Please copy the SOW PDF into that directory and try again."
        )

    if sow_filename.strip():
        name = sow_filename.strip()
        # Exact match (case-insensitive)
        exact = [p for p in candidates if p.name.lower() == name.lower()]
        if exact:
            return exact[0]
        # Partial / substring match
        partial = [p for p in candidates if name.lower() in p.name.lower()]
        if len(partial) == 1:
            log.info("Matched '%s' to %s via partial name", name, partial[0].name)
            return partial[0]
        if len(partial) > 1:
            listed = "\n".join(f"  {i+1}. {p.name}" for i, p in enumerate(partial))
            return (
                f"Multiple SOW files match '{name}':\n{listed}\n"
                f"Please specify the exact filename."
            )
        # No match at all — show what is available
        available = "\n".join(f"  - {p.name}" for p in candidates)
        return (
            f"'{name}' not found in {_SOW_DOCS_DIR}.\n"
            f"Available files:\n{available}\n"
            f"Add the correct file to {_SOW_DOCS_DIR} or use one of the names above."
        )

    # No filename given
    if len(candidates) == 1:
        return candidates[0]

    listed = "\n".join(f"  {i+1}. {p.name}" for i, p in enumerate(candidates))
    return (
        f"Multiple SOW documents found in {_SOW_DOCS_DIR}. Which one should I use?\n"
        f"{listed}\n"
        f"Please specify the filename (e.g. 'use {candidates[0].name}')."
    )


@mcp.tool()
def parse_sow(sow_filename: str = "") -> str:
    """
    Parse a SOW PDF from the SOW-docs/ directory and return a structured JSON (SowDocument).

    SOW files must be placed in <repo>/SOW-docs/ before calling this tool.
    The returned JSON can be passed directly to generate_tracker with tracker_type="sow".

    Behaviour:
    - If sow_filename matches exactly one file in SOW-docs/ → parse and return JSON.
    - If sow_filename is empty and only one file exists → use it automatically.
    - If multiple files exist and none is specified → return a list and ask the user to pick.
    - If no files exist → return instructions to add the PDF to SOW-docs/.

    Args:
        sow_filename: Filename of the SOW in SOW-docs/ (e.g. "ValorC3_PF9_PCD_SOW.pdf").
                     Partial names are accepted when unambiguous. Leave empty when only
                     one SOW file is present.

    Returns:
        SowDocument as a JSON string, or a message requesting user action.
    """
    result = _resolve_sow_pdf(sow_filename)
    if isinstance(result, str):
        return result

    doc = _parse_sow_file(str(result))
    return json.dumps(doc.to_dict(), indent=2)


@mcp.tool()
def generate_tracker(
    customer_name: str,
    data: str = "",
    tracker_type: str = "issues",
    sow_filename: str = "",
    gdrive_folder_id: str = "",
) -> str:
    """
    Generate an Excel tracker workbook for a Platform9 PCD engagement.

    tracker_type options:
    - "issues":   4-sheet workbook (Summary, Issue_tracker, Bug_reported, Open Actions).
                  Provide issues text or JSON in `data`.
    - "sow":      SOW deliverables tracker. The SOW PDF is read from SOW-docs/.
                  Optionally provide `sow_filename` to select a specific file.
                  `data` may also be a SowDocument JSON string (from parse_sow output).
    - "combined": Both issue tracker and SOW deliverables in one call.

    SOW files must be placed in <repo>/SOW-docs/ before calling this tool with
    tracker_type "sow" or "combined".

    Args:
        customer_name:    Customer name for filenames and headers.
        data:             Issues text/JSON (for "issues") or SowDocument JSON (for "sow").
        tracker_type:     "issues" | "sow" | "combined" (default: "issues").
        sow_filename:     Filename in SOW-docs/ to use as the SOW source (e.g. "Acme_SOW.pdf").
                         Leave empty to auto-select when only one file is present.
        gdrive_folder_id: Google Drive folder ID where tracker files should be saved.
                         If provided, a '<customer_name>/Engagement tracker/' subfolder
                         structure is created inside this folder and files are uploaded there.
                         Leave empty to save to the local output/<customer_name>/ directory.

    Returns:
        Absolute path(s) to the written .xlsx file(s), or a message requesting user action.
        When gdrive_folder_id is provided the response includes step-by-step Google Drive
        upload instructions with encoded file content for Claude to execute.
    """
    writer = OutputWriter(customer_name)
    tracker_type = tracker_type.lower().strip()
    safe_name = customer_name.replace(" ", "_")

    def _resolve_sow_doc() -> SowDocument | str:
        """Load SowDocument from SOW-docs/ or from pre-parsed JSON in `data`."""
        if data.strip():
            try:
                return _load_sow(data)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # fall through to file lookup

        result = _resolve_sow_pdf(sow_filename)
        if isinstance(result, str):
            return result  # user-facing message
        return _parse_sow_file(str(result))

    generated_tracker_paths: list[Path] = []

    if tracker_type == "sow":
        sow = _resolve_sow_doc()
        if isinstance(sow, str):
            return sow
        xlsx_bytes = _gen_tracker(sow)
        out_path = writer.write_bytes(f"{safe_name}_engagement_tracker.xlsx", xlsx_bytes)
        generated_tracker_paths.append(out_path)
        result = str(out_path)

    elif tracker_type == "issues":
        xlsx_bytes = generate_issues_tracker_from_text(customer_name, data)
        out_path = writer.write_bytes(f"{safe_name}_issues_tracker.xlsx", xlsx_bytes)
        generated_tracker_paths.append(out_path)
        result = str(out_path)

    elif tracker_type == "combined":
        paths: list[str] = []

        issues_bytes = generate_issues_tracker_from_text(customer_name, data)
        issues_path = writer.write_bytes(f"{safe_name}_issues_tracker.xlsx", issues_bytes)
        generated_tracker_paths.append(issues_path)
        paths.append(str(issues_path))

        sow = _resolve_sow_doc()
        if isinstance(sow, str):
            paths.append(f"SOW tracker skipped: {sow}")
        else:
            sow_bytes = _gen_tracker(sow)
            sow_path = writer.write_bytes(f"{safe_name}_engagement_tracker.xlsx", sow_bytes)
            generated_tracker_paths.append(sow_path)
            paths.append(str(sow_path))

        result = "Generated tracker files:\n" + "\n".join(paths)

    else:
        raise ValueError(
            f"Unknown tracker_type {tracker_type!r}. Expected 'issues', 'sow', or 'combined'."
        )

    if gdrive_folder_id.strip() and generated_tracker_paths:
        result += _gdrive_upload_block(
            customer_name=customer_name,
            gdrive_parent_id=gdrive_folder_id.strip(),
            doc_files=[],
            tracker_files=generated_tracker_paths,
        )

    return result


_ENV_QUESTIONNAIRE = """\
To generate a complete procedure document for **{customer_name}**, provide two things below.

─────────────────────────────────────────────────────────────────
 1. ENVIRONMENT DETAILS  (blank fields → generic text, no placeholder markers)
─────────────────────────────────────────────────────────────────

Provide as a JSON string in the `env_values` parameter.

  Network
  ───────
  management_vip               — Management plane VIP IP (e.g. "10.0.1.10")
  management_fqdn              — FQDN for the management VIP (e.g. "pcd.corp.example.com")
  management_network_cidr      — Management network CIDR (e.g. "10.0.1.0/24")
  management_gateway           — Management network default gateway IP
  tenant_network_cidr          — Tenant / VM network CIDR (e.g. "10.1.0.0/16")
  provision_network_cidr       — MaaS / bare-metal provisioning CIDR
  live_migration_network_cidr  — Live migration network CIDR (if separate from management)
  dns_servers                  — DNS server IP(s), comma-separated
  ntp_servers                  — NTP server IP(s), comma-separated
  domain_name                  — DNS domain name (e.g. "corp.example.com")

  Hosts & Hardware
  ────────────────
  control_plane_hostnames      — PCD control-plane node hostnames, comma-separated
  hypervisor_hostnames         — Hypervisor hostnames or range (e.g. "hv01, hv02" or "hv01..hv20")
  maas_server_hostname         — MaaS server hostname or IP
  server_hardware_models       — Server models (e.g. "Dell PowerEdge R750, HP DL380 Gen10")
  hypervisor_count             — Total hypervisor count (e.g. "24")

  Integrations
  ────────────
  ipam_dhcp_system             — IPAM / DHCP system (e.g. "Infoblox 10.0.0.20" or "manual")
  storage_backend              — Storage (e.g. "Ceph RBD", "NetApp NFS 10.0.0.50", "Pure Storage iSCSI")
  identity_provider            — SSO / IdP (e.g. "Microsoft AD 10.0.0.10", "Okta SAML", or "none")
  monitoring_tool              — Monitoring (e.g. "Prometheus/Grafana", "Nagios", or "none")
  backup_tool                  — Backup (e.g. "Commvault", "Veeam", or "none")

  Platform9
  ─────────
  pcd_version                  — Target PCD version (e.g. "5.6.0")
  region_name                  — OpenStack region name (e.g. "RegionOne")

─────────────────────────────────────────────────────────────────
 2. OUTPUT LOCATION  (optional — defaults to local output/{customer_name}/)
─────────────────────────────────────────────────────────────────

Provide a Google Drive folder ID in `gdrive_folder_id` to save documents there.
The following structure will be created inside that folder:

  <your_folder>/
  └── {customer_name}/
      ├── Deployment_documentation/   ← procedure.md + procedure.pdf
      └── Engagement tracker/         ← engagement_tracker.xlsx + issues_tracker.xlsx

If omitted, all files are saved to the local output/{customer_name}/ directory.

─────────────────────────────────────────────────────────────────

Call with known values (pass {{}} for env_values to skip env collection entirely):

  build_procedure_doc(
    customer_name="{customer_name}",
    env_values='{{"management_vip": "10.0.1.10", "management_fqdn": "pcd.corp.example.com", "domain_name": "corp.example.com", ...}}',
    gdrive_folder_id="<GOOGLE_DRIVE_FOLDER_ID>"
  )

To generate a fully generic document saved locally only:

  build_procedure_doc(
    customer_name="{customer_name}",
    env_values='{{}}'
  )
"""


_GDRIVE_MIME = {
    ".md":   "text/markdown",
    ".pdf":  "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _gdrive_upload_block(
    customer_name: str,
    gdrive_parent_id: str,
    doc_files: list[Path],
    tracker_files: list[Path],
) -> str:
    """Return a structured Google Drive upload block appended to tool responses.

    Encodes each file as base64 and formats explicit create_file call parameters
    so Claude can execute them against the Google Drive MCP tool without any
    further file I/O.
    """
    lines: list[str] = [
        "\n\n---\n\n## Google Drive Upload\n\n",
        f"Parent folder ID: `{gdrive_parent_id}`\n\n",
        "Execute the following steps in order using the Google Drive tools:\n\n",
        f"**Step 1** — Create folder `{customer_name}` inside `{gdrive_parent_id}`\n",
        "```\n",
        f"create_file(title='{customer_name}', parentId='{gdrive_parent_id}',\n",
        "            mimeType='application/vnd.google-apps.folder')\n",
        "```\n",
        "Save the returned folder ID as **CUSTOMER_FOLDER_ID**.\n\n",
        "**Step 2** — Create subfolder `Deployment_documentation` inside CUSTOMER_FOLDER_ID\n",
        "```\n",
        "create_file(title='Deployment_documentation', parentId=CUSTOMER_FOLDER_ID,\n",
        "            mimeType='application/vnd.google-apps.folder')\n",
        "```\n",
        "Save the returned ID as **DEPLOY_FOLDER_ID**.\n\n",
        "**Step 3** — Create subfolder `Engagement tracker` inside CUSTOMER_FOLDER_ID\n",
        "```\n",
        "create_file(title='Engagement tracker', parentId=CUSTOMER_FOLDER_ID,\n",
        "            mimeType='application/vnd.google-apps.folder')\n",
        "```\n",
        "Save the returned ID as **TRACKER_FOLDER_ID**.\n\n",
    ]

    step = 4
    for path in doc_files:
        if not path.exists():
            log.warning("GDrive upload skipped — file not found: %s", path)
            continue
        mime = _GDRIVE_MIME.get(path.suffix.lower(), "application/octet-stream")
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        lines += [
            f"**Step {step}** — Upload `{path.name}` → `Deployment_documentation`\n",
            "```\n",
            f"create_file(title='{path.name}', parentId=DEPLOY_FOLDER_ID,\n",
            f"            contentMimeType='{mime}',\n",
            "            disableConversionToGoogleType=True,\n",
            f"            base64Content='{b64}')\n",
            "```\n\n",
        ]
        step += 1

    for path in tracker_files:
        if not path.exists():
            log.warning("GDrive upload skipped — file not found: %s", path)
            continue
        mime = _GDRIVE_MIME.get(path.suffix.lower(), "application/octet-stream")
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        lines += [
            f"**Step {step}** — Upload `{path.name}` → `Engagement tracker`\n",
            "```\n",
            f"create_file(title='{path.name}', parentId=TRACKER_FOLDER_ID,\n",
            f"            contentMimeType='{mime}',\n",
            "            disableConversionToGoogleType=True,\n",
            f"            base64Content='{b64}')\n",
            "```\n\n",
        ]
        step += 1

    return "".join(lines)


@mcp.tool()
def build_procedure_doc(
    customer_name: str,
    sow_filename: str = "",
    docs_dir: str = "",
    output_dir: str = "",
    env_values: str = "",
    gdrive_folder_id: str = "",
) -> str:
    """
    Build a Day0/Day1/Day2 deployment procedure document.

    Reference docs are read from docs/ (PCD architecture guides, MaaS guides, etc.).
    If sow_filename is provided, the matching SOW from SOW-docs/ is included as
    additional context so the procedure reflects the customer's specific scope.

    SOW files must be placed in <repo>/SOW-docs/ before using sow_filename.
    If sow_filename is empty and exactly one SOW exists in SOW-docs/, it is included
    automatically. If multiple SOW files exist, the tool asks which one to use.

    The output covers:
    - Day 0: Pre-deployment planning, infrastructure assessment, network/storage planning
    - Day 1: PCD installation, MaaS, hypervisor onboarding, all integrations
    - Day 2: VM migrations, monitoring, backup, runbooks, handover

    When env_values is empty the tool returns a questionnaire asking for environment
    details (IPs, FQDNs, hostnames, hardware) AND the preferred Google Drive output
    location. Call again with the collected answers to generate the document.

    Args:
        customer_name:    Customer or project name (used in headers and output filenames).
        sow_filename:     Filename in SOW-docs/ to include as SOW context (e.g. "Acme_SOW.pdf").
                         Leave empty to auto-select when only one is present.
        docs_dir:         Override for reference docs directory (default: repo docs/).
        output_dir:       Override for output directory (default: repo output/<customer_name>/).
        env_values:       JSON dict of environment-specific values to embed in the document.
                         Supported keys: management_vip, management_fqdn, management_network_cidr,
                         management_gateway, tenant_network_cidr, provision_network_cidr,
                         live_migration_network_cidr, dns_servers, ntp_servers, domain_name,
                         control_plane_hostnames, hypervisor_hostnames, maas_server_hostname,
                         server_hardware_models, hypervisor_count, ipam_dhcp_system,
                         storage_backend, identity_provider, monitoring_tool, backup_tool,
                         pcd_version, region_name.
                         Pass '{}' to skip collection and use generic descriptive text for all
                         unknown values (no placeholder markers).
                         Leave empty (default) to receive the questionnaire.
        gdrive_folder_id: Google Drive folder ID where documents should be saved.
                         If provided, a '<customer_name>/Deployment_documentation/' subfolder
                         structure is created inside this folder and files are uploaded there.
                         Leave empty to save to the local output/<customer_name>/ directory.

    Returns:
        Paths to the generated Markdown and PDF files (always written locally), the
        questionnaire when env_values is empty, or a message requesting user action.
        When gdrive_folder_id is provided the response includes step-by-step Google Drive
        upload instructions with encoded file content for Claude to execute.
    """
    # If no env_values supplied, return a questionnaire before generating
    if not env_values.strip():
        return _ENV_QUESTIONNAIRE.format(customer_name=customer_name)

    # Parse env_values JSON
    env_context: dict[str, str] = {}
    try:
        parsed = json.loads(env_values)
        if isinstance(parsed, dict):
            env_context = {str(k): str(v) for k, v in parsed.items() if v}
    except (json.JSONDecodeError, TypeError) as exc:
        log.warning("env_values JSON parse error: %s — proceeding without env context", exc)

    resolved_docs_dir = Path(docs_dir).resolve() if docs_dir.strip() else _DEFAULT_DOCS_DIR
    docs = read_docs_dir(resolved_docs_dir)

    # Include the SOW from SOW-docs/ if available
    sow_result = _resolve_sow_pdf(sow_filename)
    if isinstance(sow_result, Path):
        try:
            text = read_file(sow_result)
            docs.append({"filename": sow_result.name, "path": str(sow_result), "text": text})
            log.info("Included SOW %s (%d chars)", sow_result.name, len(text))
        except (ValueError, FileNotFoundError) as exc:
            log.warning("Could not read SOW %s: %s", sow_result, exc)
    elif sow_filename.strip():
        return sow_result
    else:
        if sow_result.startswith("Multiple SOW"):
            return sow_result
        log.info("No SOW found in SOW-docs/ — generating procedure from reference docs only")

    base_dir = Path(output_dir).resolve() if output_dir.strip() else None
    writer = OutputWriter(customer_name, base_dir=base_dir)

    md_path, pdf_path = _gen_procedure(
        customer_name=customer_name,
        docs=docs,
        output_writer=writer,
        env_context=env_context or None,
    )

    result = (
        f"Procedure document generated successfully.\n"
        f"Markdown: {md_path}\n"
        f"PDF:      {pdf_path}"
    )

    if gdrive_folder_id.strip():
        result += _gdrive_upload_block(
            customer_name=customer_name,
            gdrive_parent_id=gdrive_folder_id.strip(),
            doc_files=[md_path, pdf_path],
            tracker_files=[],
        )

    return result


@mcp.tool()
def edit_procedure_doc(
    customer_name: str,
    instructions: str,
    gdrive_folder_id: str = "",
) -> str:
    """
    Edit an existing procedure document using natural-language instructions.

    The document must already exist in output/<customer_name>/ (created by
    build_procedure_doc). The edited document overwrites the previous version.

    Supported edit types (can be combined in one call):
    - Remove a section:  "Remove the MaaS Setup section"
    - Add a section:     "Add a section on live migration network configuration
                          with OVN-specific steps after the Network Integration section"
    - Modify a section:  "Rewrite the Storage Integration section for Pure Storage iSCSI"
    - Combined:          "Remove MaaS Setup and add detailed live migration network
                          configuration steps covering VxLAN provider network setup"

    Editing is section-scoped: only the sections being changed are sent to Claude.
    Unchanged sections are preserved locally without any API round-trip.
    Token cost is proportional to the size of the changed sections, not the full document.

    Args:
        customer_name:    Customer name matching the existing build_procedure_doc run.
        instructions:     Natural-language description of the changes to make.
        gdrive_folder_id: Google Drive folder ID where the updated document should be saved.
                         If provided, the updated files are uploaded to the existing
                         '<customer_name>/Deployment_documentation/' folder structure
                         (created by build_procedure_doc if not already present).
                         Leave empty to save locally only.

    Returns:
        Paths to the updated Markdown and PDF files, or an error if the doc is not found.
        When gdrive_folder_id is provided the response includes step-by-step Google Drive
        upload instructions with encoded file content for Claude to execute.
    """
    safe_name = customer_name.replace(" ", "_")
    md_path = _PACKAGE_ROOT / "output" / safe_name / f"{safe_name}_procedure.md"

    if not md_path.exists():
        return (
            f"No procedure document found for '{customer_name}' at:\n  {md_path}\n"
            f"Run build_procedure_doc for this customer first, then edit."
        )

    existing_md = md_path.read_text(encoding="utf-8")
    writer = OutputWriter(customer_name)

    new_md, new_pdf = _edit_procedure(
        customer_name=customer_name,
        instructions=instructions,
        existing_md=existing_md,
        output_writer=writer,
    )

    result = (
        f"Procedure document updated.\n"
        f"Markdown: {new_md}\n"
        f"PDF:      {new_pdf}"
    )

    if gdrive_folder_id.strip():
        result += _gdrive_upload_block(
            customer_name=customer_name,
            gdrive_parent_id=gdrive_folder_id.strip(),
            doc_files=[new_md, new_pdf],
            tracker_files=[],
        )

    return result


@mcp.tool()
def answer_query(question: str) -> str:
    """
    Answer a Platform9 PCD technical question using Platform9 docs, KB, and OpenStack/K8s docs.

    Fetches relevant content from:
    - https://docs.platform9.com/private-cloud-director
    - https://platform9.com/kb/pcd and https://platform9.com/kb/pcd-ts
    - https://docs.openstack.org/epoxy/
    - https://kubernetes.io/docs/home/ (for K8s questions)

    Answers include citations to the source pages.

    Args:
        question: Technical question about Platform9 PCD, OpenStack, or Kubernetes

    Returns:
        Structured answer with citations.
    """
    return _answer_query(question)


@mcp.tool()
def build_automation(
    task_description: str,
    language: str = "python",
) -> str:
    """
    Generate automation scripts for Platform9 PCD and OpenStack operations.

    References Platform9 API docs and OpenStack Epoxy API references.
    Credentials are read from standard OpenStack environment variables:
    OS_AUTH_URL, OS_PROJECT_NAME, OS_USERNAME, OS_PASSWORD, OS_DOMAIN_NAME.

    Args:
        task_description: What the automation should do (e.g. "list all VMs across projects",
                          "create a security group with HTTP/HTTPS rules", "snapshot all volumes")
        language:         "python" (uses keystoneauth1/openstack SDK) or "bash" (uses curl/jq)

    Returns:
        Working automation script with inline documentation.
    """
    return _build_automation(task=task_description, language=language)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
