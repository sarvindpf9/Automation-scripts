#!/usr/bin/env python3
"""
pf9-storage-audit.py — Cluster-wide Cinder BDM/igroup remediation.

Cross-references Nova, Cinder, and NetApp ONTAP to find and fix stale
attachment state left behind by failed live migrations.

Usage:
  # Detect only
  python3 pf9-storage-audit.py --netapp-host <ip> --netapp-user admin

  # With SSH for IQN resolution and host health
  python3 pf9-storage-audit.py --netapp-host <ip> --netapp-user admin \
    --ssh-user root --ssh-key /tmp/key

  # Supply known IQNs manually (alternative to SSH)
  python3 pf9-storage-audit.py ... --host-iqn 970-1=iqn.2004-10.com.ubuntu:01:04cd37af9c9

  # Preview remediation
  python3 pf9-storage-audit.py ... --dry-run

  # Apply igroup fixes
  python3 pf9-storage-audit.py ... --remediate
"""

import argparse
import base64
import getpass
import json
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


# ── OpenStack helpers ──────────────────────────────────────────────────────

def os_cmd(*args, allow_fail=False):
    cmd = ["openstack", *args, "-f", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if allow_fail:
            return None
        print(
            f"[ERROR] openstack {' '.join(args)}\n{result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def get_all_servers():
    servers = os_cmd("server", "list", "--all", "--long")
    return [
        {
            "id":     s.get("ID", ""),
            "name":   s.get("Name", ""),
            "host":   s.get("Host", ""),
            "status": s.get("Status", ""),
        }
        for s in servers
    ]


def get_server(server_id):
    s = os_cmd("server", "show", server_id)
    host = (s.get("OS-EXT-SRV-ATTR:hypervisor_hostname")
            or s.get("OS-EXT-SRV-ATTR:host", ""))
    return {
        "id":     s.get("id", ""),
        "name":   s.get("name", ""),
        "host":   host,
        "status": s.get("status", ""),
    }


def get_server_volumes(server_id):
    vols = os_cmd("server", "volume", "list", server_id, allow_fail=True) or []
    seen = set()
    result = []
    for v in vols:
        vid = v.get("Volume ID", v.get("id", "")) if v else ""
        if vid and vid not in seen:
            seen.add(vid)
            result.append(vid)
    return result


def get_volume_info(volume_id):
    return os_cmd("volume", "show", volume_id, allow_fail=True)


def get_hypervisor_name_map():
    """Resolve Cinder host UUIDs → hostnames (PF9 stores service UUIDs in host_name)."""
    result = {}
    services = os_cmd("compute", "service", "list", allow_fail=True) or []
    for s in services:
        if s.get("Binary") == "nova-compute":
            uuid = s.get("ID", "")
            name = s.get("Host", "")
            if uuid and name:
                result[str(uuid)] = name
    hypervisors = os_cmd("hypervisor", "list", "--long", allow_fail=True) or []
    for h in hypervisors:
        uuid = h.get("ID", h.get("id", ""))
        name = h.get("Hypervisor Hostname", h.get("hypervisor_hostname", ""))
        if uuid and name:
            result[str(uuid)] = name
    return result


def get_hypervisor_ip_map():
    result = {}
    hypervisors = os_cmd("hypervisor", "list", "--long", allow_fail=True) or []
    for h in hypervisors:
        name = h.get("Hypervisor Hostname", h.get("hypervisor_hostname", ""))
        ip = h.get("Host IP", h.get("host_ip", ""))
        if name and ip:
            result[name] = ip
    return result


# ── NetApp helpers ─────────────────────────────────────────────────────────

def _netapp_request(host, user, password, path, params=None):
    url = f"https://{host}/api/{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    creds = base64.b64encode(f"{user}:{password}".encode()).decode()
    req = urllib.request.Request(url, headers={
        "Authorization": f"Basic {creds}",
        "Accept":        "application/json",
    })
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(
            f"[ERROR] NetApp {e.code} on {url}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)


def _netapp_get_all(host, user, password, path, params=None):
    params = dict(params or {})
    params.setdefault("max_records", "1000")
    records = []
    while True:
        data = _netapp_request(host, user, password, path, params)
        records.extend(data.get("records", []))
        next_href = data.get("_links", {}).get("next", {}).get("href")
        if not next_href:
            break
        path = next_href.lstrip("/").removeprefix("api/")
        params = {}
    return records


def get_igroups(host, user, password, svm=None):
    params = {"fields": "name,uuid,initiators,svm.name"}
    if svm:
        params["svm.name"] = svm
    raw = _netapp_get_all(host, user, password,
                          "protocols/san/igroups", params)
    return {
        ig["name"]: {
            "uuid":       ig.get("uuid", ""),
            "initiators": [i.get("name", "") for i in ig.get("initiators", [])],
            "svm":        ig.get("svm", {}).get("name", ""),
        }
        for ig in raw
    }


def get_lun_map(host, user, password, svm=None):
    params = {"fields": "lun.name,igroup.name,logical_unit_number,svm.name"}
    if svm:
        params["svm.name"] = svm
    raw = _netapp_get_all(host, user, password,
                          "protocols/san/lun-maps", params)
    return {
        m.get("lun", {}).get("name", ""): {
            "igroup": m.get("igroup", {}).get("name", ""),
            "lun_id": m.get("logical_unit_number"),
            "svm":    m.get("svm", {}).get("name", ""),
        }
        for m in raw
    }


def _do_delete(host, user, password, url):
    creds = base64.b64encode(f"{user}:{password}".encode()).decode()
    req = urllib.request.Request(url, method="DELETE", headers={
        "Authorization": f"Basic {creds}",
        "Accept":        "application/json",
    })
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx):
        pass


def remove_igroup_initiator(host, user, password, ig_uuid, iqn, dry_run=False):
    label = "[DRY-RUN] " if dry_run else ""
    print(f"    {label}NetApp: remove initiator {iqn} from igroup {ig_uuid}")
    if dry_run:
        return True

    base_url = f"https://{host}/api/protocols/san/igroups/{ig_uuid}/initiators/{urllib.parse.quote(iqn, safe='')}"

    # Try with allow_delete_while_lun_mapped first (ONTAP 9.9+)
    try:
        _do_delete(host, user, password, base_url +
                   "?allow_delete_while_lun_mapped=true")
        print("    Done.")
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 400 and "allow_delete_while_lun_mapped" in body:
            pass  # Older ONTAP — retry without the parameter
        else:
            print(f"    [ERROR] {e.code}: {body}", file=sys.stderr)
            return False

    try:
        _do_delete(host, user, password, base_url)
        print("    Done.")
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 409:
            print(
                f"    [MANUAL ACTION REQUIRED] NetApp rejected automatic removal.")
            print(f"    This ONTAP version requires LUN maps to be removed first.")
            print(f"    Remove manually via NetApp System Manager:")
            print(
                f"      Storage → Igroups → search '{ig_uuid}' → Initiators → remove {iqn}")
            print(f"    Then re-run --remediate to continue.")
        else:
            print(f"    [ERROR] {e.code}: {body}", file=sys.stderr)
        return False


# ── SSH helpers ───────────────────────────────────────────────────────────

def _ssh_cmd(ssh_user, ssh_key, target, command):
    cmd = ["ssh", "-o", "ConnectTimeout=5", "-o",
           "StrictHostKeyChecking=no", "-o", "BatchMode=yes"]
    if ssh_key:
        cmd += ["-i", ssh_key]
    cmd += [f"{ssh_user}@{target}", command]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15)
        return result.stdout, result.returncode
    except Exception:
        return None, -1


def get_host_iqn_via_ssh(hostname, ssh_user, ssh_key=None, host_ip=None):
    for target in filter(None, [host_ip, hostname.split(".")[0]]):
        out, rc = _ssh_cmd(ssh_user, ssh_key, target,
                           "cat /etc/iscsi/initiatorname.iscsi")
        if rc == 0 and out:
            for line in out.splitlines():
                if line.startswith("InitiatorName="):
                    return line.split("=", 1)[1].strip()
    return None


# ── Host health checks ────────────────────────────────────────────────────

def check_host_health_via_ssh(hostname, ssh_user, ssh_key=None, host_ip=None):
    cmd = (
        "printf 'MPFAIL:%s\\n' \"$(multipath -ll 2>/dev/null | grep -cE 'failed|faulty' || echo 0)\"; "
        "printf 'DSTATE:%s\\n' \"$(ps -eo stat,comm 2>/dev/null | awk '$1~/^D/{print $2}' | sort -u | tr '\\n' ' ')\"; "
        "printf 'LIBVIRTD:%s\\n' \"$(systemctl is-active libvirtd 2>/dev/null || echo unknown)\"; "
        "printf 'VIRSH:%s\\n' \"$(timeout 5 virsh list --all --quiet 2>/dev/null | wc -l || echo timeout)\""
    )
    target = host_ip or hostname.split(".")[0]
    out, rc = _ssh_cmd(ssh_user, ssh_key, target, cmd)
    try:
        if rc != 0 or not out:
            return None
        health = {}
        for line in out.splitlines():
            key, _, val = line.partition(":")
            health[key.strip()] = val.strip()
        return {
            "libvirtd":     health.get("LIBVIRTD", "unknown"),
            "mp_failed":    int(health.get("MPFAIL", "0") or "0"),
            "dstate_procs": [p for p in health.get("DSTATE", "").split() if p],
            "virsh_domains": health.get("VIRSH", "unknown"),
        }
    except Exception:
        return None


def run_host_health_checks(nova_hosts, ssh_user, ssh_key=None, hyp_ip_map=None):
    hyp_ip_map = hyp_ip_map or {}
    results = {}
    with ThreadPoolExecutor(max_workers=min(len(nova_hosts), 8)) as pool:
        futures = {
            pool.submit(check_host_health_via_ssh, h, ssh_user, ssh_key, hyp_ip_map.get(h)): h
            for h in nova_hosts
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


def print_health_report(health_results):
    if not health_results:
        return
    print(f"\n{'='*80}")
    print("HOST HEALTH")
    print(f"{'='*80}")
    for host, h in sorted(health_results.items()):
        short = host.split(".")[0]
        if h is None:
            print(f"\n  {short}: SSH failed — health check skipped")
            continue
        mp_str = f"{h['mp_failed']} failed path(s)" if h["mp_failed"] else "OK"
        dstate_str = ", ".join(
            h["dstate_procs"]) if h["dstate_procs"] else "none"
        print(f"\n  {short}")
        print(
            f"    libvirtd     : {h['libvirtd']}{'  ← ATTENTION' if h['libvirtd'] != 'active' else ''}")
        print(
            f"    multipath    : {mp_str}{'  ← ATTENTION' if h['mp_failed'] else ''}")
        print(
            f"    D-state procs: {dstate_str}{'  ← ATTENTION' if h['dstate_procs'] else ''}")
        print(f"    virsh        : {h['virsh_domains']} domain(s) visible")


# ── Cross-reference helpers ────────────────────────────────────────────────

def iqn_to_hostname(iqn):
    parts = iqn.rsplit(":", 1)
    return parts[-1].lower() if len(parts) > 1 else iqn.lower()


def is_ubuntu_iqn(iqn):
    return "com.ubuntu" in iqn.lower()


def hostname_matches_iqn(hostname, iqn):
    # Only valid for RHEL/Rocky — Ubuntu IQNs encode a hardware ID, not a hostname.
    if is_ubuntu_iqn(iqn):
        return False
    return hostname.split(".")[0].lower() in iqn_to_hostname(iqn)


def find_lun_for_volume(volume_id, lun_map):
    for lun_path in lun_map:
        if volume_id in lun_path:
            return lun_path
    return None


# ── Detection ──────────────────────────────────────────────────────────────

def _fetch_server_items(server, hyp_map, igroups, lun_map):
    """Fetch volume/attachment data for one server. Runs in a worker thread."""
    nova_host = hyp_map.get(server["host"], server["host"])
    if not nova_host:
        return []
    items = []
    for volume_id in get_server_volumes(server["id"]):
        vol = get_volume_info(volume_id)
        if not vol:
            continue
        attachments = vol.get("attachments", [])
        if isinstance(attachments, str):
            try:
                attachments = json.loads(attachments)
            except json.JSONDecodeError:
                attachments = []
        cinder_host = attachment_id = ""
        for att in attachments:
            if att.get("server_id") == server["id"]:
                raw = att.get("host_name", "")
                cinder_host = hyp_map.get(raw, raw)
                attachment_id = att.get("attachment_id", att.get("id", ""))
                break
        lun_path = find_lun_for_volume(volume_id, lun_map)
        igroup_name = lun_map.get(lun_path, {}).get(
            "igroup") if lun_path else None
        igroup_data = igroups.get(igroup_name, {}) if igroup_name else {}
        items.append({
            "server": server, "nova_host": nova_host,
            "volume_id": volume_id, "cinder_host": cinder_host,
            "attachment_id": attachment_id, "lun_path": lun_path,
            "igroup_name": igroup_name, "igroup_data": igroup_data,
        })
    return items


def detect(servers, netapp_host, netapp_user, netapp_password, svm,
           ssh_user=None, ssh_key=None, hyp_ip_map=None, manual_iqns=None):
    print("\nQuerying NetApp ONTAP...")
    igroups = get_igroups(netapp_host, netapp_user, netapp_password, svm)
    lun_map = get_lun_map(netapp_host, netapp_user, netapp_password, svm)
    hyp_map = get_hypervisor_name_map()
    print(f"Checking {len(servers)} VM(s)...\n")

    # Pass 1: fetch per-VM data in parallel; print progress so screen isn't blank
    collected = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_server_items, s,
                               hyp_map, igroups, lun_map): s for s in servers}
        done = 0
        for future in as_completed(futures):
            done += 1
            server = futures[future]
            print(f"  [{done}/{len(servers)}] {server['name']}", flush=True)
            try:
                collected.extend(future.result())
            except Exception as exc:
                print(f"  [WARN] {server['name']}: {exc}", file=sys.stderr)

    # Pass 2a: infer ground-truth IQNs from clean (non-stale) attachments.
    # When Cinder stores UUIDs (common in PF9) this map stays empty and we
    # fall through to --host-iqn or SSH.
    host_iqn_map = {}  # nova_short → set of IQNs
    for item in collected:
        nova_s = item["nova_host"].split(".")[0].lower()
        cinder_s = item["cinder_host"].split(
            ".")[0].lower() if item["cinder_host"] else ""
        if cinder_s and nova_s == cinder_s:
            for iqn in item["igroup_data"].get("initiators", []):
                host_iqn_map.setdefault(nova_s, set()).add(iqn)

    # Pass 2b: seed from --host-iqn entries (substring match on short hostname)
    if manual_iqns:
        nova_shorts = {item["nova_host"].split(
            ".")[0].lower() for item in collected}
        for key, iqn in manual_iqns.items():
            matched = [s for s in nova_shorts if key.lower() in s]
            if matched:
                for s in matched:
                    host_iqn_map[s] = {iqn}
                    print(f"  --host-iqn: {s} → {iqn}", flush=True)
            else:
                print(f"  [WARN] --host-iqn: no host matched '{key}' (known: {', '.join(nova_shorts)})",
                      file=sys.stderr)

    # Pass 2c: SSH to fetch IQNs for hosts not yet covered
    if ssh_user:
        ssh_hosts = {h for h in {item["nova_host"] for item in collected if item["nova_host"]}
                     if h.split(".")[0].lower() not in host_iqn_map}
        if ssh_hosts:
            hyp_ip_map = hyp_ip_map or {}
            print(f"\nFetching IQNs via SSH ({ssh_user}@host)...")
            with ThreadPoolExecutor(max_workers=min(len(ssh_hosts), 8)) as pool:
                ssh_futures = {
                    pool.submit(get_host_iqn_via_ssh, h, ssh_user, ssh_key, hyp_ip_map.get(h)): h
                    for h in ssh_hosts
                }
                for future in as_completed(ssh_futures):
                    host = ssh_futures[future]
                    short = host.split(".")[0].lower()
                    iqn = future.result()
                    if iqn:
                        host_iqn_map[short] = {iqn}
                        print(f"  {short}: {iqn}", flush=True)
                    else:
                        print(f"  [WARN] {short}: SSH failed — igroup check will be skipped for Ubuntu hosts",
                              flush=True)

    # Pass 3: evaluate findings using ground-truth IQN map where available
    findings = []
    warned_hosts = set()
    for item in collected:
        server = item["server"]
        nova_host = item["nova_host"]
        cinder_host = item["cinder_host"]
        nova_s = nova_host.split(".")[0].lower()
        cinder_s = cinder_host.split(".")[0].lower() if cinder_host else ""
        igroup_name = item["igroup_name"]
        igroup_data = item["igroup_data"]
        igroup_iqns = igroup_data.get("initiators", [])
        igroup_uuid = igroup_data.get("uuid", "")
        igroup_svm = igroup_data.get("svm", "")

        bdm_stale = bool(cinder_s and nova_s != cinder_s)

        if igroup_name and igroup_iqns:
            known_iqns = host_iqn_map.get(nova_s)
            if known_iqns:
                igroup_stale = not any(
                    iqn in known_iqns for iqn in igroup_iqns)
            elif bdm_stale:
                # Ubuntu IQNs encode hardware IDs — hostname matching doesn't apply
                matchable = [
                    iqn for iqn in igroup_iqns if not is_ubuntu_iqn(iqn)]
                igroup_stale = bool(matchable) and not any(
                    hostname_matches_iqn(nova_host, iqn) for iqn in matchable
                )
            else:
                igroup_stale = False
        else:
            igroup_stale = False

        if (igroup_name and igroup_iqns
                and not host_iqn_map.get(nova_s)
                and all(is_ubuntu_iqn(q) for q in igroup_iqns)):
            warned_hosts.add(nova_host)

        if not (bdm_stale and igroup_stale):
            continue

        known_iqns = host_iqn_map.get(nova_s, set())
        stale_iqns = (
            [iqn for iqn in igroup_iqns if iqn not in known_iqns]
            if igroup_stale and known_iqns
            else [iqn for iqn in igroup_iqns if not hostname_matches_iqn(nova_host, iqn)]
            if igroup_stale
            else []
        )

        findings.append({
            "vm_id":        server["id"],
            "vm_name":      server["name"],
            "vm_status":    server["status"],
            "nova_host":    nova_host,
            "cinder_host":  cinder_host,
            "volume_id":    item["volume_id"],
            "attachment_id": item["attachment_id"],
            "lun_path":     item["lun_path"],
            "igroup":       igroup_name,
            "igroup_uuid":  igroup_uuid,
            "igroup_svm":   igroup_svm,
            "igroup_iqns":  igroup_iqns,
            "stale_iqns":   stale_iqns,
            "bdm_stale":    bdm_stale,
            "igroup_stale": igroup_stale,
        })

    for host in sorted(warned_hosts):
        short = host.split(".")[0]
        print(f"  [WARN] {short}: igroup check skipped — "
              f"pass --host-iqn {short}=<IQN> (get via: cat /etc/iscsi/initiatorname.iscsi)",
              flush=True)

    all_nova_hosts = {item["nova_host"]
                      for item in collected if item["nova_host"]}
    return findings, igroups, host_iqn_map, all_nova_hosts


# ── Reporting ──────────────────────────────────────────────────────────────

def print_report(findings):
    if not findings:
        print("✓  No stale BDM/igroup mappings detected.")
        return

    print(f"{'='*80}")
    print(f"STALE MAPPINGS FOUND: {len(findings)}")
    print(f"{'='*80}")

    for f in findings:
        tags = []
        if f["bdm_stale"]:
            tags.append("STALE BDM")
        if f["igroup_stale"]:
            tags.append("STALE IGROUP")

        print(f"\n  [{' + '.join(tags)}]")
        print(
            f"  VM           : {f['vm_name']} ({f['vm_id']})  status={f['vm_status']}")
        print(f"  Volume       : {f['volume_id']}")
        cinder_display = f["cinder_host"] or "(unknown)"
        if len(cinder_display) == 36 and cinder_display.count("-") == 4:
            cinder_display += "  (UUID — host decommissioned or not in compute service list)"
        print(f"  Nova host    : {f['nova_host']}   ← VM is HERE")
        print(
            f"  Cinder host  : {cinder_display}   ← attachment thinks it's here")
        if f["igroup"]:
            hosts = ", ".join(iqn_to_hostname(q)
                              for q in f["igroup_iqns"]) or "(none)"
            print(f"  igroup       : {f['igroup']}  →  IQN hosts: {hosts}")
        for iqn in f["stale_iqns"]:
            print(f"  Stale IQN    : {iqn}")


# ── Remediation ────────────────────────────────────────────────────────────

def remediate(findings, igroups, host_iqn_map, netapp_host, netapp_user, netapp_password, dry_run):
    if not findings:
        return

    prefix = "[DRY-RUN] " if dry_run else ""
    print(f"\n{'='*80}")
    print(f"{prefix}REMEDIATION")
    print(f"{'='*80}")
    print("Steps per finding:")
    print("  1. Fix NetApp igroup  (automated here)")
    print("  2. iSCSI rescan       (commands to run on the correct host)")
    print("  3. Cinder/Nova fix    (commands to run — review before applying)")
    print()

    by_vm = {}
    for f in findings:
        by_vm.setdefault(f["vm_id"], []).append(f)

    processed_ops = set()
    failed_igroups = set()

    for vm_id, vm_findings in by_vm.items():
        first = vm_findings[0]
        nova_s = first["nova_host"].split(".")[0].lower()
        known_iqns = host_iqn_map.get(nova_s, set())
        correct_iqn = next(iter(known_iqns), None)

        print(f"\n── {first['vm_name']} ({vm_id}) ──")
        print(f"   Nova host  : {first['nova_host']}")
        print(f"   Cinder host: {first['cinder_host'] or '(unknown)'}")

        # Step 1: Fix NetApp igroup
        print(f"\n  STEP 1: Fix NetApp igroups")
        step1_ok = True
        for f in vm_findings:
            if f["igroup_stale"] and f["stale_iqns"]:
                print(f"\n    Volume  : {f['volume_id']}")
                print(f"    igroup  : {f['igroup']}")
                if f["igroup_uuid"] in failed_igroups:
                    print(
                        f"    (skipped — manual action already required for this igroup; see above)")
                    step1_ok = False
                    continue
                for iqn in f["stale_iqns"]:
                    op_key = (f["igroup_uuid"], iqn)
                    if op_key in processed_ops:
                        print(
                            f"    (skipped — already removed {iqn} for a previous volume)")
                        continue
                    success = remove_igroup_initiator(
                        netapp_host, netapp_user, netapp_password,
                        f["igroup_uuid"], iqn, dry_run=dry_run,
                    )
                    if success:
                        processed_ops.add(op_key)
                    else:
                        step1_ok = False
                        failed_igroups.add(f["igroup_uuid"])
            else:
                print(f"\n    Volume {f['volume_id']}: igroup OK")

        any_igroup_stale = any(f["igroup_stale"] for f in vm_findings)
        if any_igroup_stale:
            print(f"\n    Add correct IQN for {first['nova_host']}:")
            if correct_iqn:
                print(f"    Found : {correct_iqn}")
                seen_add = set()
                for f in vm_findings:
                    if f["igroup_stale"] and f["igroup_uuid"] not in seen_add:
                        seen_add.add(f["igroup_uuid"])
                        print(
                            f"    curl -sk -u {netapp_user}:<pass> -X POST \\")
                        print(
                            f"      https://{netapp_host}/api/protocols/san/igroups/{f['igroup_uuid']}/initiators \\")
                        print(
                            f"      -H 'Content-Type: application/json' -d '{{\"name\": \"{correct_iqn}\"}}'")
            else:
                print(
                    f"    IQN not found — retrieve manually, then re-run with --host-iqn:")
                print(
                    f"    ssh {first['nova_host']} 'cat /etc/iscsi/initiatorname.iscsi'")
                print(
                    f"    Then: python3 pf9-storage-audit.py ... --host-iqn {nova_s}=<IQN> --remediate")

        if not step1_ok and not dry_run:
            print(f"\n  ✗ STEP 1 FAILED — igroup fix did not complete.")
            print(f"    Steps 2 and 3 are skipped until igroup is fixed.")
            print(
                f"    Via NetApp System Manager → Storage → Igroups → {first['igroup']}")
            print(f"    Then re-run with --remediate.")
            continue

        # Step 2: iSCSI rescan
        print(f"\n  STEP 2: iSCSI rescan — run on {first['nova_host']}:")
        print(f"    iscsiadm -m session -R")
        print(f"    iscsiadm -m node --login")
        print(f"    multipath -r")
        print(f"    multipath -ll | grep -E 'failed|faulty|0 paths'")

        # Step 3: Cinder / Nova fix
        print(f"\n  STEP 3: Cinder/Nova state fix")
        any_bdm_stale = any(f["bdm_stale"] for f in vm_findings)
        if any_bdm_stale:
            print(f"    # Safe option: migrate VM first")
            print(f"    openstack server migrate --live-migration {vm_id}")
            print(f"    #")
            print(f"    # If VM is stuck, force fix per volume:")
            for f in vm_findings:
                if f["bdm_stale"] and f["attachment_id"]:
                    print(
                        f"    openstack volume attachment delete {f['attachment_id']}")
                    print(
                        f"    openstack volume set --state available {f['volume_id']}  # admin")
            print(f"    # If Nova VM state is stuck:")
            print(f"    openstack server set --state active {vm_id}")
        else:
            print(f"    # BDM clean — igroup was the only issue (fixed in Step 1).")

    print(f"\n{'='*80}")
    print("After all steps, verify:")
    print("  virsh list --all           (on affected host — should not hang)")
    print("  multipath -ll              (no failed/faulty maps)")
    print("  openstack volume list      (volumes should be 'in-use')")


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Detect and remediate stale Cinder BDM/igroup state after failed migrations"
    )
    parser.add_argument("--netapp-host",     required=True)
    parser.add_argument("--netapp-user",     default="admin")
    parser.add_argument("--netapp-password", help="Prompted if omitted")
    parser.add_argument(
        "--svm",             help="Filter by SVM name (e.g. vs.5)")
    parser.add_argument(
        "--server",          help="Check a single VM by ID or name")
    parser.add_argument("--ssh-user",        default=None,
                        help="SSH user for host health checks and IQN fetching (e.g. root)")
    parser.add_argument("--ssh-key",         default=None, metavar="PATH",
                        help="SSH private key file (optional if default key works)")
    parser.add_argument("--host-iqn",        action="append", default=[], metavar="HOST=IQN",
                        help="Known IQN for a compute host, e.g. 970-1=iqn.2004-10.com.ubuntu:01:04cd37af9c9. "
                             "Repeat for each host. Run: cat /etc/iscsi/initiatorname.iscsi on each host.")
    parser.add_argument("--dry-run",         action="store_true",
                        help="Preview all remediation steps without making changes")
    parser.add_argument("--remediate",       action="store_true",
                        help="Apply igroup fixes and print Cinder/iSCSI steps")
    args = parser.parse_args()

    manual_iqns = {}
    for entry in args.host_iqn:
        if "=" not in entry:
            print(
                f"[ERROR] --host-iqn must be HOST=IQN format, got: {entry}", file=sys.stderr)
            sys.exit(1)
        host, iqn = entry.split("=", 1)
        manual_iqns[host.strip()] = iqn.strip()

    if not args.netapp_password:
        args.netapp_password = getpass.getpass(
            f"NetApp password for {args.netapp_user}@{args.netapp_host}: "
        )

    print("Querying OpenStack...")
    servers = [get_server(args.server)] if args.server else get_all_servers()
    print(f"Found {len(servers)} VM(s).")

    hyp_ip_map = get_hypervisor_ip_map()

    findings, igroups, host_iqn_map, all_nova_hosts = detect(
        servers, args.netapp_host, args.netapp_user, args.netapp_password, args.svm,
        ssh_user=args.ssh_user, ssh_key=args.ssh_key, hyp_ip_map=hyp_ip_map,
        manual_iqns=manual_iqns or None,
    )

    if args.ssh_user and all_nova_hosts:
        health_results = run_host_health_checks(
            all_nova_hosts, args.ssh_user, args.ssh_key, hyp_ip_map)
        print_health_report(health_results)

    print_report(findings)

    stale_vms = len({f["vm_id"] for f in findings})
    if findings:
        print(
            f"\nSummary: {stale_vms} VM(s) with stale BDM + igroup across {len(findings)} volume(s).")

    if args.remediate or args.dry_run:
        remediate(findings, igroups, host_iqn_map, args.netapp_host, args.netapp_user,
                  args.netapp_password, dry_run=args.dry_run)
    elif findings:
        print("\nRun with --dry-run to preview remediation steps.")
        print("Run with --remediate to apply igroup fixes and print Cinder/iSCSI steps.")

    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()