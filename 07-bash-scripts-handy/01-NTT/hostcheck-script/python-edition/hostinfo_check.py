#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import grp
import json
import os
import pwd
import re
import shlex
import socket
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import quote, urlsplit
from xml.sax.saxutils import escape

try:
    from rich import box
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print(
        "ERROR: the 'rich' module is required; install it with "
        "'python3 -m pip install rich'.",
        file=sys.stderr,
    )
    raise SystemExit(2)


DEFAULT_GLANCE_MOUNT = Path("/var/opt/imagelibrary")
HOST_LIST_PATH = Path("/tmp/host-list.json")
HOST_LIST_CREATED_PATH: Path | None = None
CLUSTER_LIST_PATH = Path("/tmp/cluster-list.json")
CLUSTER_LIST_CREATED_PATH: Path | None = None
COMMAND_TIMEOUT = 15
GIB = 1024**3
SUPPORTED_ACTIONS = {
    "check-sudoers",
    "check-mpath-orphan",
    "list-nvme-vm",
    "list-vm-mpath",
    "check-glance-mount",
    "check-control-plane",
}

REQUIRED_OPENSTACK_ENVIRONMENT = ("OS_USERNAME", "OS_PASSWORD", "OS_AUTH_URL")

@dataclass(frozen=True)
class CommandResult:
    """Captured result from an external command."""

    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


@dataclass(frozen=True)
class CheckResult:
    """One row in a host-check report."""

    name: str
    status: str
    output: str = ""
    actual: str | None = None
    expected: str | None = None
    backend_name: str | None = None
    backend_sections: tuple[str, ...] | None = None
    hostconfig_name: str | None = None
    cluster_name: str | None = None


@dataclass(frozen=True)
class OperatingSystem:
    """Distribution metadata and package-management family."""

    os_id: str
    version_id: str
    pretty_name: str
    package_family: str


def run_command(
    args: Sequence[str],
    *,
    timeout: int = COMMAND_TIMEOUT,
    input_text: str | None = None,
    environment: dict[str, str] | None = None,
) -> CommandResult:
    """Run an external command without invoking a shell."""

    command = tuple(str(arg) for arg in args)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            input=input_text,
            timeout=timeout,
            env=environment,
        )
    except FileNotFoundError:
        return CommandResult(command, 127, "", f"command not found: {command[0]}")
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        return CommandResult(command, 124, stdout, stderr, timed_out=True)

    return CommandResult(
        command,
        completed.returncode,
        completed.stdout.strip(),
        completed.stderr.strip(),
    )


def required_environment_value(variable_name: str) -> str:
    """Return a required non-empty environment value without exposing it."""

    value = os.environ.get(variable_name, "").strip()
    if not value:
        raise RuntimeError(
            f"{variable_name} is not defined or is empty; export the OpenStack "
            "RC file before running check-control-plane"
        )
    return value


def control_plane_api_url(auth_url: str) -> str:
    """Build the ResMgr endpoint from the origin in OS_AUTH_URL."""

    parsed_url = urlsplit(auth_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise RuntimeError("OS_AUTH_URL must be a valid HTTP or HTTPS URL")
    return f"{parsed_url.scheme}://{parsed_url.netloc}/resmgr/v2/blueprint/"


def storage_backend_rows(
    blueprint_name: str,
    storage_backends: dict[object, object],
) -> list[CheckResult]:
    """Return one row for every backend and all of its configured sections."""

    rows: list[CheckResult] = []
    for backend_name, configured_sections in sorted(
        storage_backends.items(), key=lambda item: str(item[0]).casefold()
    ):
        if not isinstance(configured_sections, dict):
            rows.append(
                CheckResult(
                    name=blueprint_name,
                    status="FAIL",
                    output="backend configuration must be a JSON object",
                    backend_name=str(backend_name),
                    backend_sections=(),
                )
            )
            continue

        section_names = tuple(
            sorted(
                (str(section_name) for section_name in configured_sections),
                key=str.casefold,
            )
        )
        rows.append(
            CheckResult(
                name=blueprint_name,
                status="OK" if section_names else "WARN",
                output="-" if section_names else "no backend sections configured",
                backend_name=str(backend_name),
                backend_sections=section_names,
            )
        )
    return rows


def api_origin(auth_url: str) -> str:
    """Return the scheme and authority from OS_AUTH_URL."""

    parsed_url = urlsplit(auth_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise RuntimeError("OS_AUTH_URL must be a valid HTTP or HTTPS URL")
    return f"{parsed_url.scheme}://{parsed_url.netloc}"


def fetch_api_json(
    token: str,
    url: str,
    query_name: str,
) -> tuple[object | None, CheckResult | None]:
    """Fetch and decode one authenticated JSON API response."""

    curl_result = run_command(
        [
            "curl",
            "--fail-with-body",
            "--silent",
            "--show-error",
            "--request",
            "GET",
            "--header",
            f"X-Auth-Token: {token}",
            "--header",
            "Content-Type: application/json",
            url,
        ]
    )
    if curl_result.returncode != 0:
        return None, result(
            query_name,
            "FAIL",
            curl_result.stderr or curl_result.stdout or "request failed",
        )
    if not curl_result.stdout:
        return None, None

    try:
        return json.loads(curl_result.stdout), None
    except json.JSONDecodeError as error:
        return None, result(
            query_name,
            "FAIL",
            f"control plane returned invalid JSON: {error}",
        )


def blueprint_rows(payload: object | None) -> list[CheckResult]:
    """Build blueprint and storage-backend report rows."""

    if payload is None or payload == []:
        return [
            result(
                "Control plane blueprints",
                "WARN",
                "No blueprint configuration present",
            )
        ]

    if not isinstance(payload, list):
        return [
            result(
                "Control plane blueprints",
                "FAIL",
                "expected the control plane response to be a JSON array",
            )
        ]

    rows: list[CheckResult] = []
    for blueprint in payload:
        if not isinstance(blueprint, dict):
            return [
                result(
                    "Control plane blueprints",
                    "FAIL",
                    "each blueprint in the response must be a JSON object",
                )
            ]

        name = blueprint.get("name") or "<unnamed>"
        storage_backends = blueprint.get("storageBackends", {})
        if storage_backends is None:
            storage_backends = {}
        if not isinstance(storage_backends, dict):
            return [
                result(
                    str(name),
                    "FAIL",
                    "storageBackends must be a JSON object",
                )
            ]

        configured_storage_rows = storage_backend_rows(str(name), storage_backends)
        if not configured_storage_rows:
            rows.append(
                CheckResult(
                    name=str(name),
                    status="WARN",
                    output="no backend storage configuration present",
                    backend_name="-",
                    backend_sections=(),
                )
            )
            continue
        rows.extend(configured_storage_rows)
    return rows


def host_config_rows(
    payload: object | None,
) -> tuple[list[CheckResult], list[tuple[str, str]]]:
    """Build host-config rows and return profile-to-network-label associations."""

    if payload is None or payload == []:
        return (
            [
                result(
                    "Hostconfig profiles",
                    "WARN",
                    "No hostconfig profile present in the blueprint",
                )
            ],
            [],
        )
    if not isinstance(payload, list):
        return (
            [
                result(
                    "Hostconfig profiles",
                    "FAIL",
                    "expected the hostconfig response to be a JSON array",
                )
            ],
            [],
        )

    rows: list[CheckResult] = []
    profile_labels: list[tuple[str, str]] = []
    for host_config in payload:
        if not isinstance(host_config, dict):
            return (
                [
                    result(
                        "Hostconfig profiles",
                        "FAIL",
                        "each hostconfig profile must be a JSON object",
                    )
                ],
                [],
            )
        profile_name = str(host_config.get("name") or "<unnamed>")
        network_labels = host_config.get("networkLabels", {})
        if network_labels is None:
            network_labels = {}
        if not isinstance(network_labels, dict):
            rows.append(
                result(profile_name, "FAIL", "networkLabels must be a JSON object")
            )
            continue

        label_mappings = [
            f"{label_name} -> {interface_name}"
            for label_name, interface_name in sorted(
                network_labels.items(), key=lambda item: str(item[0]).casefold()
            )
        ]
        profile_labels.extend(
            (profile_name, str(label_name)) for label_name in network_labels
        )
        rows.append(
            result(
                profile_name,
                "OK" if label_mappings else "WARN",
                (
                    "\n".join(label_mappings)
                    if label_mappings
                    else "no network labels configured"
                ),
            )
        )
    return rows, profile_labels


def host_config_names_by_id(payload: object | None) -> dict[str, str]:
    """Map each non-empty hostconfig ID to its profile name."""

    if not isinstance(payload, list):
        return {}

    names_by_id: dict[str, str] = {}
    for host_config in payload:
        if not isinstance(host_config, dict):
            continue
        host_config_id = str(host_config.get("id") or "").strip()
        if not host_config_id:
            continue
        names_by_id[host_config_id] = str(
            host_config.get("name") or "<unnamed>"
        )
    return names_by_id


def write_host_list(payload: object, destination: Path = HOST_LIST_PATH) -> None:
    """Write the fetched hosts payload to a private temporary JSON file."""

    global HOST_LIST_CREATED_PATH

    open_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        open_flags |= os.O_NOFOLLOW
    file_descriptor = os.open(destination, open_flags, 0o600)
    HOST_LIST_CREATED_PATH = destination
    try:
        os.fchmod(file_descriptor, 0o600)
        host_file = os.fdopen(file_descriptor, "w", encoding="utf-8")
    except Exception:
        os.close(file_descriptor)
        raise
    with host_file:
        json.dump(payload, host_file, ensure_ascii=False)
        host_file.write("\n")


def remove_host_list() -> None:
    """Delete the hosts file only when this process created it."""

    global HOST_LIST_CREATED_PATH

    if HOST_LIST_CREATED_PATH is None:
        return
    HOST_LIST_CREATED_PATH.unlink(missing_ok=True)
    HOST_LIST_CREATED_PATH = None


def write_cluster_list(
    payload: object,
    destination: Path = CLUSTER_LIST_PATH,
) -> None:
    """Write the fetched clusters payload to a private temporary JSON file."""

    global CLUSTER_LIST_CREATED_PATH

    open_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        open_flags |= os.O_NOFOLLOW
    file_descriptor = os.open(destination, open_flags, 0o600)
    CLUSTER_LIST_CREATED_PATH = destination
    try:
        os.fchmod(file_descriptor, 0o600)
        cluster_file = os.fdopen(file_descriptor, "w", encoding="utf-8")
    except Exception:
        os.close(file_descriptor)
        raise
    with cluster_file:
        json.dump(payload, cluster_file, ensure_ascii=False)
        cluster_file.write("\n")


def remove_cluster_list() -> None:
    """Delete the clusters file only when this process created it."""

    global CLUSTER_LIST_CREATED_PATH

    if CLUSTER_LIST_CREATED_PATH is None:
        return
    CLUSTER_LIST_CREATED_PATH.unlink(missing_ok=True)
    CLUSTER_LIST_CREATED_PATH = None


def cluster_names_by_host_id(payload: object) -> dict[str, str]:
    """Map host UUIDs in cluster hostlists to their cluster names."""

    if not isinstance(payload, list):
        return {}

    names_by_host_id: dict[str, str] = {}
    for cluster in payload:
        if not isinstance(cluster, dict):
            continue
        cluster_name = str(cluster.get("name") or "<unnamed>")
        host_ids = cluster.get("hostlist")
        if not isinstance(host_ids, list):
            continue
        for host_id in host_ids:
            normalized_host_id = str(host_id or "").strip()
            if normalized_host_id:
                names_by_host_id[normalized_host_id] = cluster_name
    return names_by_host_id


def host_list_rows(
    source: Path,
    cluster_source: Path,
    host_config_names: dict[str, str],
) -> list[CheckResult]:
    """Resolve hostconfig and cluster names for hosts read from JSON files."""

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except OSError as error:
        return [result("Hosts", "FAIL", f"cannot read {source}: {error}")]
    except json.JSONDecodeError as error:
        return [result("Hosts", "FAIL", f"invalid hosts JSON: {error}")]

    try:
        cluster_payload = json.loads(cluster_source.read_text(encoding="utf-8"))
    except OSError as error:
        return [result("Hosts", "FAIL", f"cannot read {cluster_source}: {error}")]
    except json.JSONDecodeError as error:
        return [result("Hosts", "FAIL", f"invalid clusters JSON: {error}")]

    if not isinstance(payload, list):
        return [result("Hosts", "FAIL", "hosts response must be a JSON array")]
    if not isinstance(cluster_payload, list):
        return [result("Hosts", "FAIL", "clusters response must be a JSON array")]
    if not payload:
        return [result("Hosts", "WARN", "no hosts returned by the control plane")]

    cluster_names = cluster_names_by_host_id(cluster_payload)
    rows: list[CheckResult] = []
    for host in payload:
        if not isinstance(host, dict):
            rows.append(result("<invalid host>", "FAIL", "host must be a JSON object"))
            continue

        info = host.get("info")
        hostname = (
            str(info.get("hostname") or "<unknown>")
            if isinstance(info, dict)
            else "<unknown>"
        )
        host_id = str(host.get("id") or "").strip()
        host_config_id = str(host.get("hostconfig_id") or "").strip()
        if not host_config_id:
            host_config_name = "<unset>"
            status = "WARN"
        elif host_config_id in host_config_names:
            host_config_name = host_config_names[host_config_id]
            status = "OK"
        else:
            host_config_name = f"<unresolved: {host_config_id}>"
            status = "FAIL"

        rows.append(
            CheckResult(
                name=hostname,
                status=status,
                hostconfig_name=host_config_name,
                cluster_name=cluster_names.get(host_id, "<unset>"),
            )
        )
    return rows


def provider_network_rows(
    token: str,
    origin: str,
    profile_labels: Sequence[tuple[str, str]],
) -> list[CheckResult]:
    """Return one provider-network summary row per unique network label."""

    networks_by_label: dict[str, object | CheckResult] = {}
    for _, label_name in profile_labels:
        if label_name in networks_by_label:
            continue
        encoded_label = quote(label_name, safe="")
        url = (
            f"{origin}/neutron/v2.0/networks?"
            f"provider:physical_network={encoded_label}"
        )
        payload, error = fetch_api_json(
            token,
            url,
            f"Provider networks for {label_name}",
        )
        networks_by_label[label_name] = error if error is not None else payload

    rows: list[CheckResult] = []
    for label_name, response in networks_by_label.items():
        network_blocks: list[str] = []
        if isinstance(response, CheckResult):
            rows.append(result(label_name, "FAIL", response.output))
            continue
        if response is None:
            continue
        if not isinstance(response, dict) or not isinstance(
            response.get("networks"), list
        ):
            rows.append(
                result(
                    label_name,
                    "FAIL",
                    "provider network response must contain a networks array",
                )
            )
            continue

        seen_networks: set[tuple[str, str]] = set()
        for network in response["networks"]:
            if (
                not isinstance(network, dict)
                or network.get("provider:physical_network") != label_name
            ):
                continue
            network_name = str(network.get("name") or "<unnamed>")
            tenant_id = str(network.get("tenant_id") or "<unset>")
            network_key = (network_name, tenant_id)
            if network_key in seen_networks:
                continue
            seen_networks.add(network_key)
            network_blocks.append(
                f"Network: {network_name}\nTenant ID: {tenant_id}"
            )

        if network_blocks:
            rows.append(result(label_name, "OK", "\n\n".join(network_blocks)))
    return rows or [
        result(
            "Provider networks",
            "WARN",
            "no provider network present/configured",
        )
    ]


def control_plane_reports(
    *, include_hosts: bool = False, region: str | None = None
) -> list[tuple[str, list[CheckResult]]]:
    """Return blueprint, host-config, and provider-network report sections."""

    environment = {
        variable_name: required_environment_value(variable_name)
        for variable_name in REQUIRED_OPENSTACK_ENVIRONMENT
    }
    command_environment = None
    if region is not None:
        command_environment = os.environ.copy()
        command_environment["OS_REGION_NAME"] = region
        region_result = run_command(
            ["openstack", "region", "show", region],
            environment=command_environment,
        )
        if region_result.returncode != 0:
            detail = (
                region_result.stderr
                or region_result.stdout
                or "region lookup failed"
            )
            return [
                (
                    "CONTROL PLANE",
                    [result(f"OpenStack region {region}", "FAIL", detail)],
                )
            ]
    token_result = run_command(
        ["openstack", "token", "issue", "-c", "id", "-f", "value"],
        environment=command_environment,
    )
    if token_result.returncode != 0 or not token_result.stdout:
        detail = token_result.stderr or token_result.stdout or "empty token returned"
        return [("CONTROL PLANE", [result("OpenStack token", "FAIL", detail)])]

    origin = api_origin(environment["OS_AUTH_URL"])
    blueprint_payload, blueprint_error = fetch_api_json(
        token_result.stdout,
        f"{origin}/resmgr/v2/blueprint/",
        "Control plane blueprints",
    )
    blueprint_results = (
        [blueprint_error]
        if blueprint_error is not None
        else blueprint_rows(blueprint_payload)
    )

    host_config_payload, host_config_error = fetch_api_json(
        token_result.stdout,
        f"{origin}/resmgr/v2/hostconfigs",
        "Hostconfig profiles",
    )
    if host_config_error is not None:
        host_config_results = [host_config_error]
        profile_labels: list[tuple[str, str]] = []
        host_config_names: dict[str, str] = {}
    else:
        host_config_results, profile_labels = host_config_rows(host_config_payload)
        host_config_names = host_config_names_by_id(host_config_payload)

    reports = [
        ("STORAGE BACKEND CONFIGURATION", blueprint_results),
        ("HOSTCONFIG NETWORK LABELS", host_config_results),
        (
            "PROVIDER NETWORKS",
            provider_network_rows(token_result.stdout, origin, profile_labels),
        ),
    ]
    if not include_hosts:
        return reports

    cluster_payload, cluster_error = fetch_api_json(
        token_result.stdout,
        f"{origin}/resmgr/v2/clusters",
        "Control plane clusters",
    )
    if cluster_error is not None:
        reports.append(("HOSTS", [cluster_error]))
        return reports

    host_payload, host_error = fetch_api_json(
        token_result.stdout,
        f"{origin}/resmgr/v2/hosts",
        "Control plane hosts",
    )
    if host_error is not None:
        host_results = [host_error]
    else:
        try:
            write_cluster_list(cluster_payload)
            write_host_list(host_payload)
            # Release decoded copies before loading potentially large lists.
            cluster_payload = None
            host_payload = None
            host_results = host_list_rows(
                HOST_LIST_PATH,
                CLUSTER_LIST_PATH,
                host_config_names,
            )
        except OSError as error:
            host_results = [
                result("Hosts", "FAIL", f"cannot write temporary JSON: {error}")
            ]
    reports.append(("HOSTS", host_results))
    return reports


def command_path(command: str) -> str | None:
    """Resolve a command by asking the host shell-independent utility."""

    result = run_command(["which", command])
    return result.stdout.splitlines()[0] if result.returncode == 0 else None


def read_text(path: Path) -> str | None:
    """Return readable text, or None when a file cannot be read."""

    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return None


def result(name: str, status: str, output: str = "") -> CheckResult:
    """Create a normalized report row."""

    return CheckResult(name=name, status=status, output=output.strip())


def comparison_result(
    name: str,
    status: str,
    actual: object | None,
    expected: object,
    output: str = "",
) -> CheckResult:
    """Create a report row with structured actual and expected values."""

    return CheckResult(
        name=name,
        status=status,
        output=output.strip(),
        actual="unset" if actual is None or actual == "" else str(actual),
        expected=str(expected),
    )


def detect_operating_system() -> OperatingSystem:
    """Detect a supported distribution using /etc/os-release."""

    content = read_text(Path("/etc/os-release"))
    if content is None:
        raise RuntimeError(
            "/etc/os-release is missing or unreadable; cannot select a package backend"
        )

    values: dict[str, str] = {}
    for line in content.splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')

    os_id = values.get("ID", "")
    version_id = values.get("VERSION_ID", "")
    pretty_name = values.get("PRETTY_NAME", f"{os_id or 'unknown'} {version_id}")
    if os_id == "ubuntu":
        family = "deb"
        required_command = "dpkg-query"
    elif os_id in {"rocky", "rhel", "almalinux"}:
        family = "rpm"
        required_command = "rpm"
    else:
        raise RuntimeError(
            f"unsupported operating system ID {os_id or 'unset'}; supported IDs: "
            "ubuntu, rocky, rhel, almalinux"
        )

    if command_path(required_command) is None:
        raise RuntimeError(f"{os_id} detected but {required_command} is unavailable")
    return OperatingSystem(os_id, version_id, pretty_name, family)


def package_is_installed(package_name: str, operating_system: OperatingSystem) -> bool:
    """Return whether a distribution package is installed."""

    if operating_system.package_family == "deb":
        query = run_command(
            ["dpkg-query", "-W", "-f=${db:Status-Abbrev}", package_name]
        )
        return query.returncode == 0 and query.stdout == "ii"
    return run_command(["rpm", "-q", "--quiet", package_name]).returncode == 0


def check_package_alternatives(
    requirement: str,
    packages: Sequence[str],
    operating_system: OperatingSystem,
) -> CheckResult:
    """Pass when any package in a list is installed."""

    for package_name in packages:
        if package_is_installed(package_name, operating_system):
            return result(requirement, "OK", f"package: {package_name}")
    return result(requirement, "FAIL", f"none installed: {' '.join(packages)}")


def check_command_provider(
    requirement: str, command: str, operating_system: OperatingSystem
) -> CheckResult:
    """Report the distribution package that supplies a command."""

    path = command_path(command)
    if path is None:
        return result(requirement, "FAIL", f"command unavailable: {command}")

    if operating_system.package_family == "deb":
        provider_result = run_command(["dpkg-query", "-S", path])
        provider = provider_result.stdout.split(":", 1)[0]
    else:
        provider_result = run_command(["rpm", "-qf", "--queryformat", "%{NAME}", path])
        provider = provider_result.stdout
    detail = f"command: {path}"
    if provider_result.returncode == 0 and provider:
        detail += f", package: {provider}"
    return result(requirement, "OK", detail)


def service_load_state(unit: str) -> str:
    """Return the systemd LoadState for a unit."""

    query = run_command(["systemctl", "show", unit, "--property=LoadState", "--value"])
    return query.stdout if query.returncode == 0 else ""


def service_result(unit: str) -> CheckResult:
    """Report whether a systemd service is installed and active."""

    active = run_command(["systemctl", "is-active", "--quiet", unit])
    if active.returncode == 0:
        return result(unit, "OK", "running")
    if service_load_state(unit) == "loaded":
        return result(unit, "FAIL", "installed but not running")
    return result(unit, "WARN", "not installed")


def parse_key_value_config(content: str) -> dict[str, str]:
    """Parse whitespace-tolerant key=value configuration lines."""

    values: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = re.split(r"\s*=\s*", line, maxsplit=1)
        values[key.strip()] = value.split("#", 1)[0].strip()
    return values


def extract_braced_sections(content: str, section_name: str) -> list[str]:
    """Extract all top-level named brace sections from a config file."""

    sections: list[str] = []
    pattern = re.compile(rf"^\s*{re.escape(section_name)}\s*\{{")
    lines = content.splitlines()
    index = 0
    while index < len(lines):
        if not pattern.search(lines[index]):
            index += 1
            continue
        depth = lines[index].count("{") - lines[index].count("}")
        block: list[str] = []
        index += 1
        while index < len(lines) and depth > 0:
            depth += lines[index].count("{") - lines[index].count("}")
            if depth > 0:
                block.append(lines[index])
            index += 1
        sections.append("\n".join(block))
    return sections


def parse_multipath_stanzas(content: str) -> dict[str, tuple[str, str]]:
    """Map dm-N device names to multipath map name and full stanza."""

    stanzas: dict[str, tuple[str, str]] = {}
    current: list[str] = []

    def save(lines: list[str]) -> None:
        if not lines:
            return
        match = re.search(r"\b(dm-\d+)\b", lines[0])
        if match:
            stanzas[match.group(1)] = (lines[0].split()[0], "\n".join(lines))

    for line in content.splitlines():
        if line and not line[0].isspace() and re.search(r"\bdm-\d+\b", line):
            save(current)
            current = [line]
        elif line.strip():
            current.append(line)
        elif current:
            save(current)
            current = []
    save(current)
    return stanzas


def xml_dm_devices(xml_content: str) -> set[str]:
    """Extract and resolve device-mapper paths from libvirt XML."""

    devices: set[str] = set()
    for path_value in re.findall(r"source\s+dev=['\"]([^'\"]+)", xml_content):
        match = re.search(r"/(dm-\d+)$", path_value)
        if match:
            devices.add(match.group(1))
            continue
        if path_value.startswith("/dev/mapper/") or path_value.startswith(
            "/dev/disk/by-id/"
        ):
            resolved = run_command(["readlink", "-f", path_value])
            match = re.search(r"/(dm-\d+)$", resolved.stdout)
            if match:
                devices.add(match.group(1))
    return devices


def check_environment(operating_system: OperatingSystem) -> list[CheckResult]:
    return [result("Operating system", "OK", operating_system.pretty_name)]


def check_sudoers() -> list[CheckResult]:
    """Find users granted unrestricted passwordless sudo."""

    pattern = re.compile(
        r"^([^#\s]+)\s+ALL=\(ALL(?::ALL)?\)\s+NOPASSWD:\s*ALL\s*$"
    )
    entries: list[str] = []
    paths = [Path("/etc/sudoers")]
    sudoers_dir = Path("/etc/sudoers.d")
    if sudoers_dir.is_dir():
        paths.extend(sorted(path for path in sudoers_dir.iterdir() if path.is_file()))
    for path in paths:
        content = read_text(path)
        if content is None:
            continue
        for line in content.splitlines():
            match = pattern.match(line)
            if match:
                entries.append(f"{match.group(1)} ({path})")
    if entries:
        return [result("Passwordless sudo", "OK", "\n".join(entries))]
    return [result("Passwordless sudo", "FAIL", "no matching users found")]


def check_glance_mount(directory: Path) -> list[CheckResult]:
    """Validate fstab mapping, permissions, and ownership for an image directory."""

    selected_directory = directory if directory.is_absolute() else Path("/") / directory
    normalized = Path(os.path.normpath(str(selected_directory)))
    fstab = read_text(Path("/etc/fstab"))
    if fstab is None:
        return [result("Glance mount mapping", "FAIL", "/etc/fstab is not readable")]

    mount_point = ""
    for raw_line in fstab.splitlines():
        fields = raw_line.split()
        if not fields or raw_line.lstrip().startswith("#") or len(fields) < 2:
            continue
        candidate = fields[1].rstrip("/") or "/"
        normalized_text = str(normalized)
        if candidate == normalized_text or (
            normalized_text != "/" and candidate.startswith(f"{normalized_text}/")
        ):
            mount_point = candidate
            break
    if not mount_point:
        return [
            result(
                "Glance mount mapping",
                "WARN",
                f"no /etc/fstab mapping found at or below {normalized}",
            )
        ]

    rows = [result("Glance mount mapping", "OK", mount_point)]
    try:
        stat_result = normalized.stat()
    except OSError as error:
        rows.append(result("Glance mount directory", "WARN", str(error)))
        return rows

    mode = f"{stat_result.st_mode & 0o777:o}"
    owner = run_command(["stat", "-c", "%U", str(normalized)]).stdout or str(stat_result.st_uid)
    group = run_command(["stat", "-c", "%G", str(normalized)]).stdout or str(stat_result.st_gid)
    rows.append(
        comparison_result(
            "Glance mount permissions",
            "OK" if mode == "744" else "WARN",
            mode,
            "744",
            str(normalized),
        )
    )
    rows.append(
        comparison_result(
            "Glance mount ownership",
            "OK" if (owner, group) == ("pf9", "pf9group") else "FAIL",
            f"{owner}:{group}",
            "pf9:pf9group",
            str(normalized),
        )
    )
    return rows


def check_bond() -> list[CheckResult]:
    query = run_command(["ip", "-o", "link", "show", "type", "bond"])
    interfaces = []
    for line in query.stdout.splitlines():
        fields = line.split(": ", 2)
        if len(fields) >= 2:
            interfaces.append(fields[1].split("@")[0])
    if not interfaces:
        return [result("Bond interfaces", "WARN", "no bond interfaces found")]

    rows: list[CheckResult] = []
    for interface in interfaces:
        content = read_text(Path("/proc/net/bonding") / interface) or ""
        mode_match = re.search(r"^Bonding Mode:\s*(.*)$", content, re.MULTILINE)
        mode = mode_match.group(1) if mode_match else "unknown"
        slave_interfaces = re.findall(
            r"^Slave Interface:\s*(\S+)", content, re.MULTILINE
        )
        address = run_command(
            ["ip", "-4", "-o", "addr", "show", "dev", interface, "scope", "global"]
        )
        addresses = re.findall(r"\binet\s+(\S+)", address.stdout)
        rows.append(
            result(
                interface,
                "OK" if "802.3ad" in mode else "INFO",
                f"mode: {mode}; slaves: {', '.join(slave_interfaces) or 'none'}; "
                f"IP: {', '.join(addresses) or 'none'}",
            )
        )
    return rows


def fstab_mount_entry(mount_target: str) -> str | None:
    """Return the active /etc/fstab line for a mount target, when present."""

    content = read_text(Path("/etc/fstab"))
    if content is None:
        return None

    normalized_target = os.path.normpath(mount_target)
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) >= 2 and os.path.normpath(fields[1]) == normalized_target:
            return line
    return None


def check_pf9_service_storage(
    package_name: str,
    service_name: str,
    directory: Path,
    minimum_size_gib: int,
    operating_system: OperatingSystem,
) -> list[CheckResult]:
    """Check storage only when the corresponding PF9 role is installed and active."""

    if not package_is_installed(package_name, operating_system):
        return []
    service_status = run_command(
        ["systemctl", "is-active", "--quiet", service_name]
    )
    if service_status.returncode != 0:
        return []

    rows: list[CheckResult] = []
    try:
        filesystem = os.statvfs(directory)
    except OSError as error:
        return [result(f"{directory} filesystem", "WARN", str(error))]

    size_bytes = filesystem.f_blocks * filesystem.f_frsize
    size_gib = size_bytes / GIB
    rows.append(
        comparison_result(
            f"{directory} filesystem size",
            "OK" if size_bytes >= minimum_size_gib * GIB else "WARN",
            f"{size_gib:.2f} GiB",
            f">= {minimum_size_gib} GiB",
            (
                f"Filesystem containing {directory} is below the required size."
                if size_bytes < minimum_size_gib * GIB
                else str(directory)
            ),
        )
    )

    mount = run_command(
        [
            "findmnt",
            "--json",
            "--target",
            str(directory),
            "--output",
            "SOURCE,TARGET,FSTYPE,OPTIONS",
        ]
    )
    if mount.returncode != 0:
        rows.append(
            result(
                f"{directory} mount details",
                "WARN",
                mount.stderr or "findmnt could not identify the underlying filesystem",
            )
        )
        return rows

    try:
        filesystems = json.loads(mount.stdout).get("filesystems", [])
    except (json.JSONDecodeError, AttributeError):
        filesystems = []
    if not filesystems:
        rows.append(result(f"{directory} mount details", "WARN", "no mount found"))
        return rows

    mount_details = filesystems[0]
    filesystem_type = str(mount_details.get("fstype", ""))
    mount_target = str(mount_details.get("target", ""))
    details = (
        f"source={mount_details.get('source', 'unknown')}; "
        f"target={mount_target or 'unknown'}; type={filesystem_type}; "
        f"options={mount_details.get('options', 'unknown')}"
    )
    fstab_entry = fstab_mount_entry(mount_target) if mount_target else None
    if filesystem_type.lower().startswith("nfs"):
        rows.append(
            result(f"{directory} filesystem backing", "INFO", f"NFS: {details}")
        )
        rows.append(
            result(
                f"{directory} NFS fstab entry",
                "OK" if fstab_entry else "WARN",
                (
                    fstab_entry
                    if fstab_entry
                    else (
                        f"NFS mount target {mount_target or 'unknown'} is absent "
                        "from /etc/fstab"
                    )
                ),
            )
        )
    elif mount_target != "/" and fstab_entry:
        rows.append(
            result(
                f"{directory} filesystem backing",
                "INFO",
                f"Dedicated non-NFS mount: {details}; fstab={fstab_entry}",
            )
        )
    else:
        rows.append(
            result(
                f"{directory} filesystem backing",
                "INFO",
                f"Local filesystem: {details}",
            )
        )
    return rows


def check_pf9_service_filesystems(
    operating_system: OperatingSystem,
) -> list[CheckResult]:
    """Validate filesystem capacity and NFS persistence for PF9 data paths."""

    checks = (
        (
            "pf9-glance-role",
            "pf9-glance-api.service",
            Path("/var/lib/nginx"),
            50,
        ),
        (
            "pf9-cindervolume-base",
            "pf9-cindervolume-base.service",
            Path("/opt/pf9/pf9-cindervolume-base/state/conversion"),
            100,
        ),
    )
    rows: list[CheckResult] = []
    for package_name, service_name, directory, minimum_size_gib in checks:
        rows.extend(
            check_pf9_service_storage(
                package_name,
                service_name,
                directory,
                minimum_size_gib,
                operating_system,
            )
        )
    if not rows:
        rows.append(
            result(
                "PF9 service filesystems",
                "INFO",
                "no applicable installed package with an active service",
            )
        )
    return rows


def check_ntp() -> list[CheckResult]:
    query = run_command(["timedatectl", "show", "--property=NTPSynchronized", "--value"])
    if query.returncode == 127:
        return [result("NTP synchronization", "FAIL", "timedatectl is unavailable")]
    synchronized = query.stdout == "yes"
    return [
        result(
            "NTP synchronization",
            "OK" if synchronized else "FAIL",
            query.stdout or query.stderr or "unknown",
        )
    ]


def check_packages(operating_system: OperatingSystem) -> list[CheckResult]:
    if operating_system.package_family == "deb":
        requirements = [
            ("SCSI device listing", ["lsscsi"]),
            ("SCSI generic utilities", ["sg3-utils"]),
            ("Device mapper multipath", ["multipath-tools"]),
            ("SCSI tools", ["scsitools"]),
            ("iSCSI initiator", ["open-iscsi"]),
            ("NFS client", ["nfs-common"]),
        ]
        return [
            check_package_alternatives(name, packages, operating_system)
            for name, packages in requirements
        ]

    rows = [
        check_package_alternatives(name, packages, operating_system)
        for name, packages in [
            ("SCSI device listing", ["lsscsi"]),
            ("SCSI generic utilities", ["sg3_utils"]),
            ("Device mapper multipath", ["device-mapper-multipath"]),
            ("iSCSI initiator", ["iscsi-initiator-utils"]),
            ("NFS client", ["nfs-utils"]),
        ]
    ]
    rows.append(
        check_command_provider("SCSI bus rescan utility", "rescan-scsi-bus.sh", operating_system)
    )
    return rows


def check_services() -> list[CheckResult]:
    if command_path("systemctl") is None:
        return [result("Core services", "FAIL", "systemctl is unavailable")]
    return [service_result(service) for service in ("iscsid", "multipathd")]


def check_iscsi_initiator() -> list[CheckResult]:
    rows: list[CheckResult] = []
    content = read_text(Path("/etc/iscsi/initiatorname.iscsi"))
    match = re.search(r"^InitiatorName=(.+)$", content or "", re.MULTILINE)
    rows.append(
        result(
            "iSCSI initiator name",
            "OK" if match else "FAIL",
            match.group(1) if match else "missing or empty",
        )
    )
    active = run_command(["systemctl", "is-active", "--quiet", "iscsid"])
    if active.returncode != 0:
        rows.append(result("iscsid", "WARN", "not running"))
        return rows
    rows.append(result("iscsid", "OK", "running"))
    sessions = run_command(["iscsiadm", "-m", "session"])
    if sessions.returncode == 127:
        rows.append(result("iSCSI sessions", "FAIL", "iscsiadm is unavailable"))
    elif sessions.stdout:
        rows.append(result("iSCSI sessions", "OK", sessions.stdout))
    else:
        rows.append(result("iSCSI sessions", "WARN", "no active sessions"))
    return rows


def check_nvme_configuration() -> list[CheckResult]:
    """Validate NVMe CLI, kernel modules, persistence, and host identity."""

    rows: list[CheckResult] = []
    nvme_path = command_path("nvme")
    rows.append(
        result(
            "nvme-cli",
            "OK" if nvme_path else "FAIL",
            f"command: {nvme_path}" if nvme_path else "nvme command is unavailable",
        )
    )

    required_modules = (
        "nvme_tcp",
        "nvme_fabrics",
        "nvme_keyring",
        "nvme_core",
        "nvme_auth",
    )
    for module_name in required_modules:
        module_path = Path("/sys/module") / module_name
        loaded = module_path.is_dir()
        rows.append(
            result(
                f"Runtime module {module_name}",
                "OK" if loaded else "WARN",
                "loaded" if loaded else "not loaded",
            )
        )

    persistent_modules = ("nvme_tcp", "nvme_fabrics")
    config_directories = (Path("/etc/modprobe.d"), Path("/etc/modules-load.d"))
    matches: dict[str, list[str]] = {name: [] for name in persistent_modules}
    for directory in config_directories:
        if not directory.is_dir():
            continue
        try:
            config_files = sorted(
                path for path in directory.iterdir() if path.is_file()
            )
        except OSError:
            continue
        for config_path in config_files:
            content = read_text(config_path)
            if content is None:
                continue
            active_lines = "\n".join(
                line.split("#", 1)[0] for line in content.splitlines()
            )
            # Linux treats hyphens and underscores equivalently in module names.
            normalized_active_lines = active_lines.replace("-", "_")
            for module_name in persistent_modules:
                pattern = rf"(?<![\w-]){re.escape(module_name)}(?![\w-])"
                if re.search(pattern, normalized_active_lines):
                    matches[module_name].append(str(config_path))

    for module_name in persistent_modules:
        matching_files = matches[module_name]
        rows.append(
            result(
                f"Persistent module {module_name}",
                "OK" if matching_files else "WARN",
                "\n".join(matching_files)
                if matching_files
                else "not found in /etc/modprobe.d or /etc/modules-load.d",
            )
        )

    multipath_path = Path("/sys/module/nvme_core/parameters/multipath")
    multipath_value = read_text(multipath_path)
    if multipath_value is None:
        rows.append(
            result(
                "NVMe native multipath",
                "WARN",
                f"{multipath_path} is missing or unreadable",
            )
        )
    else:
        multipath_value = multipath_value.strip()
        rows.append(
            result(
                "NVMe native multipath",
                (
                    "OK"
                    if multipath_value.casefold() in {"y", "yes", "1"}
                    else "WARN"
                ),
                multipath_value or "empty",
            )
        )

    missing_identity_message = (
        "Generate unique host NQN with nvme gen-hostnqn > /etc/nvme/hostnqn "
        "command"
    )
    for label, identity_path in (
        ("NVMe host NQN", Path("/etc/nvme/hostnqn")),
        ("NVMe host ID", Path("/etc/nvme/hostid")),
    ):
        identity_value = read_text(identity_path)
        if identity_value is None or not identity_value.strip():
            rows.append(
                result(
                    label,
                    "WARN",
                    f"{identity_path} is missing or empty. {missing_identity_message}",
                )
            )
            continue
        rows.append(result(label, "OK", identity_value))

    associated_warnings = any(row.status == "WARN" for row in rows[1:])
    if nvme_path is None and associated_warnings:
        rows.append(
            result(
                "NVMe applicability",
                "INFO",
                "System may not require NVMe configuration. If the environment "
                "does not use NVMe as the backend for workloads, the "
                "outcome can be ignored.",
            )
        )

    return rows


def check_fc_ports() -> list[CheckResult]:
    """Report local FC ports and storage targets visible through the fabric."""

    fc_hosts = sorted(Path("/sys/class/fc_host").glob("host*"))
    if not fc_hosts:
        return [
            result(
                "FC ports",
                "WARN",
                "no FC ports found on this node (/sys/class/fc_host/host* absent)",
            )
        ]

    attributes = {
        "WWPN": "port_name",
        "WWNN": "node_name",
        "Port State": "port_state",
        "Speed": "speed",
        "Fabric Name": "fabric_name",
    }
    rows: list[CheckResult] = []
    host_values: dict[str, dict[str, str]] = {}
    for host_path in fc_hosts:
        values = {
            label: (read_text(host_path / attribute) or "").strip()
            for label, attribute in attributes.items()
        }
        host_values[host_path.name] = values
        missing = [
            label
            for label, value in values.items()
            if not value or value.casefold() == "unknown"
        ]
        if missing:
            status = "FAIL"
        elif values["Port State"].casefold() != "online":
            status = "WARN"
        else:
            status = "OK"

        details = "; ".join(
            f"{label}: {value or '<not reported>'}"
            for label, value in values.items()
        )
        if missing:
            details = f"{details}; missing: {', '.join(missing)}"
        rows.append(result(host_path.name, status, details))

    online_hosts = {
        host_name
        for host_name, values in host_values.items()
        if values["Port State"].casefold() == "online"
    }
    if not online_hosts:
        rows.append(
            result(
                "FCP targets",
                "INFO",
                "remote-target discovery skipped because no local FC ports "
                "are online",
            )
        )
        return rows

    targets_by_host = {host_name: 0 for host_name in online_hosts}
    remote_ports = sorted(Path("/sys/class/fc_remote_ports").glob("rport-*"))
    for remote_path in remote_ports:
        roles = (read_text(remote_path / "roles") or "").strip()
        if "target" not in roles.casefold():
            continue

        target_wwpn = (read_text(remote_path / "port_name") or "").strip()
        host_match = re.fullmatch(r"rport-(\d+):\d+-\d+", remote_path.name)
        host_name = f"host{host_match.group(1)}" if host_match else "unknown"
        local_values = host_values.get(host_name)
        local_wwpn = local_values["WWPN"] if local_values else "<not reported>"
        local_state = (
            local_values["Port State"] if local_values else "<not reported>"
        )

        relationship_status = "OK"
        relationship_notes: list[str] = []
        if local_values is None:
            relationship_status = "WARN"
            relationship_notes.append("local FC host not found")
        elif host_name not in online_hosts:
            relationship_status = "WARN"
            relationship_notes.append("local FC port is not online")
        if not target_wwpn or target_wwpn.casefold() == "unknown":
            relationship_status = "WARN"
            relationship_notes.append("target WWPN unavailable")

        details = (
            f"Local Host: {host_name}; Local WWPN: {local_wwpn}; "
            f"Local State: {local_state}; "
            f"Target WWPN: {target_wwpn or '<not reported>'}; "
            f"Remote Role: {roles or '<not reported>'}"
        )
        if relationship_notes:
            details = f"{details}; notes: {', '.join(relationship_notes)}"
        rows.append(result(remote_path.name, relationship_status, details))

        if host_name in targets_by_host:
            targets_by_host[host_name] += 1

    hosts_without_targets = sorted(
        host_name
        for host_name, visible_targets in targets_by_host.items()
        if visible_targets == 0
    )
    per_host_counts = "; ".join(
        f"{host_name}: {targets_by_host[host_name]} target(s)"
        for host_name in sorted(targets_by_host)
    )
    if hosts_without_targets:
        rows.append(
            result(
                "FCP targets",
                "WARN",
                "FCP targets are not visible through: "
                f"{', '.join(hosts_without_targets)}. Visible targets by host: "
                f"{per_host_counts}. Check zoning/zoneset activation, "
                "target-port availability, and fabric connectivity.",
            )
        )
    else:
        rows.append(
            result(
                "FCP targets",
                "OK",
                "FCP target visibility confirmed for all online local FC "
                f"ports; {per_host_counts}",
            )
        )
    return rows


def check_iscsid_conf() -> list[CheckResult]:
    if command_path("iscsid") is None:
        return [result("iscsid.conf", "WARN", "iscsid is not installed")]
    content = read_text(Path("/etc/iscsi/iscsid.conf"))
    if content is None:
        return [result("iscsid.conf", "FAIL", "file is missing or unreadable")]
    configured = parse_key_value_config(content)
    expected = {
        "node.session.timeo.replacement_timeout": "15",
        "node.conn[0].timeo.login_timeout": "5",
        "node.conn[0].timeo.logout_timeout": "5",
        "node.session.err_timeo.abort_timeout": "10",
        "node.session.err_timeo.lu_reset_timeout": "20",
    }
    rows = []
    for key, wanted in expected.items():
        actual = configured.get(key)
        status = "OK" if actual == wanted else ("WARN" if actual else "FAIL")
        rows.append(comparison_result(key, status, actual, wanted))
    return rows


def parse_multipath_block_values(block: str) -> dict[str, str]:
    """Parse key/value directives from a multipath.conf brace block."""

    values: dict[str, str] = {}
    for line in block.splitlines():
        fields = shlex.split(line, comments=True)
        if len(fields) >= 2 and fields[0] not in {"device", "{"}:
            values[fields[0]] = " ".join(fields[1:]).rstrip("}").strip()
    return values


def check_multipath_blacklist() -> list[CheckResult]:
    path = Path("/etc/multipath.conf")
    content = read_text(path)
    if content is None:
        scsi_id = command_path("scsi_id")
        guidance = (
            f"use {scsi_id} -gud <DEVICE> to obtain local-drive WWIDs"
            if scsi_id
            else "install the distribution udev package to obtain scsi_id"
        )
        return [result("multipath.conf", "FAIL", guidance)]

    rows: list[CheckResult] = []
    defaults = extract_braced_sections(content, "defaults")
    default_values = parse_multipath_block_values(defaults[0]) if defaults else {}
    actual = default_values.get("checker_timeout")
    rows.append(
        comparison_result(
            "defaults.checker_timeout",
            "OK" if actual == "15" else "WARN",
            actual,
            "15",
        )
    )

    blacklist = extract_braced_sections(content, "blacklist")
    blacklist_entries = [
        line.strip()
        for block in blacklist
        for line in block.splitlines()
        if re.search(r"\b(?:devnode|wwid|device)\b", line)
    ]
    rows.append(
        result(
            "Multipath blacklist",
            "OK" if blacklist_entries else "WARN",
            "\n".join(blacklist_entries) or "no wwid/devnode entries",
        )
    )

    devices_sections = extract_braced_sections(content, "devices")
    device_blocks = []
    for section in devices_sections:
        device_blocks.extend(extract_braced_sections(section, "device"))
    netapp_block = next(
        (block for block in device_blocks if re.search(r'\bvendor\s+"?NETAPP"?', block)),
        None,
    )
    if netapp_block is None:
        rows.append(result("NETAPP multipath device", "WARN", "device block not found"))
    else:
        rows.append(result("NETAPP multipath device", "OK", "device block found"))
        configured = parse_multipath_block_values(netapp_block)
        expected = {
            "path_grouping_policy": "group_by_prio",
            "prio": "alua",
            "failback": "immediate",
            "fast_io_fail_tmo": "5",
            "dev_loss_tmo": "30",
            "product": "LUN.*",
            "path_selector": "service-time 0",
            "features": "0",
            "hardware_handler": "1 alua",
        }
        for key, wanted in expected.items():
            actual = configured.get(key)
            status = "OK" if actual == wanted else ("WARN" if actual else "FAIL")
            rows.append(
                comparison_result(
                    f"NETAPP {key}",
                    status,
                    actual,
                    wanted,
                )
            )
    rows.append(result("multipath.conf content", "INFO", content))
    return rows


def check_lvm_filters() -> list[CheckResult]:
    content = read_text(Path("/etc/lvm/lvm.conf"))
    if content is None:
        return [result("LVM filters", "FAIL", "lvm.conf is missing or unreadable")]
    matches = re.findall(r"^\s*(?:global_)?filter\s*=.*$", content, re.MULTILINE)
    if not matches:
        return [result("LVM filters", "WARN", "filter and global_filter are unset")]
    return [result("LVM filters", "OK", "\n".join(line.strip() for line in matches))]


def check_hosts() -> list[CheckResult]:
    content = read_text(Path("/etc/hosts"))
    if content is None:
        return [result("/etc/hosts", "FAIL", "file is unreadable")]
    note = "Review required host mappings, including storage SVM IP/FQDN records."
    return [result("/etc/hosts", "INFO", f"{note}\n\n{content}")]


def check_fstab() -> list[CheckResult]:
    content = read_text(Path("/etc/fstab"))
    if content is None:
        return [result("/etc/fstab", "FAIL", "file is unreadable")]
    return [result("/etc/fstab", "OK", content)]


def check_group_consistency() -> list[CheckResult]:
    query = run_command(["grpck", "-r"])
    if query.returncode == 127:
        return [result("Group database", "FAIL", "grpck is unavailable")]
    return [
        result(
            "Group database",
            "OK" if query.returncode == 0 else "FAIL",
            query.stdout or query.stderr or "consistency check passed",
        )
    ]


def check_rsyslog_pf9_rules() -> list[CheckResult]:
    directory = Path("/etc/rsyslog.d")
    if not directory.is_dir():
        return [result("PF9 rsyslog rules", "WARN", f"{directory} not found")]
    log_paths = [
        "/var/log/pf9/ostackhost.log",
        "/var/log/pf9/cindervolume-base.log",
        "/var/log/pf9/hostagent.log",
        "/var/log/pf9/glance-api.log",
        "/var/log/pf9/novncproxy.log",
        "/var/log/pf9/pf9-neutron-ovn-metadata-agent.log",
    ]
    files = [(path, read_text(path) or "") for path in directory.rglob("*") if path.is_file()]
    rows = []
    for log_path in log_paths:
        matches = [str(path) for path, content in files if log_path in content]
        rows.append(
            result(
                log_path,
                "OK" if matches else "WARN",
                "\n".join(matches) or f"not found under {directory}",
            )
        )
    return rows


def check_sysctl_settings() -> list[CheckResult]:
    expected = {"net.ipv4.tcp_retries2": "7", "vm.swappiness": "10"}
    directory = Path("/etc/sysctl.d")
    files = list(directory.glob("*.conf")) if directory.is_dir() else []
    rows: list[CheckResult] = []
    for key, wanted in expected.items():
        runtime = run_command(["sysctl", "-n", key])
        rows.append(
            comparison_result(
                f"Runtime {key}",
                "OK" if runtime.stdout == wanted else ("WARN" if runtime.stdout else "FAIL"),
                runtime.stdout,
                wanted,
            )
        )
        matching_files = []
        for path in files:
            values = parse_key_value_config(read_text(path) or "")
            if values.get(key) == wanted:
                matching_files.append(str(path))
        rows.append(
            result(
                f"Persistent {key}",
                "OK" if matching_files else "FAIL",
                "\n".join(matching_files) or f"not found under {directory}",
            )
        )
    return rows


def check_pf9_user_group() -> list[CheckResult]:
    """Check PF9 account records through Python's system account database."""

    rows = []
    try:
        user = pwd.getpwnam("pf9")
        rows.append(
            result(
                "PF9 user",
                "OK",
                f"name={user.pw_name}, uid={user.pw_uid}, gid={user.pw_gid}, "
                f"home={user.pw_dir}, shell={user.pw_shell}",
            )
        )
    except KeyError:
        rows.append(result("PF9 user", "FAIL", "pf9 not found"))

    try:
        group = grp.getgrnam("pf9group")
        members = ", ".join(group.gr_mem) or "none"
        rows.append(
            result(
                "PF9 group",
                "OK",
                f"name={group.gr_name}, gid={group.gr_gid}, members={members}",
            )
        )
    except KeyError:
        rows.append(result("PF9 group", "FAIL", "pf9group not found"))
    return rows


def check_pf9_packages(operating_system: OperatingSystem) -> list[CheckResult]:
    rows: list[CheckResult] = []
    if operating_system.package_family == "deb":
        for requirement, packages in (
            ("Open vSwitch common files", ["openvswitch-common"]),
            ("Open vSwitch service", ["openvswitch-switch"]),
            ("OVN common files", ["ovn-common"]),
            ("OVN host", ["ovn-host"]),
        ):
            rows.append(check_package_alternatives(requirement, packages, operating_system))
    else:
        rows.extend(
            [
                check_command_provider("Open vSwitch", "ovs-vsctl", operating_system),
                check_command_provider("OVN host controller", "ovn-controller", operating_system),
            ]
        )
    packages = [
        "pf9-cindervolume-base",
        "pf9-cindervolume-config",
        "pf9-comms",
        "pf9-glance-role",
        "pf9-ha-slave",
        "pf9-hostagent",
        "pf9-ip-discovery",
        "pf9-neutron-base",
        "pf9-neutron-ovn-controller",
        "pf9-neutron-ovn-metadata-agent",
        "pf9-ostackhost",
    ]
    for package in packages:
        installed = package_is_installed(package, operating_system)
        rows.append(
            result(
                package,
                "OK" if installed else "FAIL",
                "installed" if installed else "not installed",
            )
        )
    return rows


def compare_libvirt_inventory() -> str:
    """Compare local domain XML names with virsh inventory."""

    qemu_dir = Path("/etc/libvirt/qemu")
    xml_names = {path.stem for path in qemu_dir.glob("*.xml")} if qemu_dir.is_dir() else set()
    virsh = run_command(["virsh", "list", "--all", "--name"])
    virsh_names = {name for name in virsh.stdout.splitlines() if name}
    only_xml = sorted(xml_names - virsh_names)
    only_virsh = sorted(virsh_names - xml_names)
    return "\n".join(
        [
            f"XML only: {', '.join(only_xml) or 'none'}",
            f"virsh only: {', '.join(only_virsh) or 'none'}",
            f"local XML configs: {len(xml_names)}",
            f"virsh domains: {len(virsh_names)}",
        ]
    )


def check_file_ownership(
    path: Path,
    check_name: str,
    *,
    missing_status: str = "WARN",
    missing_message: str = "missing or unreadable",
) -> CheckResult:
    """Report a file's mode and whether pf9:pf9group owns it."""

    try:
        file_stat = path.stat()
    except OSError:
        return result(check_name, missing_status, missing_message)

    try:
        owner = pwd.getpwuid(file_stat.st_uid).pw_name
    except KeyError:
        owner = str(file_stat.st_uid)
    try:
        group = grp.getgrgid(file_stat.st_gid).gr_name
    except KeyError:
        group = str(file_stat.st_gid)

    ownership = f"{owner}:{group}"
    mode = stat.filemode(file_stat.st_mode)
    output = f"path={path}; ownership={ownership}; mode={mode}"
    if ownership != "pf9:pf9group":
        output += "\nthe owner and the group requires to be pf9:pf9group"
    return result(
        check_name,
        "OK" if ownership == "pf9:pf9group" else "WARN",
        output,
    )


def override_content_result(
    check_name: str,
    content: str | None,
    *,
    missing_status: str = "WARN",
    missing_message: str = "missing or unreadable",
) -> CheckResult:
    """Distinguish missing, empty, and populated override files."""

    if content is None:
        return result(check_name, missing_status, missing_message)
    if not content.strip():
        return result(check_name, "INFO", "file found with no content")
    return result(check_name, "INFO", content)


def check_glance_cinder_store_parameters(path: Path) -> CheckResult:
    """Report required Glance Cinder store parameters without exposing secrets."""

    required_parameters = (
        "cinder_api_insecure",
        "cinder_os_region_name",
        "cinder_store_auth_address",
        "cinder_store_password",
        "cinder_store_project_domain_name",
        "cinder_store_project_name",
        "cinder_store_user_domain_name",
        "cinder_store_user_name",
        "cinder_volume_type",
    )
    content = read_text(path)
    if content is None:
        return result(
            "Glance Cinder store parameters",
            "WARN",
            f"{path} is missing or unreadable",
        )

    configured = parse_key_value_config(content)
    missing = [key for key in required_parameters if not configured.get(key)]
    parameter_status = [
        f"{key}: {'missing' if key in missing else 'configured'}"
        for key in required_parameters
    ]
    if missing:
        parameter_status.append(f"Missing parameters: {', '.join(missing)}")
    return result(
        "Glance Cinder store parameters",
        "WARN" if missing else "OK",
        "\n".join(parameter_status),
    )


def check_pf9_services(operating_system: OperatingSystem) -> list[CheckResult]:
    services = [
        "pf9-ostackhost.service",
        "pf9-cindervolume-base.service",
        "pf9-glance-api.service",
        "pf9-comms.service",
        "pf9-ha-slave.service",
        "pf9-hostagent.service",
        "pf9-libvirt-exporter.service",
        "pf9-neutron-ovn-metadata-agent.service",
        "pf9-node-exporter.service",
        "pf9-novncproxy.service",
        "pf9-prometheus.service",
        "pf9-remote-write.service",
        "pf9-sidekick.service",
    ]
    rows = [service_result(service) for service in services]
    status_by_name = {row.name: row.status for row in rows}
    if package_is_installed(
        "pf9-ostackhost", operating_system
    ) and status_by_name.get("pf9-ostackhost.service") == "OK":
        nova_path = Path("/opt/pf9/etc/nova/conf.d/nova_override.conf")
        content = read_text(nova_path)
        if content is None:
            rows.append(result("nova_override.conf", "INFO", "no nova overrides found on the host"))
        else:
            match = re.search(r"^\s*volume_use_multipath\s*=.*$", content, re.MULTILINE)
            rows.append(
                result(
                    "nova volume_use_multipath",
                    "OK" if match else "WARN",
                    match.group(0).strip() if match else "setting is absent",
                )
            )
        rows.append(
            override_content_result("nova_override.conf content", content)
        )
        rows.append(
            check_file_ownership(
                nova_path,
                "nova_override.conf ownership",
                missing_status="INFO",
            )
        )
        rows.append(result("Libvirt VM inventory", "INFO", compare_libvirt_inventory()))

    if package_is_installed(
        "pf9-cindervolume-base", operating_system
    ) and status_by_name.get("pf9-cindervolume-base.service") == "OK":
        cinder_path = Path(
            "/opt/pf9/etc/pf9-cindervolume-base/conf.d/cinder_override.conf"
        )
        content = read_text(cinder_path)
        rows.append(
            override_content_result("cinder_override.conf content", content)
        )
        rows.append(
            check_file_ownership(
                cinder_path,
                "cinder_override.conf ownership",
                missing_status="INFO",
            )
        )

    if package_is_installed(
        "pf9-glance-role", operating_system
    ) and status_by_name.get("pf9-glance-api.service") == "OK":
        rows.append(
            check_glance_cinder_store_parameters(Path("/etc/glance-api.conf"))
        )
        glance_override_path = Path("/etc/glance/glance-api-override.conf")
        glance_override_content = read_text(glance_override_path)
        rows.append(
            override_content_result(
                "glance-api-override.conf content",
                glance_override_content,
                missing_status="INFO",
                missing_message="no glance overrides found on the host",
            )
        )
        rows.append(
            check_file_ownership(
                glance_override_path,
                "glance-api-override.conf ownership",
                missing_status="INFO",
                missing_message="no glance overrides found on the host",
            )
        )
    return rows


def check_ovs_bridges() -> list[CheckResult]:
    bridges_result = run_command(["ovs-vsctl", "list-br"])
    if bridges_result.returncode == 127:
        return [result("OVS bridges", "FAIL", "ovs-vsctl is unavailable")]
    bridges = bridges_result.stdout.splitlines()
    if not bridges:
        return [result("OVS bridges", "FAIL", "no bridges configured")]
    rows: list[CheckResult] = []
    for bridge in bridges:
        address = run_command(["ip", "-4", "-o", "addr", "show", "dev", bridge])
        matches = re.findall(r"\binet\s+(\S+)", address.stdout)
        ports = run_command(["ovs-vsctl", "list-ports", bridge]).stdout.splitlines()
        if bridge == "br-int":
            displayed_ports = ports
        else:
            displayed_ports = []
            for port in ports:
                interface_type = run_command(
                    ["ovs-vsctl", "get", "interface", port, "type"]
                ).stdout.strip('"')
                if interface_type not in {"patch", "internal"} and re.match(
                    r"^(?:ens|eth|bond|vlan|em|enp|eno)\d", port
                ):
                    displayed_ports.append(port)
        rows.append(
            result(
                f"OVS bridge {bridge}",
                "OK" if matches else "WARN",
                f"IP: {', '.join(matches) or 'none'}\n"
                f"Ports: {', '.join(displayed_ports) or 'none'}",
            )
        )
    return rows


def check_virsh_vm(uuid: str) -> list[CheckResult]:
    if command_path("virsh") is None:
        return [result("Virsh VM", "FAIL", "virsh is unavailable")]
    domain = run_command(["virsh", "domname", uuid])
    if domain.returncode != 0 or not domain.stdout:
        return [result("Virsh VM", "FAIL", f"no VM found with UUID {uuid}")]
    block_list = run_command(["virsh", "domblklist", "--details", domain.stdout])
    rows = [result("Virsh VM", "OK", f"{domain.stdout} ({uuid})")]
    if not block_list.stdout:
        rows.append(result("VM block devices", "WARN", "no block devices found"))
        return rows
    rows.append(result("VM block devices", "INFO", block_list.stdout))
    dm_devices = sorted(set(re.findall(r"\bdm-\d+\b", block_list.stdout)))
    if not dm_devices:
        rows.append(result("VM multipath devices", "WARN", "no dm-N devices found"))
        return rows
    multipath = parse_multipath_stanzas(run_command(["multipath", "-ll"]).stdout)
    for device in dm_devices:
        mapping = multipath.get(device)
        rows.append(
            result(
                device,
                "OK" if mapping else "WARN",
                f"/dev/mapper/{mapping[0]}" if mapping else "not found in multipath output",
            )
        )
    return rows


def check_virsh_responsiveness() -> list[CheckResult]:
    query = run_command(["virsh", "list", "--all"], timeout=10)
    if query.returncode == 0:
        return [result("Virsh responsiveness", "OK", "virsh responded within 10 seconds")]
    detail = (
        "timed out after 10 seconds"
        if query.timed_out
        else query.stderr or f"exit code {query.returncode}"
    )
    rows = [result("Virsh responsiveness", "FAIL", detail)]
    processes = run_command(["ps", "-eo", "pid=,stat=,comm=,args="])
    zombies = []
    for line in processes.stdout.splitlines():
        fields = line.split(maxsplit=3)
        if len(fields) >= 3 and fields[1].startswith("Z") and "qemu" in line.lower():
            zombies.append(line.strip())
    rows.append(
        result(
            "Zombie QEMU processes",
            "WARN" if zombies else "INFO",
            "\n".join(zombies) or "none found",
        )
    )
    return rows


def collect_vm_dm_map() -> dict[str, str]:
    """Map dm-N devices to libvirt domain names from local XML."""

    mapping: dict[str, str] = {}
    qemu_dir = Path("/etc/libvirt/qemu")
    if not qemu_dir.is_dir():
        return mapping
    for xml_path in qemu_dir.glob("*.xml"):
        content = read_text(xml_path)
        if content is None:
            continue
        for device in xml_dm_devices(content):
            mapping[device] = xml_path.stem
    return mapping


def check_multipath_orphans() -> list[CheckResult]:
    multipath_result = run_command(["multipath", "-ll"])
    if multipath_result.returncode == 127:
        return [result("Multipath orphans", "WARN", "multipath is unavailable")]
    stanzas = parse_multipath_stanzas(multipath_result.stdout)
    if not stanzas:
        return [result("Multipath orphans", "WARN", "no multipath devices found")]
    vm_mapping = collect_vm_dm_map()
    rows: list[CheckResult] = []
    for device, (map_name, stanza) in stanzas.items():
        owner = vm_mapping.get(device)
        faulty = re.findall(r"^.*\b(?:failed|faulty)\b.*$", stanza, re.MULTILINE)
        if not owner:
            rows.append(result(f"{map_name} ({device})", "WARN", f"orphaned\n{stanza}"))
        if faulty:
            rows.append(
                result(
                    f"{map_name} ({device}) paths",
                    "FAIL",
                    f"VM: {owner or 'none'}\n" + "\n".join(faulty),
                )
            )
    if not rows:
        rows.append(
            result(
                "Multipath devices",
                "OK",
                "all devices are VM-referenced with healthy paths",
            )
        )
    return rows


def check_vm_disk_multipath() -> list[CheckResult]:
    domains = run_command(["virsh", "list", "--name"], timeout=10)
    if domains.returncode != 0:
        return [
            result(
                "VM disk multipath",
                "WARN",
                "virsh is unavailable or unresponsive",
            )
        ]
    virtual_machines = [name for name in domains.stdout.splitlines() if name]
    if not virtual_machines:
        return [result("VM disk multipath", "INFO", "no running VMs")]
    stanzas = parse_multipath_stanzas(run_command(["multipath", "-ll"]).stdout)
    rows: list[CheckResult] = []
    for virtual_machine in virtual_machines:
        domain_info = run_command(["virsh", "dominfo", virtual_machine]).stdout
        uuid_match = re.search(r"^UUID:\s*(\S+)", domain_info, re.MULTILINE)
        uuid_text = uuid_match.group(1) if uuid_match else "unknown"
        block_list_result = run_command(
            ["virsh", "domblklist", "--details", virtual_machine]
        )
        if block_list_result.returncode != 0:
            rows.append(
                result(
                    virtual_machine,
                    "WARN",
                    block_list_result.stderr or "unable to list VM block devices",
                )
            )
            continue

        disks: list[tuple[str, str]] = []
        for line in block_list_result.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 4 and fields[1] == "disk" and fields[3] != "-":
                disks.append((fields[2], fields[3]))
        if not disks:
            rows.append(result(virtual_machine, "WARN", "no VM disks found"))
            continue

        for target, source in disks:
            resolved_source = run_command(["readlink", "-f", source]).stdout or source
            device_match = re.search(r"/(dm-\d+)$", resolved_source)
            identity = f"{virtual_machine}: {target}"
            if not device_match:
                rows.append(
                    result(
                        identity,
                        "non-multipath disk",
                        f"UUID: {uuid_text}; source: {source}; "
                        f"resolved: {resolved_source}\n"
                        "VM appears to disk which are not managed by "
                        "dm-multipath services",
                    )
                )
                continue

            device = device_match.group(1)
            mapping = stanzas.get(device)
            if not mapping:
                rows.append(
                    result(
                        identity,
                        "FAIL",
                        f"UUID: {uuid_text}; device: {device}; "
                        "not found in multipath output",
                    )
                )
                continue
            map_name, stanza = mapping
            path_lines = re.findall(r"^.*\d+:\d+:\d+:\d+.*$", stanza, re.MULTILINE)
            active = [
                line
                for line in path_lines
                if re.search(r"\bactive\b.*\bready\b", line)
            ]
            if path_lines and len(active) == len(path_lines):
                status = "OK"
                state = "active"
            elif active:
                status = "WARN"
                state = "degraded"
            else:
                status = "FAIL"
                state = "dead"
            rows.append(
                result(
                    identity,
                    status,
                    f"UUID: {uuid_text}; device: {device}; map: {map_name}; {state} "
                    f"({len(active)}/{len(path_lines)} paths up)",
                )
            )
    return rows


def resolve_nvme_namespace(device_path: str) -> str | None:
    """Resolve a libvirt block path to its parent NVMe namespace device."""

    resolved_path = run_command(["readlink", "-f", device_path]).stdout
    candidate = resolved_path or device_path
    match = re.fullmatch(r"/dev/(nvme\d+n\d+)(?:p\d+)?", candidate)
    return f"/dev/{match.group(1)}" if match else None


def check_vm_nvme_attachments() -> list[CheckResult]:
    """Map running VM disks to NVMe subsystems using the local host NQN."""

    ostackhost = run_command(
        ["systemctl", "is-active", "--quiet", "pf9-ostackhost.service"]
    )
    if ostackhost.returncode != 0:
        return [
            result(
                "VM NVMe attachments",
                "INFO",
                "ostackhost service not running on the host skipping the check",
            )
        ]

    domains = run_command(["virsh", "list", "--name"], timeout=10)
    if domains.returncode != 0:
        return [
            result(
                "VM NVMe attachments",
                "WARN",
                domains.stderr or "virsh is unavailable or unresponsive",
            )
        ]

    virtual_machines = [name for name in domains.stdout.splitlines() if name]
    if not virtual_machines:
        return [
            result(
                "VM NVMe attachments",
                "INFO",
                "virsh returned no running VMs; skipping the check",
            )
        ]

    hostnqn_path = Path("/etc/nvme/hostnqn")
    hostnqn = (read_text(hostnqn_path) or "").strip()
    nvme_path = command_path("nvme")
    multipath_stanzas = parse_multipath_stanzas(
        run_command(["multipath", "-ll"]).stdout
    )

    rows: list[CheckResult] = []
    for virtual_machine in virtual_machines:
        domain_info = run_command(["virsh", "dominfo", virtual_machine]).stdout
        uuid_match = re.search(r"^UUID:\s*(\S+)", domain_info, re.MULTILINE)
        uuid_text = uuid_match.group(1) if uuid_match else "unknown"
        block_list = run_command(
            ["virsh", "domblklist", "--details", virtual_machine]
        )
        if block_list.returncode != 0:
            rows.append(
                result(
                    virtual_machine,
                    "WARN",
                    block_list.stderr or "unable to list VM block devices",
                )
            )
            continue

        disks: list[tuple[str, str]] = []
        for line in block_list.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 4 and fields[1] == "disk" and fields[3] != "-":
                disks.append((fields[2], fields[3]))
        if not disks:
            rows.append(result(virtual_machine, "WARN", "no VM disks found"))
            continue

        for target, source in disks:
            resolved_source = run_command(["readlink", "-f", source]).stdout or source
            device = resolve_nvme_namespace(source)
            identity = f"{virtual_machine} ({uuid_text}) -> {target}"
            if device is None:
                dm_match = re.search(r"/(dm-\d+)$", resolved_source)
                mapping = (
                    multipath_stanzas.get(dm_match.group(1)) if dm_match else None
                )
                if not mapping:
                    rows.append(
                        result(
                            identity,
                            "non-nVMe",
                            f"source: {source}\nresolved: {resolved_source}",
                        )
                    )
                    continue

                map_name, stanza = mapping
                path_lines = re.findall(
                    r"^.*\d+:\d+:\d+:\d+.*$", stanza, re.MULTILINE
                )
                active_paths = [
                    line
                    for line in path_lines
                    if re.search(r"\bactive\b.*\bready\b", line)
                ]
                if path_lines and len(active_paths) == len(path_lines):
                    path_state = "active"
                elif active_paths:
                    path_state = "degraded"
                else:
                    path_state = "dead"
                rows.append(
                    result(
                        identity,
                        "non-nVMe",
                        f"source: {source}; map: {map_name}; {path_state} "
                        f"({len(active_paths)}/{len(path_lines)} paths up)\n{stanza}",
                    )
                )
                continue

            if not hostnqn:
                rows.append(
                    result(
                        identity,
                        "FAIL",
                        f"device: {device}; {hostnqn_path} is missing, unreadable, "
                        "or empty",
                    )
                )
                continue
            if nvme_path is None:
                rows.append(
                    result(identity, "FAIL", f"device: {device}; nvme unavailable")
                )
                continue

            subsystem = run_command(["nvme", "list-subsys", device])
            if subsystem.returncode != 0:
                rows.append(
                    result(
                        identity,
                        "FAIL",
                        subsystem.stderr or "unable to query NVMe subsystem",
                    )
                )
                continue

            subsystem_hostnqns = set(
                re.findall(r"^\s*hostnqn\s*=\s*(\S+)", subsystem.stdout, re.MULTILINE)
            )
            hostnqn_matches = hostnqn in subsystem_hostnqns
            status = "OK" if hostnqn_matches else "WARN"
            match_detail = (
                f"hostnqn matches {hostnqn_path}"
                if hostnqn_matches
                else f"hostnqn does not match {hostnqn_path}"
            )
            rows.append(
                result(
                    identity,
                    status,
                    f"device: {device}; {match_detail}\n{subsystem.stdout}",
                )
            )

    return rows


def expand_cpu_list(cpu_list: str) -> set[int]:
    """Expand a Linux CPU list such as ``0-3,8`` into CPU numbers."""

    cpus: set[int] = set()
    for item in cpu_list.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            if "-" in item:
                start_text, end_text = item.split("-", 1)
                start = int(start_text)
                end = int(end_text)
                cpus.update(range(start, end + 1))
            else:
                cpus.add(int(item))
        except ValueError:
            continue
    return cpus


def check_cpu_virtualization() -> list[CheckResult]:
    """Check CPU virtualization flags, KVM, and the libvirt service."""

    cpu_info = read_text(Path("/proc/cpuinfo")) or ""
    has_virtualization = bool(re.search(r"\b(?:vmx|svm)\b", cpu_info))
    rows = [
        result(
            "CPU virtualization flags",
            "OK" if has_virtualization else "FAIL",
            "vmx/svm present" if has_virtualization else "no vmx/svm flag",
        )
    ]

    try:
        kvm_present = stat.S_ISCHR(Path("/dev/kvm").stat().st_mode)
    except OSError:
        kvm_present = False
    rows.append(
        result(
            "/dev/kvm",
            "OK" if kvm_present else "FAIL",
            "character device present" if kvm_present else "missing",
        )
    )

    libvirtd = run_command(["systemctl", "is-active", "--quiet", "libvirtd"])
    rows.append(
        result(
            "libvirtd",
            "OK" if libvirtd.returncode == 0 else "WARN",
            "active"
            if libvirtd.returncode == 0
            else "not active (check modular virtqemud)",
        )
    )
    return rows


def check_kernel_cpu_parameters() -> list[CheckResult]:
    """Validate CPU isolation, IOMMU, and hugepage kernel parameters."""

    cmdline = (read_text(Path("/proc/cmdline")) or "").strip()
    checks = [
        (
            "IOMMU enabled on cmdline",
            r"(?:^|\s)(?:intel|amd)_iommu=on(?:\s|$)",
            "FAIL",
            "no intel_iommu=on / amd_iommu=on",
        ),
        ("iommu=pt", r"(?:^|\s)iommu=pt(?:\s|$)", "WARN", "absent"),
        ("isolcpus", r"(?:^|\s)isolcpus=\S+", "FAIL", "missing"),
        ("nohz_full", r"(?:^|\s)nohz_full=\S+", "FAIL", "missing"),
        ("rcu_nocbs", r"(?:^|\s)rcu_nocbs=\S+", "FAIL", "missing"),
        (
            "Hugepage parameters",
            r"(?:^|\s)(?:hugepagesz|default_hugepagesz)=\S+",
            "FAIL",
            "no hugepage parameters",
        ),
    ]
    rows = []
    for name, pattern, failure_status, failure_output in checks:
        match = re.search(pattern, cmdline)
        rows.append(
            result(
                name,
                "OK" if match else failure_status,
                match.group(0).strip() if match else failure_output,
            )
        )
    rows.append(result("Kernel command line", "INFO", cmdline or "unreadable"))
    return rows


def check_cpu_isolation() -> list[CheckResult]:
    """Report effective CPU isolation and validate SMT sibling placement."""

    isolated_text = (
        read_text(Path("/sys/devices/system/cpu/isolated")) or ""
    ).strip()
    nohz_text = (read_text(Path("/sys/devices/system/cpu/nohz_full")) or "").strip()
    online_text = (read_text(Path("/sys/devices/system/cpu/online")) or "").strip()
    smt_text = (read_text(Path("/sys/devices/system/cpu/smt/active")) or "n/a").strip()
    rows = [
        result("Isolated CPUs", "INFO", isolated_text or "not configured"),
        result("nohz_full CPUs", "INFO", nohz_text or "not configured"),
        result("Online CPUs", "INFO", online_text or "not reported"),
        result("SMT active", "INFO", smt_text),
    ]

    isolated_cpus = expand_cpu_list(isolated_text)
    sibling_warnings = []
    for cpu in sorted(isolated_cpus):
        sibling_path = Path(
            f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list"
        )
        sibling_text = (read_text(sibling_path) or "").strip()
        siblings = expand_cpu_list(sibling_text)
        outside = sorted(siblings - isolated_cpus)
        if outside:
            sibling_warnings.append(
                f"cpu{cpu} sibling set {sibling_text} includes non-isolated "
                f"CPU(s): {','.join(str(item) for item in outside)}"
            )
    rows.append(
        result(
            "SMT sibling pairing",
            "WARN" if sibling_warnings else "OK",
            "\n".join(sibling_warnings) or "check completed",
        )
    )
    return rows


def check_hugepage_allocation() -> list[CheckResult]:
    """Report hugepage allocation, hugetlbfs mounts, and NUMA free pages."""

    memory_info = read_text(Path("/proc/meminfo")) or ""
    wanted = re.compile(
        r"^(?:HugePages_Total|HugePages_Free|HugePages_Rsvd|HugePages_Surp|"
        r"Hugepagesize|Hugetlb):",
        re.MULTILINE,
    )
    values = [line for line in memory_info.splitlines() if wanted.match(line)]
    rows = [
        result(
            "Hugepage allocation",
            "INFO" if values else "WARN",
            "\n".join(values) or "hugepage values not found in /proc/meminfo",
        )
    ]

    mount = run_command(["findmnt", "-t", "hugetlbfs"])
    rows.append(
        result(
            "hugetlbfs mount",
            "OK" if mount.returncode == 0 else "WARN",
            mount.stdout or "no hugetlbfs mount",
        )
    )
    if command_path("virsh"):
        freepages = run_command(["virsh", "freepages", "--all"])
        rows.append(
            result(
                "NUMA hugepage allocation",
                "INFO" if freepages.returncode == 0 else "WARN",
                freepages.stdout or freepages.stderr or "virsh freepages --all failed",
            )
        )
    else:
        rows.append(result("NUMA hugepage allocation", "WARN", "virsh unavailable"))
    return rows


def check_irq_placement() -> list[CheckResult]:
    """Check irqbalance configuration and IRQ/process use of isolated CPUs."""

    isolated_text = (
        read_text(Path("/sys/devices/system/cpu/isolated")) or ""
    ).strip()
    isolated_cpus = expand_cpu_list(isolated_text)
    irqbalance = run_command(["systemctl", "is-active", "--quiet", "irqbalance"])
    rows = [
        result(
            "irqbalance",
            "OK" if irqbalance.returncode == 0 else "WARN",
            "active" if irqbalance.returncode == 0 else "not active",
        )
    ]

    irqbalance_config = read_text(Path("/etc/default/irqbalance")) or ""
    banned_setting = next(
        (
            line.strip()
            for line in irqbalance_config.splitlines()
            if re.match(r"^IRQBALANCE_BANNED_CPU", line)
        ),
        "",
    )
    rows.append(
        result(
            "IRQBALANCE_BANNED_CPU",
            "OK" if banned_setting else "FAIL",
            banned_setting or "not configured in /etc/default/irqbalance",
        )
    )

    irq_hits = []
    affinity_paths = Path("/proc/irq").glob("[0-9]*/effective_affinity_list")
    for affinity_path in sorted(affinity_paths):
        affinity_text = (read_text(affinity_path) or "").strip()
        if isolated_cpus & expand_cpu_list(affinity_text):
            irq_hits.append(f"IRQ {affinity_path.parent.name}: {affinity_text}")
    rows.append(
        result(
            "IRQ affinity on isolated CPUs",
            "INFO" if irq_hits else "OK",
            "\n".join(irq_hits) or "no effective-affinity overlap",
        )
    )

    if not isolated_cpus:
        rows.append(
            result(
                "Processes on isolated CPUs",
                "INFO",
                "CORE   PPID     PID      PROCESS\n"
                "skipped; no isolated CPUs",
            )
        )
        return rows
    processes = run_command(["ps", "-eLo", "psr=,ppid=,pid=,comm="])
    matching_processes = []
    for line in processes.stdout.splitlines():
        fields = line.split(maxsplit=3)
        if fields and fields[0].isdigit() and int(fields[0]) in isolated_cpus:
            process_name = fields[3] if len(fields) == 4 else ""
            matching_processes.append(
                f"{fields[0]:<6} {fields[1]:<8} {fields[2]:<8} {process_name}"
            )
    process_output = "CORE   PPID     PID      PROCESS\n"
    if matching_processes:
        process_output += "\n".join(matching_processes[:20])
    else:
        process_output += "none found"
    rows.append(
        result(
            "Processes on isolated CPUs",
            "INFO",
            process_output,
        )
    )
    return rows


def check_nic_passthrough() -> list[CheckResult]:
    """Check IOMMU groups, persistent VFIO overrides, and vfio_pci."""

    iommu_directory = Path("/sys/kernel/iommu_groups")
    groups = list(iommu_directory.iterdir()) if iommu_directory.is_dir() else []
    rows = [
        result(
            "IOMMU groups",
            "OK" if groups else "FAIL",
            f"{len(groups)} group(s) found" if groups else "no IOMMU groups",
        )
    ]

    if command_path("driverctl"):
        overrides = run_command(["driverctl", "list-overrides"])
        rows.append(
            result(
                "driverctl overrides",
                "INFO" if overrides.stdout else "WARN",
                overrides.stdout or overrides.stderr or "no device overrides",
            )
        )
        vfio_devices = []
        for line in overrides.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[1] == "vfio-pci":
                vfio_devices.append(fields[0])
        if vfio_devices:
            details = []
            for pci_address in vfio_devices:
                pci = run_command(["lspci", "-nnks", pci_address])
                details.append(
                    pci.stdout or f"unable to query {pci_address} with lspci"
                )
            rows.append(result("vfio-pci devices", "INFO", "\n\n".join(details)))
        else:
            rows.append(result("vfio-pci devices", "WARN", "no driver overrides"))
    else:
        rows.append(result("driverctl overrides", "WARN", "driverctl unavailable"))

    modules = run_command(["lsmod"])
    vfio_loaded = bool(re.search(r"^vfio_pci\s", modules.stdout, re.MULTILINE))
    rows.append(
        result(
            "vfio_pci module",
            "OK" if vfio_loaded else "WARN",
            "loaded" if vfio_loaded else "not loaded",
        )
    )
    return rows


def check_nova_cpu_passthrough_config() -> list[CheckResult]:
    """Report Nova CPU pinning, memory reservation, PCI, and hugepage settings."""

    nova_path = Path(
        os.environ.get("NOVA_CONF", "/opt/pf9/etc/nova/conf.d/nova_override.conf")
    )
    content = read_text(nova_path)
    if content is None:
        return [result("nova.conf", "WARN", f"{nova_path} is not readable")]

    configured = parse_key_value_config(content)
    rows = []
    for key in ("cpu_dedicated_set", "cpu_shared_set", "reserved_host_memory_mb"):
        value = configured.get(key)
        rows.append(result(key, "INFO" if value else "WARN", value or "not configured"))
    related = [
        line.strip()
        for line in content.splitlines()
        if re.match(r"^\s*(?:device_spec|alias|reserved_huge_pages)\s*=", line)
    ]
    rows.append(
        result(
            "PCI aliases, device specs, or reserved hugepages",
            "INFO" if related else "WARN",
            "\n".join(related) or "not configured",
        )
    )
    return rows


def conditional_resource_isolation_reports() -> list[tuple[str, list[CheckResult]]]:
    """Return checks enabled by detected CPU, memory, and VFIO settings."""

    reports: list[tuple[str, list[CheckResult]]] = []

    cmdline = (read_text(Path("/proc/cmdline")) or "").strip()
    dedicated_resources_configured = bool(
        re.search(
            r"(?:^|\s)(?:isolcpus|hugepages|hugepagesz|default_hugepagesz)=\S+",
            cmdline,
        )
    )
    if dedicated_resources_configured:
        reports.extend(
            [
                ("KERNEL COMMAND LINE", check_kernel_cpu_parameters()),
                ("CPU ISOLATION", check_cpu_isolation()),
                ("CURRENT HUGEPAGE ALLOCATION", check_hugepage_allocation()),
                ("IRQ PLACEMENT", check_irq_placement()),
            ]
        )
    else:
        skipped = "no dedicated CPU or memory configuration setting found"
        reports.extend(
            [
                (title, [result("Resource isolation settings", "INFO", skipped)])
                for title in (
                    "KERNEL COMMAND LINE",
                    "CPU ISOLATION",
                    "CURRENT HUGEPAGE ALLOCATION",
                    "IRQ PLACEMENT",
                )
            ]
        )

    modules = run_command(["lsmod"])
    vfio_pci_loaded = bool(
        re.search(r"^vfio_pci\s", modules.stdout, re.MULTILINE)
    ) or Path("/sys/module/vfio_pci").is_dir()
    if vfio_pci_loaded:
        reports.append(("NIC PASSTHROUGH CONFIGURATION", check_nic_passthrough()))
    else:
        reports.append(
            (
                "NIC PASSTHROUGH CONFIGURATION",
                [
                    result(
                        "NIC passthrough settings",
                        "INFO",
                        "no NIC passthrough settings configured",
                    )
                ],
            )
        )

    return reports


def resource_isolation_reports() -> list[tuple[str, list[CheckResult]]]:
    """Return the complete standalone resource-isolation report."""

    reports = [("VIRTUALIZATION AND KVM", check_cpu_virtualization())]
    reports.extend(conditional_resource_isolation_reports())
    reports.append(
        (
            "NOVA CPU AND PASSTHROUGH CONFIGURATION",
            check_nova_cpu_passthrough_config(),
        )
    )
    return reports


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""

    parser = argparse.ArgumentParser(
        description="Run Platform9 host readiness and storage checks.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "actions",
        nargs="*",
        metavar="CHECK",
        help=(
            "optional standalone check: check-sudoers, check-mpath-orphan, "
            "list-nvme-vm, list-vm-mpath, check-glance-mount, or "
            "check-control-plane"
        ),
    )
    parser.add_argument("--virsh", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--hosts",
        action="store_true",
        help="include host, hostconfig profile, and cluster mappings; requires check-control-plane",
    )
    parser.add_argument(
        "--region",
        help="OpenStack region for check-control-plane; defaults to OS_REGION_NAME",
    )
    parser.add_argument("--uuid", help="check one virsh VM and its multipath disks")
    parser.add_argument(
        "--all-optional",
        action="store_true",
        help=(
            "run all optional checks, including resource-isolation settings, "
            "except the passwordless sudo user listing; results are included "
            "in requested log, JSON, and PDF reports"
        ),
    )
    parser.add_argument(
        "--run-all",
        action="store_true",
        help=(
            "run every non-parameterized check, including passwordless sudo, "
            "standalone storage checks, and resource-isolation checks; "
            "check-control-plane is excluded"
        ),
    )
    parser.add_argument(
        "--resource-isolate-settings",
        action="store_true",
        help="run only CPU, hugepage, IRQ, KVM, and PCI passthrough checks",
    )
    parser.add_argument(
        "--storage-check",
        action="store_true",
        help=(
            "run only NVMe, iSCSI initiator, FC ports, iscsid configuration, "
            "multipath blacklist, and LVM filter checks"
        ),
    )
    parser.add_argument(
        "--nvme-config",
        action="store_true",
        help="include the NVMe configuration check",
    )
    parser.add_argument(
        "--glance-mount-dir",
        type=Path,
        default=DEFAULT_GLANCE_MOUNT,
        help="directory used by check-glance-mount",
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--log",
        action="store_true",
        help="write a timestamped plain-text copy of the report",
    )
    output_group.add_argument("--output", type=Path, help="write a plain-text report")
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="write a timestamped color-coded PDF report",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="write a timestamped machine-parseable JSON report",
    )
    return parser


def normalize_legacy_arguments(arguments: Sequence[str]) -> list[str]:
    """Translate the Bash script's optional positional mount directory."""

    normalized: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        normalized.append(argument)
        if argument == "check-glance-mount" and index + 1 < len(arguments):
            candidate = arguments[index + 1]
            if not candidate.startswith("-") and candidate not in SUPPORTED_ACTIONS:
                normalized.extend(["--glance-mount-dir", candidate])
                index += 1
        index += 1
    return normalized


def validate_actions(parser: argparse.ArgumentParser, actions: Sequence[str]) -> list[str]:
    """Validate positional checks while accepting the Bash script's mount syntax."""

    invalid = [action for action in actions if action not in SUPPORTED_ACTIONS]
    if invalid:
        parser.error(
            f"unknown check(s): {', '.join(invalid)}; choose from "
            f"{', '.join(sorted(SUPPORTED_ACTIONS))}"
        )
    return list(dict.fromkeys(actions))


def status_text(status: str) -> Text:
    """Return a color-coded Rich status label."""

    styles = {
        "OK": "bold green",
        "FAIL": "bold red",
        "WARN": "bold yellow",
        "INFO": "cyan",
        "non-nVMe": "cyan",
        "non-multipath disk": "cyan",
        "ERROR": "bold red",
    }
    return Text(status, style=styles.get(status, "white"))


def comparison_table(row: CheckResult) -> Table:
    """Render actual and expected values as a color-coded nested table."""

    table = Table(box=box.ROUNDED, show_header=True, padding=(0, 1))
    table.add_column("Actual", overflow="fold")
    table.add_column("Expected", overflow="fold")
    actual_styles = {
        "OK": "bold green",
        "WARN": "bold yellow",
        "FAIL": "bold red",
        "ERROR": "bold red",
    }
    table.add_row(
        Text(row.actual or "unset", style=actual_styles.get(row.status, "white")),
        Text(row.expected or "-", style="bold cyan"),
    )
    return table


def report_name_column(title: str) -> str:
    """Return the first-column heading for a report section."""

    if title == "VM NVME ATTACHMENTS":
        return "VM UUID->root Disk"
    if title == "HOSTCONFIG NETWORK LABELS":
        return "Hostconfig Profile"
    if title == "PROVIDER NETWORKS":
        return "Network Label"
    if title == "STORAGE BACKEND CONFIGURATION":
        return "Blueprint"
    if title == "HOSTS":
        return "Hostname"
    return "Check"


def render_section(console: Console, title: str, rows: Iterable[CheckResult]) -> None:
    """Render one rounded Rich table."""

    table = Table(
        title=title,
        title_justify="left",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column(
        report_name_column(title), style="bold cyan", no_wrap=True, ratio=1
    )
    if title == "STORAGE BACKEND CONFIGURATION":
        table.add_column("Backend Name", style="bold", overflow="fold", ratio=1)
        table.add_column("Sections", overflow="fold", ratio=2)
    elif title == "HOSTS":
        table.add_column("Hostconfig Profile", overflow="fold", ratio=2)
        table.add_column("Cluster Name", overflow="fold", ratio=2)
    else:
        status_width = 20 if title == "VM DISK MULTIPATH" else 8
        table.add_column("Status", justify="center", no_wrap=True, width=status_width)
        table.add_column("Output", overflow="fold", ratio=3)
    for row in rows:
        output = comparison_table(row) if row.expected is not None else row.output or "-"
        if title == "STORAGE BACKEND CONFIGURATION":
            sections = "\n".join(row.backend_sections or ()) or row.output or "-"
            table.add_row(
                row.name,
                row.backend_name or "-",
                sections,
            )
        elif title == "HOSTS":
            table.add_row(
                row.name,
                row.hostconfig_name or "-",
                row.cluster_name or row.output or "-",
            )
        else:
            table.add_row(row.name, status_text(row.status), output)
    console.print(table)
    console.print()


def render_report_metadata(
    console: Console,
    host_name: str,
    generated_at: dt.datetime,
) -> None:
    """Render host and generation time in a consistent top-level table."""

    table = Table(
        title="hostInfo-check",
        title_justify="left",
        box=box.ROUNDED,
        show_header=True,
    )
    table.add_column("Host Name", style="bold cyan", ratio=1)
    table.add_column("Report Time", style="bold", ratio=1)
    table.add_row(host_name, generated_at.strftime("%Y-%m-%d %H:%M:%S %Z"))
    console.print(table)
    console.print()


def pdf_paragraph_text(value: str) -> str:
    """Escape plain text and preserve its line breaks for ReportLab."""

    return escape(value).replace("\n", "<br/>")


def chunk_report_output(
    value: str,
    character_limit: int = 1_800,
    line_limit: int = 32,
) -> list[str]:
    """Split long output so individual PDF table rows can span pages safely."""

    if not value:
        return ["-"]
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for line in value.splitlines() or [value]:
        while len(line) > character_limit:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_length = 0
            chunks.append(line[:character_limit])
            line = line[character_limit:]
        projected = current_length + len(line) + (1 if current else 0)
        if current and (projected > character_limit or len(current) >= line_limit):
            chunks.append("\n".join(current))
            current = [line]
            current_length = len(line)
        else:
            current.append(line)
            current_length = projected
    if current:
        chunks.append("\n".join(current))
    return chunks or ["-"]


def write_pdf_report(
    destination: Path,
    reports: Sequence[tuple[str, list[CheckResult]]],
    host_name: str,
    generated_at: dt.datetime,
) -> None:
    """Write a paginated PDF that preserves the report's status colors."""

    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            LongTable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table as PdfTable,
            TableStyle,
        )
    except ImportError as error:
        raise RuntimeError(
            "PDF output requires ReportLab; install it with "
            "'python3 -m pip install reportlab'"
        ) from error

    destination.parent.mkdir(parents=True, exist_ok=True)
    page_size = landscape(A4)
    document = SimpleDocTemplate(
        str(destination),
        pagesize=page_size,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Host check report - {host_name}",
        author="hostinfo_check.py",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        textColor=colors.HexColor("#0f172a"),
        fontSize=18,
        leading=22,
        spaceAfter=5 * mm,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontName="Courier",
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#0f172a"),
        wordWrap="CJK",
    )
    check_style = ParagraphStyle(
        "CheckName",
        parent=body_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0891b2"),
    )
    centered_style = ParagraphStyle(
        "Centered",
        parent=body_style,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )
    header_style = ParagraphStyle(
        "Header",
        parent=centered_style,
        fontSize=8,
        textColor=colors.white,
    )
    status_colors = {
        "OK": colors.HexColor("#16a34a"),
        "FAIL": colors.HexColor("#dc2626"),
        "WARN": colors.HexColor("#d97706"),
        "INFO": colors.HexColor("#0891b2"),
        "non-nVMe": colors.HexColor("#0891b2"),
        "non-multipath disk": colors.HexColor("#0891b2"),
        "ERROR": colors.HexColor("#dc2626"),
    }

    def status_paragraph(status: str) -> object:
        return Paragraph(
            status,
            ParagraphStyle(
                f"Status{status or 'Blank'}",
                parent=centered_style,
                textColor=status_colors.get(status, colors.HexColor("#0f172a")),
            ),
        )

    def page_footer(canvas: object, doc: object) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(12 * mm, 7 * mm, f"Host: {host_name}")
        canvas.drawRightString(
            page_size[0] - 12 * mm,
            7 * mm,
            f"Page {doc.page}",
        )
        canvas.restoreState()

    available_width = page_size[0] - document.leftMargin - document.rightMargin
    column_widths = [available_width * 0.22, available_width * 0.10, available_width * 0.68]
    metadata_table = PdfTable(
        [
            [Paragraph("Host Name", header_style), Paragraph("Report Time", header_style)],
            [
                Paragraph(pdf_paragraph_text(host_name), check_style),
                Paragraph(
                    pdf_paragraph_text(generated_at.strftime("%Y-%m-%d %H:%M:%S %Z")),
                    body_style,
                ),
            ],
        ],
        colWidths=[available_width / 2, available_width / 2],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        ),
    )
    story = [
        Paragraph("Host Information Check Report", title_style),
        metadata_table,
        Spacer(1, 5 * mm),
    ]

    for section_title, rows in reports:
        story.append(
            PdfTable(
                [[Paragraph(pdf_paragraph_text(section_title), header_style)]],
                colWidths=[available_width],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
                        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#334155")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                ),
            )
        )
        is_blueprint_section = section_title == "STORAGE BACKEND CONFIGURATION"
        is_hosts_section = section_title == "HOSTS"
        section_column_widths = column_widths
        if is_blueprint_section:
            section_column_widths = [
                available_width * 0.25,
                available_width * 0.30,
                available_width * 0.45,
            ]
            table_data: list[list[object]] = [
                [
                    Paragraph("Blueprint", header_style),
                    Paragraph("Backend Name", header_style),
                    Paragraph("Sections", header_style),
                ]
            ]
        elif is_hosts_section:
            section_column_widths = [
                available_width * 0.30,
                available_width * 0.40,
                available_width * 0.30,
            ]
            table_data = [
                [
                    Paragraph("Hostname", header_style),
                    Paragraph("Hostconfig Profile", header_style),
                    Paragraph("Cluster Name", header_style),
                ]
            ]
        else:
            table_data = [
                [
                    Paragraph(report_name_column(section_title), header_style),
                    Paragraph("Status", header_style),
                    Paragraph("Output", header_style),
                ]
            ]
        for row in rows:
            if row.expected is not None:
                actual_color = status_colors.get(row.status, colors.HexColor("#0f172a"))
                comparison = PdfTable(
                    [
                        [
                            Paragraph("Actual", header_style),
                            Paragraph("Expected", header_style),
                        ],
                        [
                            Paragraph(
                                pdf_paragraph_text(row.actual or "unset"),
                                ParagraphStyle(
                                    f"Actual{len(table_data)}",
                                    parent=body_style,
                                    textColor=actual_color,
                                    fontName="Courier-Bold",
                                ),
                            ),
                            Paragraph(
                                pdf_paragraph_text(row.expected),
                                ParagraphStyle(
                                    f"Expected{len(table_data)}",
                                    parent=body_style,
                                    textColor=colors.HexColor("#0891b2"),
                                    fontName="Courier-Bold",
                                ),
                            ),
                        ],
                    ],
                    colWidths=[column_widths[2] / 2 - 4, column_widths[2] / 2 - 4],
                    style=TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ]
                    ),
                )
                outputs: list[object] = [comparison]
                if row.output:
                    outputs.append(Paragraph(pdf_paragraph_text(row.output), body_style))
                output_cell: object = outputs[0] if len(outputs) == 1 else outputs
                table_data.append(
                    [
                        Paragraph(pdf_paragraph_text(row.name), check_style),
                        status_paragraph(row.status),
                        output_cell,
                    ]
                )
                continue

            if is_blueprint_section:
                sections = "\n".join(row.backend_sections or ()) or row.output or "-"
                table_data.append(
                    [
                        Paragraph(pdf_paragraph_text(row.name), check_style),
                        Paragraph(
                            pdf_paragraph_text(row.backend_name or "-"), body_style
                        ),
                        Paragraph(pdf_paragraph_text(sections), body_style),
                    ]
                )
                continue

            if is_hosts_section:
                table_data.append(
                    [
                        Paragraph(pdf_paragraph_text(row.name), check_style),
                        Paragraph(
                            pdf_paragraph_text(row.hostconfig_name or "-"), body_style
                        ),
                        Paragraph(
                            pdf_paragraph_text(
                                row.cluster_name or row.output or "-"
                            ),
                            body_style,
                        ),
                    ]
                )
                continue

            chunks = chunk_report_output(row.output or "-")
            for chunk_index, chunk in enumerate(chunks):
                row_name = row.name if chunk_index == 0 else "(continued)"
                table_data.append(
                    [
                        Paragraph(pdf_paragraph_text(row_name), check_style),
                        status_paragraph(row.status if chunk_index == 0 else ""),
                        Paragraph(pdf_paragraph_text(chunk), body_style),
                    ]
                )

        table_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ]
        story.append(
            LongTable(
                table_data,
                colWidths=section_column_widths,
                repeatRows=1,
                splitByRow=1,
                style=TableStyle(table_style),
            )
        )
        story.append(Spacer(1, 5 * mm))

    document.build(story, onFirstPage=page_footer, onLaterPages=page_footer)


def timestamped_path(path: Path, generated_at: dt.datetime) -> Path:
    """Append the run timestamp before a requested filename extension."""

    timestamp = generated_at.strftime("%Y%m%d_%H%M%S")
    if path.suffix:
        return path.with_name(f"{path.stem}-{timestamp}{path.suffix}")
    return path.with_name(f"{path.name}-{timestamp}")


def text_output_path(
    arguments: argparse.Namespace,
    generated_at: dt.datetime,
    host_name: str,
) -> Path | None:
    if arguments.output:
        return timestamped_path(arguments.output, generated_at)
    if arguments.log:
        timestamp = generated_at.strftime("%Y%m%d_%H%M%S")
        return Path(f"hostcheck-{host_name}-{timestamp}.log")
    return None


def write_json_report(
    destination: Path,
    reports: Sequence[tuple[str, list[CheckResult]]],
    host_name: str,
    generated_at: dt.datetime,
) -> None:
    """Write a stable, machine-parseable representation of all checks."""

    checks = [row for _, rows in reports for row in rows]
    if any(row.status in {"FAIL", "ERROR"} for row in checks):
        overall_status = "FAIL"
    elif any(row.status == "WARN" for row in checks):
        overall_status = "WARN"
    else:
        overall_status = "OK"

    payload = {
        "schema_version": 1,
        "report_name": "hostInfo-check",
        "host_name": host_name,
        "generated_at": generated_at.isoformat(),
        "overall_status": overall_status,
        "sections": [
            {
                "name": section_name,
                "checks": [
                    {
                        "name": row.name,
                        "status": row.status,
                        "actual": row.actual,
                        "expected": row.expected,
                        "backend_name": row.backend_name,
                        "backend_sections": row.backend_sections,
                        "hostconfig_name": row.hostconfig_name,
                        "cluster_name": row.cluster_name,
                        "output": row.output,
                    }
                    for row in rows
                ],
            }
            for section_name, rows in reports
        ],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def storage_reports(
    *, include_nvme: bool = False
) -> list[tuple[str, list[CheckResult]]]:
    """Run the core host-storage checks in their normal report order."""

    reports = [
        ("ISCSI INITIATOR", check_iscsi_initiator()),
        ("FC PORTS", check_fc_ports()),
        ("ISCSID CONF", check_iscsid_conf()),
        ("MULTIPATH BLACKLIST", check_multipath_blacklist()),
        ("LVM FILTERS", check_lvm_filters()),
    ]
    if include_nvme:
        reports.insert(0, ("NVME CONFIGURATION", check_nvme_configuration()))
    return reports


def run_selected_checks(
    arguments: argparse.Namespace, operating_system: OperatingSystem
) -> list[tuple[str, list[CheckResult]]]:
    """Apply the Bash script's check-selection behavior."""

    if arguments.storage_check and not arguments.run_all:
        return storage_reports(include_nvme=True)

    actions = (
        set(SUPPORTED_ACTIONS) - {"check-control-plane"}
        if arguments.run_all
        else set(arguments.actions)
    )
    run_all_optional = arguments.all_optional or arguments.run_all
    if actions == {"check-control-plane"} and not run_all_optional:
        return control_plane_reports(
            include_hosts=arguments.hosts,
            region=arguments.region,
        )
    if actions == {"check-sudoers"} and not run_all_optional:
        reports = [("PASSWORDLESS SUDO", check_sudoers())]
        if arguments.nvme_config:
            reports.append(("NVME CONFIGURATION", check_nvme_configuration()))
        return reports

    reports = [("ENVIRONMENT", check_environment(operating_system))]
    standalone = actions & {
        "check-mpath-orphan",
        "list-nvme-vm",
        "list-vm-mpath",
        "check-glance-mount",
        "check-control-plane",
    }
    if run_all_optional:
        standalone.update(
            {
                "check-mpath-orphan",
                "list-nvme-vm",
                "list-vm-mpath",
                "check-glance-mount",
            }
        )
    if standalone:
        if "check-mpath-orphan" in standalone:
            reports.append(("MULTIPATH ORPHANS", check_multipath_orphans()))
        if "list-nvme-vm" in standalone:
            reports.append(("VM NVME ATTACHMENTS", check_vm_nvme_attachments()))
        if "list-vm-mpath" in standalone:
            reports.append(("VM DISK MULTIPATH", check_vm_disk_multipath()))
        if "check-glance-mount" in standalone:
            reports.append(
                ("GLANCE IMAGE MOUNT", check_glance_mount(arguments.glance_mount_dir))
            )
        if "check-control-plane" in standalone:
            reports.extend(
                control_plane_reports(
                    include_hosts=arguments.hosts,
                    region=arguments.region,
                )
            )
        if not run_all_optional:
            if arguments.nvme_config:
                reports.append(("NVME CONFIGURATION", check_nvme_configuration()))
            return reports
    if arguments.uuid:
        reports.append(("VIRSH VM", check_virsh_vm(arguments.uuid)))
        if not arguments.run_all:
            if arguments.nvme_config:
                reports.append(("NVME CONFIGURATION", check_nvme_configuration()))
            return reports

    if "check-sudoers" in actions and (
        arguments.run_all or not arguments.all_optional
    ):
        reports.append(("PASSWORDLESS SUDO", check_sudoers()))
    reports.extend(
        [
            ("CHECK BOND MODE", check_bond()),
            ("NTP", check_ntp()),
            ("SYSCTL SETTINGS", check_sysctl_settings()),
            ("PACKAGES", check_packages(operating_system)),
            ("SERVICES", check_services()),
        ]
    )
    reports.extend(
        storage_reports(include_nvme=arguments.nvme_config or arguments.run_all)
    )
    reports.extend(
        [
            ("PF9 PACKAGES", check_pf9_packages(operating_system)),
            ("PF9 SERVICES", check_pf9_services(operating_system)),
            (
                "PF9 SERVICE FILESYSTEMS",
                check_pf9_service_filesystems(operating_system),
            ),
            ("OVS BRIDGES", check_ovs_bridges()),
            ("/ETC/HOSTS ENTRIES", check_hosts()),
            ("/ETC/FSTAB ENTRIES", check_fstab()),
            ("VIRSH LIVENESS", check_virsh_responsiveness()),
            ("GROUP CONSISTENCY", check_group_consistency()),
            ("RSYSLOG PF9 RULES", check_rsyslog_pf9_rules()),
            ("PF9 USER AND GROUP", check_pf9_user_group()),
        ]
    )
    if run_all_optional:
        reports.extend(resource_isolation_reports())
    else:
        reports.extend(conditional_resource_isolation_reports())
    return reports


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args(normalize_legacy_arguments(sys.argv[1:]))
    arguments.actions = validate_actions(parser, arguments.actions)
    if (
        arguments.region is not None
        and "check-control-plane" not in arguments.actions
    ):
        parser.error("--region requires the check-control-plane argument")
    if arguments.hosts and "check-control-plane" not in arguments.actions:
        parser.error("--hosts requires the check-control-plane argument")
    if arguments.hosts and arguments.run_all:
        parser.error("--hosts cannot be combined with --run-all")
    if arguments.hosts and arguments.storage_check and not arguments.run_all:
        parser.error("--hosts cannot be combined with --storage-check")
    if (
        arguments.hosts
        and arguments.resource_isolate_settings
        and not arguments.run_all
    ):
        parser.error("--hosts cannot be combined with --resource-isolate-settings")
    if "check-control-plane" in arguments.actions and not arguments.run_all:
        try:
            for variable_name in REQUIRED_OPENSTACK_ENVIRONMENT:
                required_environment_value(variable_name)
        except RuntimeError as error:
            parser.exit(2, f"ERROR: {error}\n")
    sudoers_only = (
        arguments.actions == ["check-sudoers"]
        and not arguments.all_optional
        and not arguments.run_all
        and not arguments.nvme_config
    )
    storage_only = arguments.storage_check and not arguments.run_all
    resource_isolation_only = (
        arguments.resource_isolate_settings and not arguments.run_all
    )

    console = Console(record=True)
    host_name = socket.gethostname().split(".")[0]
    generated_at = dt.datetime.now().astimezone()
    try:
        if storage_only:
            reports = storage_reports(include_nvme=True)
        elif resource_isolation_only:
            reports = resource_isolation_reports()
            if arguments.nvme_config:
                reports.append(("NVME CONFIGURATION", check_nvme_configuration()))
        elif sudoers_only:
            reports = [("PASSWORDLESS SUDO", check_sudoers())]
        else:
            operating_system = detect_operating_system()
            reports = run_selected_checks(arguments, operating_system)
    except RuntimeError as error:
        render_section(
            console,
            "HOST CHECK ERROR",
            [result("Initialization", "ERROR", str(error))],
        )
        return 2

    if not sudoers_only:
        render_report_metadata(console, host_name, generated_at)
    for title, rows in reports:
        render_section(console, title, rows)
    if arguments.hosts:
        try:
            remove_host_list()
            remove_cluster_list()
        except OSError as error:
            console.print(
                "[bold red]ERROR:[/bold red] cannot delete temporary JSON "
                f"resource: {error}"
            )
            return 2

    text_destination = text_output_path(arguments, generated_at, host_name)
    if text_destination:
        try:
            text_destination.parent.mkdir(parents=True, exist_ok=True)
            text_destination.write_text(console.export_text(), encoding="utf-8")
        except OSError as error:
            console.print(
                f"[bold red]ERROR:[/bold red] cannot write {text_destination}: {error}"
            )
            return 2
        console.print(f"Report written to [cyan]{text_destination}[/cyan]")

    if arguments.pdf:
        timestamp = generated_at.strftime("%Y%m%d_%H%M%S")
        pdf_destination = Path(f"hostcheck-{host_name}-{timestamp}.pdf")
        try:
            write_pdf_report(
                pdf_destination,
                reports,
                host_name,
                generated_at,
            )
        except (OSError, RuntimeError) as error:
            console.print(
                f"[bold red]ERROR:[/bold red] cannot write {pdf_destination}: {error}"
            )
            return 2
        console.print(f"PDF report written to [cyan]{pdf_destination}[/cyan]")

    if arguments.json:
        timestamp = generated_at.strftime("%Y%m%d_%H%M%S")
        json_destination = Path(f"hostcheck-{host_name}-{timestamp}.json")
        try:
            write_json_report(
                json_destination,
                reports,
                host_name,
                generated_at,
            )
        except OSError as error:
            console.print(
                f"[bold red]ERROR:[/bold red] cannot write {json_destination}: {error}"
            )
            return 2
        console.print(f"JSON report written to [cyan]{json_destination}[/cyan]")

    failed = any(row.status in {"FAIL", "ERROR"} for _, rows in reports for row in rows)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
