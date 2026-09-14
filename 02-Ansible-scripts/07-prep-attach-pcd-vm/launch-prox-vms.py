#!/usr/bin/env python3

import sys
from datetime import datetime
import yaml
import os
import argparse
import subprocess
from modules import pcdInstallHelper

###############################################################################
#                                 Global vars                                 #
###############################################################################
current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
logfileName = f"pcd-install-operation-{current_time}.log"
current_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.dirname(os.path.abspath(__file__))

# create logging directory if not present
logdir = f"{current_dir}/logs/pcd_installer_logs"
if not os.path.exists(logdir):
    os.makedirs(logdir)
# logfile = os.path.join(f"{current_dir}/logs/pcd_installer_logs/", logfileName)
logfile = os.path.join(f"{logdir}", logfileName)

###############################################################################
#                           Argument parsing                                  #
###############################################################################
parser = argparse.ArgumentParser(description="Utility to configure PCD and enrol nodes",
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
# parser.add_argument("-clustername", "--clustername", action='store', help="takes clustername as input (REQUIRED)", required=False)
parser.add_argument("-portal", "--portal", action='store',
                    help="takes region name as input (REQUIRED)", required=False)
parser.add_argument("-region", "--region", action='store',
                    help="takes site name as input to form DU name. DU=<portal>-<region> (REQUIRED)", required=False)
parser.add_argument("-env", "--env", action='store',
                    help="takes a string value to segregate hosts in the side. Value: STRING", required=False)
parser.add_argument("-render-userconfig", "--render-userconfig", action='store',
                    help="takes filepath of user config for host onboarding. Value: FILEPATH", required=False)
parser.add_argument("-show-dir", "--show-dir", action='store',
                    help="to list required dir view of regions sub-dirs. Values: yes|no", required=False)
parser.add_argument("-setup-environment", "--setup-environment", action='store',
                    help="Setup environment for ansible play exec and management (REQUIRED). Values: yes|no", required=False)
parser.add_argument("-create-templates-json", "--create-templates-json", action='store',
                    help="save all userconfig in a json file locally inside jsonsave/directory (OPTIONAL)", required=False)
parser.add_argument("-create-blueprints", "--create-blueprints", action='store',
                    help="start blueprint template generation. values: yes|no", required=False)
parser.add_argument("-apply-blueprints", "--apply-blueprints", action='store',
                    help="Deploy the blueprint templates. Values: yes|no", required=False)
parser.add_argument("-create-hostconfigs", "--create-hostconfigs", action='store',
                    help="start hostconfigs template generation Values: yes|no", required=False, default="")
parser.add_argument("-apply-hostconfigs", "--apply-hostconfigs", action='store',
                    help="deploy the hostconfigs template. Values: yes|no", required=False)
parser.add_argument("-create-networks-configs", "--create-networks-configs", action='store',
                    help="Create network templates from the user configs Values: yes|no", required=False)
parser.add_argument("-apply-networks-configs", "--apply-networks-configs", action='store',
                    help="Create network templates from the user configs Values: yes|no", required=False)
parser.add_argument("-apply-playbooks-all", "--apply-playbooks-all", action='store',
                    help="Deploy all playbooks with DU name prefix from the playbooks directory. Values: yes|no", required=False)
parser.add_argument("-create-hostagents-configs", "--create-hostagents-configs", action='store',
                    help="Create/render node onboarding playbooks with user input. Values: yes|no", required=False)
parser.add_argument("-apply-hosts-onboard", "--apply-hosts-onboard", action='store',
                    help="Create/render node onboarding playbooks with user input. Values: yes|no", required=False)
parser.add_argument("-update-role-config", "--update-role-config", action='store',
                    help="re-render the templates with updated role details. Values: yes|no", required=False)
parser.add_argument("-ostype ", "--ostype", action='store',
                    help="take input to get os flavor of local environment to setup the ecosystem . Values: mac|ubuntu", required=False)
parser.add_argument("-env-file ", "--env-file", action='store',
                    help="provide file containing portal,region and env as yaml . Values: YAML file", required=False)
parser.add_argument("-url ", "--url", action='store',
                    help="Set portal URL for blueprint/hostconfigs/network resources", required=False)
parser.add_argument("-deauth-role ", "--deauth-role", action='store',
                    help="De-authorize/remove a role from specific host or an environment", required=False)
parser.add_argument("-role ", "--role", action='store',
                    help="pass role name with -deauth-role argument. Values: hypervisor|image|storage", required=False)
parser.add_argument("-state ", "--state", action='store',
                    help="pass state info of play with -deauth-role argument. Values: absent|present", required=False)
parser.add_argument("-ip ", "--ip", action='store',
                    help="pass ip with -deauth-role argument. Values: string (OPTIONAL). env value will take precdence if not provided.", required=False)
parser.add_argument("-onprem ", "--onprem", action='store',
                    help="set onprem yes to enable on-prem specific options.", required=False)
parser.add_argument("-ip-addr", "--ip-addr", required=False,
                    help="to be used with onprem option. The VIP IP address to add to /etc/hosts.")
parser.add_argument("-fqdn", "--fqdn", required=False,
                    help="to be used with onprem option. Set the FQDN of the UI.")
parser.add_argument("-fqdninfra", "--fqdninfra", required=False,
                    help="to be used with onprem option. Set The Infra FQDN of the UI.")
args = parser.parse_args()

###############################################################################
#                           Global section                                    #
###############################################################################
# Directory creations
yaml_data = {}
if args.env_file:
   yaml_data = pcdInstallHelper.loadEnvFile(args.env_file)
env_config = {
    "portal": args.portal or yaml_data.get("portal"),
    "region": args.region or yaml_data.get("region"),
    "env": args.env or yaml_data.get("env"),
}
for key in ["portal", "region", "env"]:
  if not env_config[key]:
    print(
        f"Error: '{key}' must be provided either in the YAML file or as a command-line argument.", file=sys.stderr)
    sys.exit(1)
# Directory creations
home = os.getenv("HOME")
# userLocalDir = pcdInstallHelper.createDir(f"{home}/.config/{args.clustername}")
clustername = args.portal if args.portal else yaml_data.get("portal")
sitename = args.region if args.region else yaml_data.get("region")
subsite = args.env if args.env else yaml_data.get("env")
