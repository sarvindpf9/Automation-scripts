#!/usr/bin/env python3
"""
scan_free_ips.py — Scan a subnet and report free (unused) IP addresses.

Usage:
  python3 scan_free_ips.py 192.168.1.0/24
  python3 scan_free_ips.py 10.0.0.0/22 --timeout 1.5 --workers 64
  python3 scan_free_ips.py 172.16.0.0/20 --method ping
  python3 scan_free_ips.py 192.168.1.0/24 --output free_ips.txt
"""

import argparse
import ipaddress
import subprocess
import socket
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# ── probe methods ────────────────────────────────────────────────────────────


def ping_host(ip: str, timeout: float) -> bool:
    """Return True if host responds to ICMP ping."""
    flag = "-c" if sys.platform != "win32" else "-n"
    timeout_flag = "-W" if sys.platform != "win32" else "-w"
    timeout_val = str(int(timeout * 1000) if sys.platform ==
                      "win32" else timeout)
    result = subprocess.run(
        ["ping", flag, "1", timeout_flag, timeout_val, ip],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def tcp_probe(ip: str, timeout: float,
              ports: tuple = (22, 80, 443, 3389, 445)) -> bool:
    """Return True if any common TCP port answers (no ICMP needed)."""
    for port in ports:
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            pass
    return False


def host_is_up(ip: str, method: str, timeout: float) -> bool:
    if method == "ping":
        return ping_host(ip, timeout)
    elif method == "tcp":
        return tcp_probe(ip, timeout)
    else:  # "both" — host is up if either method says so
        return ping_host(ip, timeout) or tcp_probe(ip, timeout)

# ── reverse-DNS helper ───────────────────────────────────────────────────────


def rdns(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except socket.herror:
        return ""

# ── main scanner ─────────────────────────────────────────────────────────────


def scan_subnet(
    cidr: str,
    method: str = "ping",
    timeout: float = 1.0,
    workers: int = 50,
    skip_network: bool = True,
    resolve: bool = False,
):
    """
    Scan every usable host in *cidr*.

    Returns:
        (free: list[str], used: list[str])
    """
    network = ipaddress.ip_network(cidr, strict=False)
    hosts = list(network.hosts())  # excludes network + broadcast

    free, used = [], []
    total = len(hosts)

    print(
        f"\n[{datetime.now():%H:%M:%S}] Scanning {cidr}  "
        f"({total} hosts, method={method}, timeout={timeout}s, workers={workers})\n"
    )

    def probe(ip_obj):
        ip = str(ip_obj)
        up = host_is_up(ip, method, timeout)
        hostname = rdns(ip) if (resolve and up) else ""
        return ip, up, hostname

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(probe, h): h for h in hosts}
        for fut in as_completed(futures):
            ip, up, hostname = fut.result()
            done += 1
            if up:
                used.append((ip, hostname))
                status = f"  [UP]   {ip:<20}"
                if hostname:
                    status += f"  ({hostname})"
                print(status)
            else:
                free.append(ip)
            # progress indicator every 10 %
            if done % max(1, total // 10) == 0:
                pct = done / total * 100
                print(f"  ... {done}/{total} ({pct:.0f}%)", flush=True)

    return sorted(free, key=lambda x: ipaddress.ip_address(x)), used

# ── report ───────────────────────────────────────────────────────────────────


def print_report(cidr, free, used, output_file=None):
    total = len(free) + len(used)
    lines = [
        "",
        "=" * 52,
        f" Scan report — {cidr}",
        f" {datetime.now():%Y-%m-%d %H:%M:%S}",
        "=" * 52,
        f" Total hosts scanned : {total}",
        f" In use (responded)  : {len(used)}",
        f" FREE (no response)  : {len(free)}",
        "=" * 52,
        "",
        "Free IPs:",
    ]
    for ip in free:
        lines.append(f"  {ip}")
    if used:
        lines += ["", "In-use IPs:"]
        for ip, hostname in sorted(used, key=lambda x: ipaddress.ip_address(x[0])):
            suffix = f"  ({hostname})" if hostname else ""
            lines.append(f"  {ip:<20}{suffix}")
    lines.append("")
    report = "\n".join(lines)
    print(report)
    if output_file:
        with open(output_file, "w") as f:
            f.write(report)
        print(f"[saved → {output_file}]")

# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    p = argparse.ArgumentParser(
        description="Scan a subnet and report free (unused) IPs."
    )
    p.add_argument(
        "subnet",           help="CIDR notation, e.g. 192.168.1.0/24")
    p.add_argument("--method",          choices=["ping", "tcp", "both"],
                   default="ping",
                   help="Probe method (default: ping)")
    p.add_argument("--timeout",         type=float, default=1.0,
                   help="Seconds per probe (default: 1.0)")
    p.add_argument("--workers",         type=int,   default=50,
                   help="Parallel threads (default: 50)")
    p.add_argument("--resolve",         action="store_true",
                   help="Reverse-DNS in-use IPs")
    p.add_argument("--output",          metavar="FILE",
                   help="Save report to file")
    args = p.parse_args()

    try:
        ipaddress.ip_network(args.subnet, strict=False)
    except ValueError as e:
        print(f"Invalid subnet: {e}", file=sys.stderr)
        sys.exit(1)

    free, used = scan_subnet(
        args.subnet,
        method=args.method,
        timeout=args.timeout,
        workers=args.workers,
        resolve=args.resolve,
    )
    print_report(args.subnet, free, used, output_file=args.output)


if __name__ == "__main__":
    main()
