#!/usr/bin/env python3
import os
import sys
import json
import requests
import argparse

# List of required environment variables
required_vars = ['DOMAIN', 'BORK', 'EMAIL', 'BORK_TOKEN', 'SHORTNAME', 'TOKEN',
                 'AIM', 'PASSWORD', 'REGION', 'SPOT_ORGANIZATION_NAME', 'CHART_NAME']

# Get env vars from deploy.env
env = {}
for var in required_vars:
    value = os.environ.get(var)
    if value is None or value == '':
        print(f"Missing required environment variable: {var}")
        sys.exit(1)
    env[var] = value

# Argument parsing
parser = argparse.ArgumentParser(
    description="Process inputs to delete/deploy PCD SaaS KDU.")
parser.add_argument('--customer', '-c', required=False,
                    help='Name of the CUSTOMER')
parser.add_argument('--get-kubeconfig', required=False,
                    help='set access and fetch kubeconfig of speecified cloud space', default='')
parser.add_argument('--infra', action='store_true',
                    help='Use infra payload create/delete commands')
parser.add_argument('--region', action='store_true',
                    help='Use region payload and create/delete commands')
parser.add_argument('--delete', action='store_true',
                    help='Set to "yes" to run delete request', default='no')
parser.add_argument('--create', action='store_true',
                    help='Set to "yes" to run delete request', default='no')

args = parser.parse_args()

CUSTOMER = args.customer
# DO_DELETE = (args.delete.lower() == "y")
# DO_CREATE = (args.create.lower() == "y")
DO_DELETE = (args.delete)
DO_CREATE = (args.create)
USE_INFRA = args.infra
USE_REGION = args.region
GET_KUBECONFIG = args.get_kubeconfig

# Prepare payloads
payload_region_file = f'payload-{env["REGION"]}-{CUSTOMER}.json'
payload_infra_file = f'payload-infra-{CUSTOMER}.json'

payload_region = {
    "admin_password": env["PASSWORD"],
    "aim": env["AIM"],
    "regionname": env["REGION"],
    "options": {
        "multi_region": "true",
        "chart_url": f"https://ops-opex-pcd-dev-pcd-charts.s3.us-west-2.amazonaws.com/kdu/{env['CHART_NAME']}.tgz",
        "parallel": "true",
        "skip_components": "terrakube"
    }
}
payload_infra = {
    "admin_password": env["PASSWORD"],
    "aim": env["AIM"],
    "regionname": "infra",
    "options": {
        "multi_region": "true",
        "chart_url": f"https://ops-opex-pcd-dev-pcd-charts.s3.us-west-2.amazonaws.com/kdu/{env['CHART_NAME']}.tgz",
    }
}
payload_spot = {
    "organization_name": env["SPOT_ORGANIZATION_NAME"],
    "cloudspace_name": env["AIM"],
    "refresh_token": env["BORK_TOKEN"]
}
print(payload_spot)

# write payloads to files
for filename, data in [(payload_region_file, payload_region), (payload_infra_file, payload_infra), ('spot-payload.json', payload_spot)]:
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

bork_url = env["BORK"]
domain = env["DOMAIN"]

headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {env["TOKEN"]}',
}

# Ready payload files
with open(payload_infra_file, 'rb') as f:
    deploy_data_infra = f.read()
with open(payload_region_file, 'rb') as f:
    deploy_data_region = f.read()
with open('spot-payload.json', 'rb') as f:
    spot_payload = f.read()


# Main logic to deploy or delete based on args
if GET_KUBECONFIG:
    spot_url = "https://spot.rackspace.com/apis/auth.ngpc.rxt.io/v1/generate-kubeconfig"
    response_deploy = requests.post(
        spot_url, json=payload_spot, headers=headers)
    print(response_deploy)
    print(f"Return status: {response_deploy.status_code}")
    if response_deploy.status_code == 200:
        # Extract kubeconfig text from the data section
        response_json = response_deploy.json()
        kubeconfig_content = response_json["data"]["kubeconfig"]
        # Save as text
        with open(f'kubeconfig-{GET_KUBECONFIG}', 'w') as f:
            f.write(kubeconfig_content)
        print(f"Kubeconfig saved to kubeconfig-{env['AIM']}")

if DO_DELETE:
    # print(USE_INFRA)
    if USE_INFRA:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {env["TOKEN"]}',
        }
        infra_url = f"https://{bork_url}/api/v1/regions/{CUSTOMER}.{domain}"
        customer_url = f"https://{bork_url}/api/v1/customers/{CUSTOMER}.{domain}"
        email_url = f"https://{bork_url}/api/v1/customers/{CUSTOMER}"
        payload = {"customer": CUSTOMER}
        customer_email = {"admin_email": env['EMAIL']}

        print('Deleting infra region:', infra_url)
        # response_infra = requests.request('BURN', infra_url, data=deploy_data_infra, headers=headers)
        response_infra = requests.request('BURN', infra_url, headers=headers)
        print('Delete infra region response:',
              response_infra.status_code, response_infra.text)

        print('Deleting infra customer entry:', customer_url)
        response_customer_infra = requests.request(
            'DELETE', customer_url, headers=headers, json=payload)
        print('Delete infra customer response:',
              response_customer_infra.status_code, response_customer_infra.text)

        print('Removing customer email:', customer_email)
        response_email = requests.request(
            'DELETE', email_url, json=customer_email, headers=headers)
        print('Remove customer response response:',
              response_email.status_code, response_email.text)

    elif USE_REGION:
        region_url = f"https://{bork_url}/api/v1/regions/{CUSTOMER}-{env['REGION']}.{domain}"
        customer_url_region = f"https://{bork_url}/api/v1/customers/{CUSTOMER}-{env['REGION']}.{domain}"

        print('Deleting region:', region_url)
        response_region = requests.request(
            'BURN', region_url, data=deploy_data_region, headers=headers)
        print('Delete region response:',
              response_region.status_code, response_region.text)
        print('Deleting region customer:', customer_url_region)
        response_customer_region = requests.request(
            'DELETE', customer_url_region, headers=headers)
        # print('Delete region customer response:', response_customer_region.status_code, response_customer_region.text)

elif DO_CREATE:
    # print(USE_INFRA)
    if USE_INFRA:

        url_email = f"https://{bork_url}/api/v1/customers/{CUSTOMER}"
        response_email = requests.post(
            url_email,
            json={"admin_email": env['EMAIL']},
            headers=headers,
        )
        print('Customer Email:', response_email.status_code, response_email.text)

        url_deploy = f"https://{bork_url}/api/v1/regions/{CUSTOMER}.{domain}"
        print('Creating infra customer entity:', url_deploy)
        payload = {"customer": CUSTOMER}
        response_deploy = requests.post(
            url_deploy, json=payload, headers=headers)
        # print('Create infra customer response:', response_deploy.status_code, response_deploy.text)

        print('Creating infra region...')
        response_deploy = requests.request(
            'DEPLOY',
            url_deploy,
            data=deploy_data_infra,
            headers=headers,
        )
        print('Deploy infra region response:',
              response_deploy.status_code, response_deploy.text)

    elif USE_REGION:
        url_deploy = f"https://{bork_url}/api/v1/regions/{CUSTOMER}-{env['REGION']}.{domain}"
        print('Creating region customer entity:', url_deploy)
        payload = {"customer": CUSTOMER}
        response_deploy = requests.post(url_deploy, json=payload)
        # print('Create region customer response:', response_deploy.status_code, response_deploy.text)

        print('Deploying region...')
        response_deploy = requests.request(
            'DEPLOY', url_deploy, data=deploy_data_region, headers=headers)
        print('Deploy region response:',
              response_deploy.status_code, response_deploy.text)
