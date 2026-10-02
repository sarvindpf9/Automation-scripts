import argparse
import subprocess
import sys
import json
import copy
import os
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined


###############################################################################
#                           Argument parsing                                  #
###############################################################################
parser = argparse.ArgumentParser(description="parser script for user input to playbook vars",
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
# parser.add_argument("-clustername", "--clustername", action='store', help="takes clustername as input (REQUIRED)", required=False)
parser.add_argument("-hostname", "--hostname", action='store',
                    help="name of the proxomox host", required=True)
parser.add_argument("-username", "--username", action='store',
                    help="name of the user", required=True)
parser.add_argument("-proxpass", "--proxpass", action='store',
                    help="passwd to connect proxmox host", required=True)
parser.add_argument("-vmprofile", "--vmprofile", action='store',
                    help="VM resource profile (mem/proc)", required=True)
parser.add_argument("-vmcount", "--vmcount", action='store', type=int,
                    help="number of VMs limited to 3", required=True)
parser.add_argument("-varsfile", "--varsfile", action='store', default="playbook-vars.yml",
                    help="combined host + VM vars YAML written by this script", required=False)
parser.add_argument("-template", "--template", action='store',
                    default=str(Path(__file__).parent / "vm-config.yml.j2"),
                    help="Jinja template rendered with the vars file", required=False)
parser.add_argument("-output", "--output", action='store', default="vm-config.yml",
                    help="final rendered YAML", required=False)
parser.add_argument("-set-inventory", "--set-inventory", action='store', default="inventory.yaml",
                    help="Ansible inventory YAML written by this script", required=False)
parser.add_argument("-inventory-template", "--inventory-template", action='store',
                    default=str(Path(__file__).parent / "inventory.yml.j2"),
                    help="Jinja template used to render the inventory", required=False)

# parser.add_argument("-region", "--region", action='store', help="takes site name as input to form DU name. DU=<portal>-<region> (REQUIRED)", required=False)
# parser.add_argument("-env", "--env", action='store', help="takes a string value to segregate hosts in the side. Value: STRING", required=False)
# parser.add_argument("-render-userconfig", "--render-userconfig", action='store', help="takes filepath of user config for host onboarding. Value: FILEPATH", required=False)
# parser.add_argument("-show-dir", "--show-dir", action='store', help="to list required dir view of regions sub-dirs. Values: yes|no", required=False)
args = parser.parse_args()


proxHostProfile = [{
    "ipaddress": "192.168.1.82",
    "portNumber": "8006",
    "proxmoxApiUser": "root@pam",
    "proxmoxApiPassword": f"{args.proxpass}",
    "proxmox_node": "homelab-pve",
    "datastoreId": "local-1TB",
    "cloudinit_drive_datastore_id": "local-1TB",
    "snippet_datastore_id": "local",
    "snippet_directory": "/var/lib/vz/snippets",
    "proxmox_validate_certs": "false",
    "proxmox_api_timeout": "300",
    "template_vm_id": "104",
    "template_vm_name": "ubuntu-24-04-tmpl"
}]

vmProfileName = [{
    "memory_mb": "8096",
    "cores": "4",
    "sockets": "1",
    "disk_size_gb": "130",
    "network_interfaces": [{"bridge": "vmbr0", "dhcp4": "true"}, {"bridge": "vxnet2", "dhcp4": "false"}]
},
    {"memory_mb": "12296",
     "cores": "8",
     "sockets": "1",
     "disk_size_gb": "130",
     "network_interfaces": [{"bridge": "vmbr0", "dhcp4": "true"}, {"bridge": "vxnet2", "dhcp4": "false"}]
     },
    {"memory_mb": "32768",
     "cores": "12",
     "sockets": "1",
     "disk_size_gb": "130",
     "network_interfaces": [{"bridge": "vmbr0", "dhcp4": "true"}, {"bridge": "vxnet2", "dhcp4": "false"}]
     }]


#### Check input

# max VMs allowed per t-shirt size
maxVmCount = {"default": 3, "large": 2, "xlarge": 1}
def checkInputArgs(profile=args.vmprofile, vmcount=args.vmcount):
  if vmcount < 0:
    print(f"vmcount must be >= 0, got {vmcount}")
    sys.exit(255)
  if vmcount > maxVmCount[profile]:
    print(f"only {maxVmCount[profile]} VM(s) can be deployed with a t-shirt of {profile}")
    sys.exit(255)


###############################################################################
#                     Select host + VM profiles                               #
###############################################################################
if args.hostname == "homelab-pve":
  selectedHost = copy.deepcopy(proxHostProfile[0])
else:
  # exit before writing anything so a half-built vars file never reaches the template
  sys.exit(f"ERROR: no host profile defined for '{args.hostname}'")

profileIndex = {"default": 0, "large": 1, "xlarge": 2}
if args.vmprofile not in profileIndex:
  sys.exit(f"ERROR: unknown vmprofile '{args.vmprofile}' (use default|large|xlarge)")
checkInputArgs()
if args.vmprofile in ("default", "large"):
  # vmcount 0 -> one VM numbered 0; vmcount N -> N VMs numbered 1..N
  vmNumbers = range(1, args.vmcount + 1) if args.vmcount >= 1 else [0]
else:
  # xlarge always produces a single unnumbered VM
  vmNumbers = [""]

# keyed by VM id (ubuntu24-lab-testN) to match the "vms:" mapping the playbook expects
selectedVms = {}
for count in vmNumbers:
  # deepcopy so each VM gets its own dict (incl. network_interfaces list) instead of sharing one object
  vm = copy.deepcopy(vmProfileName[profileIndex[args.vmprofile]])
  # username is not part of vm_name: the playbook prepends vm_name_prefix (= --username)
  vm = {"vm_name": f"u24-test{count}", **vm}
  selectedVms[f"ubuntu24-lab-test{count}"] = vm

###############################################################################
#           combine both profiles into one vars YAML                          #
###############################################################################
# keep the password out of the vars file; it is passed straight to the render step
selectedHost.pop("proxmoxApiPassword", None)

playbookVars = {
    "vm_name_prefix": args.username,
    "proxmox_host": selectedHost,
    "vms": selectedVms,
}

with open(args.varsfile, "w", encoding="utf-8") as varsFile:
  # sort_keys=False keeps keys in the order they are defined above
  yaml.safe_dump(playbookVars, varsFile, sort_keys=False,
                 default_flow_style=False)

###############################################################################
#           feed the vars YAML into the Jinja template                        #
###############################################################################
with open(args.varsfile, encoding="utf-8") as varsFile:
  templateVars = yaml.safe_load(varsFile)

# secrets come from the CLI / environment so they never live in the template or vars file
secretVars = {"proxmox_api_password": args.proxpass}
for envName in ("CLOUD_PASSWORD", "CLOUD_INIT_USER_PASSWORD"):
  if envName not in os.environ:
    sys.exit(f"ERROR: environment variable {envName} is not set")
  secretVars[envName.lower()] = os.environ[envName]

def renderTemplate(templateFile, outputFile, renderVars):
  """Render templateFile with renderVars and write the result to outputFile."""
  templatePath = Path(templateFile)
  jinjaEnv = Environment(
      loader=FileSystemLoader(templatePath.parent),
      # fail on a missing variable instead of silently rendering ""
      undefined=StrictUndefined,
      trim_blocks=True,            # drop the newline after {% ... %} tags
      lstrip_blocks=True,          # drop indentation before {% ... %} tags
      keep_trailing_newline=True,
  )
  rendered = jinjaEnv.get_template(templatePath.name).render(**renderVars)
  with open(outputFile, "w", encoding="utf-8") as outFile:
    outFile.write(rendered)


renderTemplate(args.template, args.output, {**templateVars, **secretVars})

###############################################################################
#           create inventory file                                             #
###############################################################################
# proxmox node name -> host vars; every entry renders under the proxmox_nodes group
proxmoxHosts = {
    templateVars["proxmox_host"]["proxmox_node"]: {
        "ansible_host": templateVars["proxmox_host"]["ipaddress"],
        "ansible_user": "root",
        "ansible_ssh_password": args.proxpass,
    },
}

renderTemplate(args.inventory_template, args.set_inventory,
               {"proxmox_hosts": proxmoxHosts})

print(f"vars file : {args.varsfile}")
print(f"rendered  : {args.output}")
print(f"inventory : {args.set_inventory}")
