import csv
import base64
import subprocess
import json
import time
import logging
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
import sys

cloud_init_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'cloud_inits'))

def setup_logger():
    log_dir = 'deploy_logs'
    os.makedirs(log_dir, exist_ok=True)
    #timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    log_file = os.path.join(log_dir, f"maas_deployment.log")
    logger = logging.getLogger("maas_logger")
    logger.setLevel(logging.INFO)
    logger.propagate = False  
    file_handler = RotatingFileHandler(
        log_file, maxBytes=1 * 1024 * 1024, backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger

#initialise logger service
logger=setup_logger()

def get_machine_status(maas_user, system_id):
    status_command = ["maas", maas_user, "machine", "read", system_id]
    result = subprocess.run(status_command, capture_output=True, text=True)
    if result.returncode == 0:
        machine_info = json.loads(result.stdout)
        return machine_info.get("status_name", "Unknown")
    return "Unknown"


def wait_for_status(maas_user, system_id, expected_status, hostname, timeout=1800, interval=10):
    elapsed_time = 0
    while elapsed_time < timeout:
        status = get_machine_status(maas_user, system_id)
        message = f"[{hostname}] Current status: {status}"
        logger.info(message)
        if status == expected_status:
            return True
        time.sleep(interval)
        elapsed_time += interval
    logger.warning(f"[{hostname}] Timeout waiting to reach {expected_status}.")
    return False

def create_machine(maas_user, row):
    try:
        hostname = row.get("hostname")
        architecture = row.get("architecture")
        mac_addresses = row.get("mac_addresses")
        power_type = row.get("power_type")

        if not all([hostname, architecture, mac_addresses, power_type]):
            logger.error(f"[{hostname}] Missing required fields in row: {row}")
            return hostname or "unknown", None, "Missing required fields"

        if isinstance(mac_addresses, list):
            mac_addresses = ",".join(mac_addresses)

        power_parameters = {
            "power_user": row.get("power_user"),
            "power_pass": row.get("power_pass"),
            "power_driver": row.get("power_driver"),
            "power_address": row.get("power_address"),
            "cipher_suite_id": row.get("cipher_suite_id"),
            "power_boot_type": row.get("power_boot_type"),
            "privilege_level": row.get("privilege_level"),
            "k_g": row.get("k_g")
        }

        print(f"[{hostname}] Power parameters: {power_parameters}")

        create_command = [
            "maas", maas_user, "machines", "create",
            f"hostname={hostname}",
            f"architecture={architecture}",
            f"mac_addresses={mac_addresses}",
            f"power_type={power_type}",
            f"power_parameters={json.dumps(power_parameters)}"
        ]

        process = subprocess.Popen(create_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()
        exit_code = process.returncode

        if exit_code == 0:
            logger.info(f"[{hostname}] MAAS CLI output: {stdout.strip()}")
            try:
                response_json = json.loads(stdout.strip())
                return hostname, response_json.get("system_id"), None
            except json.JSONDecodeError:
                logger.warning(f"[{hostname}] Could not parse JSON output, returning raw output")
                return hostname, None, "Invalid JSON response"
        logger.error(f"[{hostname}] MAAS CLI failed (exit code {exit_code})")
        logger.error(f"[{hostname}] STDERR: {stderr.strip()}")
        logger.error(f"[{hostname}] STDOUT: {stdout.strip()}")
        if exit_code == 2:
            try:
                error_json = json.loads(stdout.strip())
                mac_errors = error_json.get("mac_addresses", [])
                if mac_errors:
                    logger.warning(f"[{hostname}] MAAS reported MAC address issue: {mac_errors}")
                    return hostname, None, f"MAC address conflict: {mac_errors[0]}"
            except json.JSONDecodeError:
                logger.error(f"[{hostname}] Invalid JSON in stdout on error code 2")
            return hostname, None, f"Exit 2 error: {stderr.strip() or stdout.strip()}"
        return hostname, None, f"Error code {exit_code}: {stderr.strip() or stdout.strip()}"
    except Exception as e:
        logger.exception(f"[{hostname or 'unknown'}] Unexpected error during machine creation: {str(e)}")
        return hostname or "unknown", None, f"Unhandled exception: {str(e)}"


def apply_cloud_init(maas_user, system_id, cloud_init_file, hostname):
    try:
        if not os.path.isfile(cloud_init_file):
            logger.error(f"[{hostname}] Cloud-init file not found: {cloud_init_file}")
            print(f"[{hostname}] Cloud-init file not found: {cloud_init_file}")
            return
        with open(cloud_init_file, "rb") as f:
            user_data = f.read()
        user_data_b64 = base64.b64encode(user_data).decode("utf-8")
        deploy_command = [
            "maas", maas_user, "machine", "deploy", system_id,
            f"user_data={user_data_b64}"
        ]

        # Execute the command
        result = subprocess.run(
            deploy_command,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            logger.info(f"[{hostname}] Successfully initiated deployment with cloud-init.")
            print(f"[{hostname}] Deployment initiated with cloud-init.")
        else:
            logger.error(f"[{hostname}] MAAS CLI error: {result.stderr.strip()}")
            print(f"[{hostname}] MAAS CLI error: {result.stderr.strip()}")

    except Exception as e:
        logger.error(f"[{hostname}] Unexpected error: {str(e)}")
        print(f"[{hostname}] Unexpected error: {str(e)}")


def deploy_machine(maas_user, hostname, system_id):
    try:
        deploy_command = ["maas", maas_user, "machine", "deploy", system_id]
        subprocess.run(deploy_command, check=True, capture_output=True, text=True)
        logger.info(f"[{hostname}] Deploy initiated")
    except Exception as e:
        logger.error(f"[{hostname}] Failed to deploy: {str(e)}")


def configure_and_deploy(maas_user, hostname, system_id, cloud_init_file):
    if not system_id:
        logger.warning(f"[{hostname}] Skipping due to missing system_id.")
        return

    if wait_for_status(maas_user, system_id, "Ready", hostname):
        if cloud_init_file:
            apply_cloud_init(maas_user, system_id, cloud_init_file, hostname)
        deploy_machine(maas_user, hostname, system_id)

        if wait_for_status(maas_user, system_id, "Deployed", hostname):
            logger.info(f"[{hostname}] Successfully deployed.")
        else:
            logger.warning(f"[{hostname}] Did not reach 'Deployed' state.")
    else:
        logger.warning(f"[{hostname}] Skipping deployment (not Ready).")


def find_cloud_init_file(hostname, cloud_init_dir=cloud_init_dir):
    if isinstance(hostname, str):
        hostname_list = [hostname]
    if isinstance(hostname, (list, set)):
        hostname_list = list(hostname)
    for host in hostname_list:
        for filename in os.listdir(cloud_init_dir):
            if filename.startswith(host):
                matched_file = os.path.join(cloud_init_dir, filename)
                return matched_file
    return None

def add_machines_from_csv(maas_user, csv_file, cloud_init_dir=cloud_init_dir):
    if not os.path.isfile(csv_file):
        logger.error(f"CSV file not found: {csv_file}")
        return
    if not os.path.isdir(cloud_init_dir):
        logger.error(f"Cloud-init directory not found: {cloud_init_dir}")
        return
    with open(csv_file, mode='r') as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            logger.error("CSV file is missing header row.")
            return
        reader.fieldnames = [field.strip() for field in reader.fieldnames]
        rows = []
        for row in reader:
            if not row:
                continue
            cleaned_row = {k.strip(): v.strip() for k, v in row.items()}
            rows.append(cleaned_row)
    if not rows:
        logger.warning("No machine entries found in CSV.")
        return
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_row = {executor.submit(create_machine, maas_user, row): row for row in rows}
        for future in future_to_row:
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                row = future_to_row[future]
                logger.error(f"[{row.get('hostname', 'unknown')}] Error creating machine: {str(e)}")
    valid_results = [r for r in results if r[1] is not None]
    if not valid_results:
        logger.error("All machine creation attempts failed. Exiting.")
        return
    results_with_cloud_init = []
    for result in valid_results:
        hostname, system_id, _ = result
        cloud_init_file = find_cloud_init_file(hostname, cloud_init_dir)
        if not cloud_init_file:
            logger.warning(f"[{hostname}] No cloud-init file found, skipping deployment...")
            continue
        else:
            logger.info(f"[{hostname}] Cloud-init file found: {cloud_init_file}")
        results_with_cloud_init.append((hostname, system_id, cloud_init_file))
    if not results_with_cloud_init:
        logger.error("No machines available with valid cloud-init files. Exiting.")
        return
    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(lambda args: configure_and_deploy(maas_user, *args), results_with_cloud_init)