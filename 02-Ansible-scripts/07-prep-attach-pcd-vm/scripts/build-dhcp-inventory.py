#!/usr/bin/env python3
"""Build an Ansible inventory from Proxmox QEMU guest-agent IP data."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


MAC_PATTERN = re.compile(
    r"(?:^|,)(?:virtio|e1000|rtl8139|vmxnet3)=([0-9a-fA-F:]{17})(?:,|$)"
)


class ProxmoxClient:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        validate_certs: bool,
    ) -> None:
        self.base_url = f"https://{host}:{port}/api2/json"
        self.username = username
        self.password = password
        self.context = None if validate_certs else ssl._create_unverified_context()
        self.ticket = ""
        self.csrf_token = ""

    def authenticate(self) -> None:
        response = self.request(
            "POST",
            "/access/ticket",
            data={
                "username": self.username,
                "password": self.password,
            },
            auth_required=False,
        )
        data = response["data"]
        self.ticket = data["ticket"]
        self.csrf_token = data["CSRFPreventionToken"]

    def request(
        self,
        method: str,
        path: str,
        data: dict[str, str] | None = None,
        auth_required: bool = True,
    ) -> dict[str, Any]:
        encoded_data = None
        headers = {}

        if data is not None:
            encoded_data = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        if auth_required:
            headers["Cookie"] = f"PVEAuthCookie={self.ticket}"
            if method not in {"GET", "HEAD"}:
                headers["CSRFPreventionToken"] = self.csrf_token

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=encoded_data,
            headers=headers,
            method=method,
        )

        with urllib.request.urlopen(request, context=self.context, timeout=30) as result:
            return json.loads(result.read().decode())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-host", required=True)
    parser.add_argument("--api-port", type=int, required=True)
    parser.add_argument("--api-user", required=True)
    parser.add_argument("--validate-certs", choices=["true", "false"], required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ssh-user", default="ubuntu")
    parser.add_argument("--ssh-private-key", required=True)
    parser.add_argument("--initial-delay", type=int, default=90)
    parser.add_argument("--max-wait", type=int, default=900)
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument("--qemu-agent-enabled", choices=["true", "false"], required=True)
    return parser.parse_args()


def has_dhcp_interface(vm_config: dict[str, Any]) -> bool:
    return any(
        bool(nic.get("dhcp4", False))
        for nic in vm_config.get("network_interfaces", [])
    )


def primary_static_ip(vm_config: dict[str, Any]) -> str:
    interfaces = vm_config.get("network_interfaces", [])
    if not interfaces:
        return ""

    primary_ip = interfaces[0].get("ip", "")
    if not primary_ip:
        return ""

    return str(primary_ip).split("/", maxsplit=1)[0]


def dhcp_interface_indexes(vm_config: dict[str, Any]) -> list[int]:
    return [
        index
        for index, nic in enumerate(vm_config.get("network_interfaces", []))
        if bool(nic.get("dhcp4", False))
    ]


def vm_net_macs(config: dict[str, Any], indexes: list[int]) -> set[str]:
    macs = set()
    for index in indexes:
        value = str(config.get(f"net{index}", ""))
        match = MAC_PATTERN.search(value)
        if match:
            macs.add(match.group(1).lower())
    return macs


def usable_ipv4(value: str) -> bool:
    try:
        ip_address = ipaddress.ip_address(value)
    except ValueError:
        return False

    return not (
        ip_address.is_loopback
        or ip_address.is_link_local
        or ip_address.is_unspecified
    )


def find_interface_ip(agent_result: dict[str, Any], allowed_macs: set[str]) -> str:
    interfaces = agent_result.get("data", {}).get("result", [])
    for interface in interfaces:
        interface_mac = str(interface.get("hardware-address", "")).lower()
        if interface_mac not in allowed_macs:
            continue

        for address in interface.get("ip-addresses", []):
            if address.get("ip-address-type") != "ipv4":
                continue

            ip_value = str(address.get("ip-address", ""))
            if usable_ipv4(ip_value):
                return ip_value

    return ""


def resolve_dhcp_ip(
    client: ProxmoxClient,
    node: str,
    vm_id: int,
    allowed_macs: set[str],
    deadline: float,
    poll_interval: int,
) -> str:
    while time.monotonic() < deadline:
        try:
            agent_result = client.request(
                "GET",
                f"/nodes/{node}/qemu/{vm_id}/agent/network-get-interfaces",
            )
        except urllib.error.URLError:
            time.sleep(poll_interval)
            continue

        ip_value = find_interface_ip(agent_result, allowed_macs)
        if ip_value:
            return ip_value

        time.sleep(poll_interval)

    return ""


def yaml_scalar(value: str) -> str:
    return json.dumps(value)


def normalize_private_key_path(path: str) -> str:
    if path.endswith(".pub"):
        return path[:-4]
    return path


def effective_vm_name(vm_config: dict[str, Any], vm_key: str, prefix: Any) -> str:
    base_name = str(vm_config.get("vm_name", vm_key))
    clean_prefix = str(prefix).strip() if prefix else ""
    if not clean_prefix:
        return base_name
    return f"{clean_prefix}-{base_name}"


def write_inventory(
    output_path: Path,
    hosts: dict[str, dict[str, str]],
    ssh_user: str,
    ssh_private_key: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ssh_private_key = normalize_private_key_path(ssh_private_key)

    lines = [
        "---",
        "# Generated by scripts/build-dhcp-inventory.py",
        "all:",
        "  children:",
        "    proxmox_vms:",
        "      hosts:",
    ]

    for vm_name, host_config in sorted(hosts.items()):
        ip_value = host_config["ansible_host"]
        vm_ssh_user = host_config.get("ansible_user", ssh_user)
        lines.extend(
            [
                f"        {yaml_scalar(vm_name)}:",
                f"          ansible_host: {yaml_scalar(ip_value)}",
                f"          ansible_user: {yaml_scalar(vm_ssh_user)}",
                f"          ansible_ssh_private_key_file: {yaml_scalar(ssh_private_key)}",
                '          ansible_python_interpreter: "/usr/bin/python3"',
            ]
        )

    lines.extend(
        [
            "      vars:",
            '        ansible_become_method: "sudo"',
            '        ansible_become_user: "root"',
            "",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    password = os.environ.get("PROXMOX_API_PASSWORD", "")
    if not password:
        print("PROXMOX_API_PASSWORD is required", file=sys.stderr)
        return 1

    payload = json.load(sys.stdin)
    vms = payload.get("vms", {})
    vm_name_prefix = payload.get("vm_name_prefix", "")
    qemu_agent_enabled = args.qemu_agent_enabled == "true"
    dhcp_vms = {
        key: config
        for key, config in vms.items()
        if has_dhcp_interface(config)
    }

    if dhcp_vms and not qemu_agent_enabled:
        print(
            "DHCP inventory generation requires qemu_agent_enabled: true.",
            file=sys.stderr,
        )
        return 1

    if args.initial_delay > 0 and dhcp_vms:
        time.sleep(args.initial_delay)

    client = ProxmoxClient(
        host=args.api_host,
        port=args.api_port,
        username=args.api_user,
        password=password,
        validate_certs=args.validate_certs == "true",
    )
    client.authenticate()

    hosts: dict[str, dict[str, str]] = {}
    deadline = time.monotonic() + args.max_wait

    for vm_key, vm_config in vms.items():
        vm_name = effective_vm_name(vm_config, vm_key, vm_name_prefix)
        static_ip = primary_static_ip(vm_config)
        if static_ip:
            hosts[vm_name] = {
                "ansible_host": static_ip,
                "ansible_user": str(vm_config.get("cloud_init_user", args.ssh_user)),
            }

    for vm_key, vm_config in dhcp_vms.items():
        vm_name = effective_vm_name(vm_config, vm_key, vm_name_prefix)
        vm_id = int(vm_config["vm_id"])
        config_result = client.request(
            "GET",
            f"/nodes/{args.node}/qemu/{vm_id}/config",
        )
        macs = vm_net_macs(
            config_result.get("data", {}),
            dhcp_interface_indexes(vm_config),
        )

        if not macs:
            print(
                f"Could not find Proxmox MAC address for DHCP NIC on VM {vm_name}.",
                file=sys.stderr,
            )
            return 1

        ip_value = resolve_dhcp_ip(
            client=client,
            node=args.node,
            vm_id=vm_id,
            allowed_macs=macs,
            deadline=deadline,
            poll_interval=args.poll_interval,
        )
        if not ip_value:
            print(
                f"Timed out waiting for DHCP IPv4 from QEMU guest agent on VM {vm_name}.",
                file=sys.stderr,
            )
            return 1
        hosts[vm_name] = {
            "ansible_host": ip_value,
            "ansible_user": str(vm_config.get("cloud_init_user", args.ssh_user)),
        }

    write_inventory(
        output_path=Path(args.output).expanduser(),
        hosts=hosts,
        ssh_user=args.ssh_user,
        ssh_private_key=args.ssh_private_key,
    )
    print(f"Wrote inventory for {len(hosts)} VM(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
