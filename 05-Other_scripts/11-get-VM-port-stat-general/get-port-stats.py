#!/usr/bin/env python3

import argparse
import csv
import json
import openstack
from pathlib import Path


JSON_FILE = "all-tenant.json"

def parse_args():
    parser = argparse.ArgumentParser(
        description="Dump all-tenant VM data to JSON and generate CSV report"
    )
    parser.add_argument(
        "--cloud",
        required=True,
        help="Cloud name from clouds.yaml",
    )
    parser.add_argument(
        "--output",
        default="openstack_vm_interfaces_all_projects.csv",
        help="Output CSV file name",
    )
    return parser.parse_args()


# Dump all tenant data locally
def dump_all_tenants_to_json(conn, json_path):
    """
    Fetch all-tenant VM + ports + SGs using SDK (Epoxy-safe)
    """

    project_cache = {
        p.id: {
            "project_name": p.name,
            "project_domain_id": getattr(p, "domain_id", ""),
        }
        for p in conn.identity.projects()
    }

    all_data = []

    for server in conn.compute.servers(details=True, all_projects=True):
        vm_entry = {
            "vm_name": server.name,
            "vm_uuid": server.id,
            "project_uuid": getattr(server, "project_id", ""),
            "vm_state": getattr(server, "status", ""),
            "project_name": "",
            "project_domain_id": "",
            "ports": [],
        }

        proj = project_cache.get(server.project_id, {})
        vm_entry["project_name"] = proj.get("project_name", "")
        vm_entry["project_domain_id"] = proj.get("project_domain_id", "")

        # IMPORTANT: no fields= here
        ports = conn.network.ports(device_id=server.id)

        for port in ports:
            port_entry = {
                "interface_id": port.id,
                "interface_mac": port.mac_address,
                "interface_ip": [
                    ip.get("ip_address")
                    for ip in (port.fixed_ips or [])
                ],
                "port_security_enabled": getattr(
                    port, "port_security_enabled", None
                ),
                "security_group_ids": list(
                    getattr(port, "security_group_ids", [])
                ),
            }

            vm_entry["ports"].append(port_entry)

        all_data.append(vm_entry)

    with open(json_path, "w") as f:
        json.dump(all_data, f, indent=2)

    print(f"[INFO] JSON written to {json_path}")

def json_to_csv(json_path, csv_path, conn):
    """
    Generate CSV from previously saved JSON file
    """

    with open(json_path) as f:
        data = json.load(f)

    fieldnames = [
        "vm_name",
        "vm_uuid",
        "project_name",
        "project_uuid",
        "project_domain_id",
        "vm_state",
        "interface_id",
        "interface_mac",
        "interface_ip",
        "port_security_enabled",
        "security_group_name",
        "security_group_id",
    ]

    with open(csv_path, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for vm in data:
            ports = vm.get("ports") or [{}]

            for port in ports:
                sg_ids = port.get("security_group_ids") or []

                port_sec = port.get("port_security_enabled")
                port_sec_str = (
                    "" if port_sec is None else "True" if port_sec else "False"
                )

                interface_ip = ",".join(
                    ip for ip in port.get("interface_ip", []) if ip
                )

                if not sg_ids:
                    writer.writerow({
                        "vm_name": vm.get("vm_name", ""),
                        "vm_uuid": vm.get("vm_uuid", ""),
                        "project_name": vm.get("project_name", ""),
                        "project_uuid": vm.get("project_uuid", ""),
                        "project_domain_id": vm.get("project_domain_id", ""),
                        "vm_state": vm.get("vm_state", ""),
                        "interface_id": port.get("interface_id", ""),
                        "interface_mac": port.get("interface_mac", ""),
                        "interface_ip": interface_ip,
                        "port_security_enabled": port_sec_str,
                        "security_group_name": "",
                        "security_group_id": "",
                    })
                    continue

                for sg_id in sg_ids:
                    try:
                        sg = conn.network.get_security_group(sg_id)
                        sg_name = sg.name if sg else ""
                    except Exception:
                        sg_name = ""

                    writer.writerow({
                        "vm_name": vm.get("vm_name", ""),
                        "vm_uuid": vm.get("vm_uuid", ""),
                        "project_name": vm.get("project_name", ""),
                        "project_uuid": vm.get("project_uuid", ""),
                        "project_domain_id": vm.get("project_domain_id", ""),
                        "vm_state": vm.get("vm_state", ""),
                        "interface_id": port.get("interface_id", ""),
                        "interface_mac": port.get("interface_mac", ""),
                        "interface_ip": interface_ip,
                        "port_security_enabled": port_sec_str,
                        "security_group_name": sg_name,
                        "security_group_id": sg_id,
                    })

    print(f"[INFO] CSV written to {csv_path}")


def main():
    args = parse_args()
    conn = openstack.connect(cloud=args.cloud)

    json_path = Path(JSON_FILE)
    csv_path = Path(args.output)

    dump_all_tenants_to_json(conn, json_path)
    json_to_csv(json_path, csv_path, conn)


if __name__ == "__main__":
    main()