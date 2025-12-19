#!/usr/bin/env python3

import argparse
import csv
import subprocess
import logging
from datetime import datetime
import os
import json


def log_and_print(message, level="info"):
    getattr(logging, level, logging.info)(message)
    print(message)


def run_command(command, timeout=20):
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=True, timeout=timeout)
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        log_and_print(f"Command timed out: {' '.join(command)}", "error")
        return None
    except subprocess.CalledProcessError as e:
        log_and_print(
            f"Error executing command '{' '.join(command)}': {e.stderr}", "error")
        return None


def save_server_list_temp(filename="openstack_server_list.csv"):
    output = run_command(
        ["openstack", "server", "list", "--all-projects", "-f", "csv"], timeout=300
    )
    if output:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(output)
        return filename
    else:
        return None


def get_uuid_from_servers_csv(instance_name, server_csv_file):
    with open(server_csv_file, newline='', encoding='utf-8') as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            if row.get('Name', '').strip() == instance_name:
                return row.get('ID')
        return None


def get_network_uuid(network_name):
    cmd = ["openstack", "network", "show", network_name, "-f", "json"]
    output = run_command(cmd)
    if output:
        try:
            result = json.loads(output)
            return result.get("id")
        except Exception:
            return None
    return None


def get_instance_ip(instance_uuid):
    cmd = ["openstack", "server", "show", instance_uuid, "-f", "json"]
    output = run_command(cmd)
    if output:
        try:
            result = json.loads(output)
            addresses = result.get("addresses")
            if addresses:
                # Addresses in format "netname=IP" or multiple entries separated by commas
                split = addresses.split(',')
                ips = []
                for s in split:
                    parts = s.strip().split('=')
                    if len(parts) > 1:
                        ips.append(parts[1].strip())
                if ips:
                    return ips[0]  # return first found IP
        except Exception:
            return None
    return None


def ping_vm(ip_address):
    if not ip_address:
        return False
    cmd = ["ping", "-c", "2", "-W", "2", ip_address]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False
    except Exception as e:
        log_and_print(f"Ping test failed for {ip_address}: {e}", "error")
        return False


def get_port_details(instance_uuid):
    cmd = ["openstack", "port", "list",
           "--server", instance_uuid, "-f", "json"]
    output = run_command(cmd)
    ports = []
    if output:
        try:
            plist = json.loads(output)
            for port in plist:
                port_id = port.get("ID")
                network_name = port.get("Network")
                network_uuid = get_network_uuid(
                    network_name) if network_name else None
                ports.append({
                    "port_id": port_id,
                    "network_name": network_name,
                    "network_uuid": network_uuid
                })
        except Exception:
            pass
    return ports


def main():
    logging.basicConfig(
        filename=f"openstack_fetch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    parser = argparse.ArgumentParser(
        description="Fetch OpenStack VM details using server list temp file.")
    parser.add_argument(
        "csv_file", help="Path to CSV file with instance names")
    parser.add_argument("--ping", action="store_true",
                        help="Run ping tests on the VM IPs")
    args = parser.parse_args()

    log_and_print(f"Processing instances from CSV: {args.csv_file}")
    instance_uuids = []

    # Save OpenStack server list
    temp_srv_list = save_server_list_temp()
    if not temp_srv_list:
        log_and_print("Could not fetch/save OpenStack server list!", "error")
        return

    try:
        with open(args.csv_file, newline='') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                instance_name = row[0].strip()
                log_and_print(
                    f"\nFetching details for instance: {instance_name}")

                instance_uuid = get_uuid_from_servers_csv(
                    instance_name, temp_srv_list)
                if instance_uuid:
                    log_and_print(f"Instance UUID: {instance_uuid}")
                    instance_uuids.append(instance_uuid)

                    if args.ping:
                        ip_address = get_instance_ip(instance_uuid)
                        if ip_address:
                            if ping_vm(ip_address):
                                log_and_print(
                                    f"VM {instance_name} ({ip_address}) is currently reachable.")
                                continue
                            else:
                                log_and_print(
                                    f"Ping failed for {instance_name} ({ip_address}). Collecting further details.")
                        else:
                            log_and_print(
                                f"No IP address found for {instance_name}.", "warning")

                    ports = get_port_details(instance_uuid)
                    for p in ports:
                        log_and_print(f"  Port UUID: {p['port_id']}")
                        log_and_print(f"  Network Name: {p['network_name']}")
                        log_and_print(f"  Network UUID: {p['network_uuid']}")
                else:
                    log_and_print(
                        f"Could not find instance {instance_name}.", "warning")

    except FileNotFoundError:
        log_and_print(f"CSV file not found: {args.csv_file}", "error")
    finally:
        try:
            os.unlink(temp_srv_list)
        except Exception:
            pass

    log_and_print("\nCollected instance UUIDs:")
    for uuid in instance_uuids:
        log_and_print(uuid)


if __name__ == "__main__":
    main()
