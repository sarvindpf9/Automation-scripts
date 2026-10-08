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
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
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
COMMAND_TIMEOUT = 15
SUPPORTED_ACTIONS = {
    "check-sudoers",
    "check-mpath-orphan",
    "list-vm-mpath",
    "check-glance-mount",
}


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
            "OK" if mode == "744" else "FAIL",
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
        return [result("Bond interfaces", "FAIL", "no bond interfaces found")]

    rows: list[CheckResult] = []
    for interface in interfaces:
        content = read_text(Path("/proc/net/bonding") / interface) or ""
        mode_match = re.search(r"^Bonding Mode:\s*(.*)$", content, re.MULTILINE)
        mode = mode_match.group(1) if mode_match else "unknown"
        address = run_command(
            ["ip", "-4", "-o", "addr", "show", "dev", interface, "scope", "global"]
        )
        addresses = re.findall(r"\binet\s+(\S+)", address.stdout)
        rows.append(
            result(
                interface,
                "OK" if "802.3ad" in mode else "WARN",
                f"mode: {mode}; IP: {', '.join(addresses) or 'none'}",
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
            "OK" if actual == "15" else ("WARN" if actual else "FAIL"),
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
        return [result("PF9 rsyslog rules", "FAIL", f"{directory} not found")]
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
                "OK" if matches else "FAIL",
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


def check_pf9_services() -> list[CheckResult]:
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
    if status_by_name.get("pf9-ostackhost.service") == "OK":
        nova_path = Path("/opt/pf9/etc/nova/conf.d/nova_override.conf")
        content = read_text(nova_path)
        if content is None:
            rows.append(result("nova_override.conf", "WARN", "missing or unreadable"))
        else:
            match = re.search(r"^\s*volume_use_multipath\s*=.*$", content, re.MULTILINE)
            rows.append(
                result(
                    "nova volume_use_multipath",
                    "OK" if match else "WARN",
                    match.group(0).strip() if match else "setting is absent",
                )
            )
            rows.append(result("nova_override.conf content", "INFO", content))
        rows.append(result("Libvirt VM inventory", "INFO", compare_libvirt_inventory()))

    if status_by_name.get("pf9-cindervolume-base.service") == "OK":
        cinder_path = Path(
            "/opt/pf9/etc/pf9-cindervolume-base/conf.d/cinder_override.conf"
        )
        content = read_text(cinder_path)
        rows.append(
            result(
                "cinder_override.conf",
                "OK" if content is not None else "WARN",
                content or "missing or unreadable",
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
        return [result("VM disk multipath", "WARN", "virsh is unavailable or unresponsive")]
    virtual_machines = [name for name in domains.stdout.splitlines() if name]
    if not virtual_machines:
        return [result("VM disk multipath", "INFO", "no running VMs")]
    stanzas = parse_multipath_stanzas(run_command(["multipath", "-ll"]).stdout)
    rows: list[CheckResult] = []
    qemu_dir = Path("/etc/libvirt/qemu")
    for virtual_machine in virtual_machines:
        domain_info = run_command(["virsh", "dominfo", virtual_machine]).stdout
        uuid_match = re.search(r"^UUID:\s*(\S+)", domain_info, re.MULTILINE)
        block_list = run_command(
            ["virsh", "domblklist", "--details", virtual_machine]
        ).stdout
        devices: set[str] = set()
        for path_value in re.findall(r"(/dev/\S+)", block_list):
            direct = re.search(r"/(dm-\d+)$", path_value)
            if direct:
                devices.add(direct.group(1))
            else:
                resolved = run_command(["readlink", "-f", path_value]).stdout
                match = re.search(r"/(dm-\d+)$", resolved)
                if match:
                    devices.add(match.group(1))
        if not devices:
            xml_content = read_text(qemu_dir / f"{virtual_machine}.xml")
            if xml_content:
                devices = xml_dm_devices(xml_content)
        if not devices:
            rows.append(result(virtual_machine, "WARN", "no dm-N block devices found"))
            continue
        for device in sorted(devices):
            mapping = stanzas.get(device)
            identity = f"{virtual_machine}: {device}"
            uuid_text = uuid_match.group(1) if uuid_match else "unknown"
            if not mapping:
                rows.append(result(identity, "FAIL", f"UUID: {uuid_text}; not found in multipath"))
                continue
            map_name, stanza = mapping
            path_lines = re.findall(r"^.*\d+:\d+:\d+:\d+.*$", stanza, re.MULTILINE)
            active = [line for line in path_lines if re.search(r"\bactive\b.*\bready\b", line)]
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
                    f"UUID: {uuid_text}; map: {map_name}; {state} "
                    f"({len(active)}/{len(path_lines)} paths up)",
                )
            )
    return rows


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
            "list-vm-mpath, or check-glance-mount"
        ),
    )
    parser.add_argument("--virsh", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--uuid", help="check one virsh VM and its multipath disks")
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
        type=Path,
        metavar="FILE",
        help="write a color-coded PDF report to FILE",
    )
    parser.add_argument(
        "--json",
        type=Path,
        metavar="FILE",
        help="write a machine-parseable JSON report to FILE",
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
        "ERROR": "bold red",
    }
    return Text(status, style=styles.get(status, "white"))


def comparison_table(row: CheckResult) -> Table:
    """Render actual and expected values as a color-coded nested table."""

    table = Table(box=box.ROUNDED, show_header=True, expand=True, padding=(0, 1))
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


def render_section(console: Console, title: str, rows: Iterable[CheckResult]) -> None:
    """Render one rounded Rich table."""

    table = Table(title=title, box=box.ROUNDED, show_lines=True, expand=True)
    table.add_column("Check", style="bold cyan", no_wrap=True, ratio=1)
    table.add_column("Status", justify="center", no_wrap=True, width=8)
    table.add_column("Output", overflow="fold", ratio=3)
    for row in rows:
        output = comparison_table(row) if row.expected is not None else row.output or "-"
        table.add_row(row.name, status_text(row.status), output)
    console.print(table)


def render_report_metadata(
    console: Console,
    host_name: str,
    generated_at: dt.datetime,
) -> None:
    """Render host and generation time in a consistent top-level table."""

    table = Table(
        title="hostInfo-check",
        box=box.ROUNDED,
        show_header=True,
        expand=True,
    )
    table.add_column("Host Name", style="bold cyan", ratio=1)
    table.add_column("Report Time", style="bold", ratio=1)
    table.add_row(host_name, generated_at.strftime("%Y-%m-%d %H:%M:%S %Z"))
    console.print(table)


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
        table_data: list[list[object]] = [
            [
                Paragraph("Check", header_style),
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

            chunks = chunk_report_output(row.output or "-")
            for chunk_index, chunk in enumerate(chunks):
                table_data.append(
                    [
                        Paragraph(
                            pdf_paragraph_text(row.name if chunk_index == 0 else "(continued)"),
                            check_style,
                        ),
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
                colWidths=column_widths,
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


def run_selected_checks(
    arguments: argparse.Namespace, operating_system: OperatingSystem
) -> list[tuple[str, list[CheckResult]]]:
    """Apply the Bash script's check-selection behavior."""

    reports = [("ENVIRONMENT", check_environment(operating_system))]
    actions = set(arguments.actions)
    standalone = actions & {
        "check-mpath-orphan",
        "list-vm-mpath",
        "check-glance-mount",
    }
    if standalone:
        if "check-mpath-orphan" in actions:
            reports.append(("MULTIPATH ORPHANS", check_multipath_orphans()))
        if "list-vm-mpath" in actions:
            reports.append(("VM DISK MULTIPATH", check_vm_disk_multipath()))
        if "check-glance-mount" in actions:
            reports.append(
                ("GLANCE IMAGE MOUNT", check_glance_mount(arguments.glance_mount_dir))
            )
        return reports
    if arguments.uuid:
        reports.append(("VIRSH VM", check_virsh_vm(arguments.uuid)))
        return reports

    if "check-sudoers" in actions:
        reports.append(("PASSWORDLESS SUDO", check_sudoers()))
    reports.extend(
        [
            ("CHECK BOND MODE", check_bond()),
            ("NTP", check_ntp()),
            ("SYSCTL SETTINGS", check_sysctl_settings()),
            ("PACKAGES", check_packages(operating_system)),
            ("SERVICES", check_services()),
            ("ISCSI INITIATOR", check_iscsi_initiator()),
            ("ISCSID CONF", check_iscsid_conf()),
            ("MULTIPATH BLACKLIST", check_multipath_blacklist()),
            ("LVM FILTERS", check_lvm_filters()),
            ("PF9 PACKAGES", check_pf9_packages(operating_system)),
            ("PF9 SERVICES", check_pf9_services()),
            ("OVS BRIDGES", check_ovs_bridges()),
            ("/ETC/HOSTS ENTRIES", check_hosts()),
            ("/ETC/FSTAB ENTRIES", check_fstab()),
            ("VIRSH LIVENESS", check_virsh_responsiveness()),
            ("GROUP CONSISTENCY", check_group_consistency()),
            ("RSYSLOG PF9 RULES", check_rsyslog_pf9_rules()),
            ("PF9 USER AND GROUP", check_pf9_user_group()),
        ]
    )
    return reports


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args(normalize_legacy_arguments(sys.argv[1:]))
    arguments.actions = validate_actions(parser, arguments.actions)

    console = Console(record=True)
    host_name = socket.gethostname().split(".")[0]
    generated_at = dt.datetime.now().astimezone()
    try:
        operating_system = detect_operating_system()
        reports = run_selected_checks(arguments, operating_system)
    except RuntimeError as error:
        render_section(
            console,
            "HOST CHECK ERROR",
            [result("Initialization", "ERROR", str(error))],
        )
        return 2

    render_report_metadata(console, host_name, generated_at)
    for title, rows in reports:
        render_section(console, title, rows)

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
        pdf_destination = timestamped_path(arguments.pdf, generated_at)
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
        json_destination = timestamped_path(arguments.json, generated_at)
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
