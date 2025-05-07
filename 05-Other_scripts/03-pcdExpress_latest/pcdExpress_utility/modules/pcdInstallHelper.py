import yaml
import json
import subprocess
import os
#from yaml.loader import SafeLoader
from jinja2 import Environment, FileSystemLoader, Template
import sys

# get the dict from both files
def get_yaml_dict(dict1, dict2):
    for key in dict2:
        if key in dict1 and isinstance(dict1[key], dict) and isinstance(dict2[key], dict):
            get_yaml_dict(dict1[key], dict2[key])
        else:
            dict1[key] = dict2[key]
    return dict1

# perform merge of yaml and convert to json (depends on the yaml_dict function) 
def merge_yaml_files(file_paths):
    merged_data = {}
    for file_path in file_paths:
        with open(file_path, 'r') as file:
            data = yaml.safe_load(file)
            merged_data = get_yaml_dict(merged_data, data)
    return merged_data

# Generate json file for given input
def generate_save_json(data, outputfile):
    with open(outputfile, 'w') as output_file:
        json.dump(data, output_file, indent=2)

# Check file in location
def check_file_location(filename, location):
    checkFilePath = subprocess.run(['stat', f'{location}/{filename}'], stdout=subprocess.PIPE)
    if checkFilePath.returncode != 0:
        return False    
    return checkFilePath


def check_dir_location(dirname):
    checkDirPath = subprocess.run(
        ['stat', f'{dirname}'], stdout=subprocess.PIPE)
    if checkDirPath.returncode != 0:
        return False
    return checkDirPath

# Create directory in desired location
def createDir(pathname):
    if not os.path.exists(pathname):
       try:
           # Create the directory
           os.makedirs(pathname)
           print(f"creating Directory: {pathname}")
       except OSError as e:
           print(f"Error creating directory '{pathname}': {e}")

# Run playbook function
def run_ansible_playbook(playbook_path, inventory_path, args=None, collections_paths=None):
    command = ['ansible-playbook', '-i', inventory_path, playbook_path, '-v']
    if args and isinstance(args, dict):
       for key, value in args.items():
         command.extend(['-e', f"{key}={value}"])
    env = os.environ.copy()  # Copy existing environment
    if collections_paths:  # Add ANSIBLE_COLLECTIONS_PATHS if provided
        env['ANSIBLE_COLLECTIONS_PATHS'] = collections_paths
    process = subprocess.run(command, capture_output=True, text=True, env=env)

    
    env = os.environ.copy()
    env['ANSIBLE_DEPRECATION_WARNINGS'] = 'False'
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        for line in iter(process.stdout.readline, ''):
            print(line, end='')
        process.wait()
        if process.returncode != 0:
            print(f"\nError running {playbook_path}:")
            for line in iter(process.stderr.readline, ''):
                print(line, end='')

    except FileNotFoundError:
        print(f"Command not found: {command[0]}")
    except Exception as e:
        print(f"An error occurred while running the playbook: {e}")

# Run all playbook in the config directory
def apply_playbooks_with_prefix(directory, prefix):
    for file in os.listdir(directory):
        if file.startswith(prefix) and (file.endswith('.yaml') or file.endswith('.yml')):
            playbook_path = os.path.join(directory, file)
            print(f"Running playbook: {playbook_path}")
            run_ansible_playbook(playbook_path)

# Generate vars file for given resource
def render_vars_template(userFilePath, template_path, template_file, output_path):
    try:
        with open(f"{userFilePath}", 'r') as yaml_file:
            context = yaml.safe_load(yaml_file)
        env = Environment(loader=FileSystemLoader(template_path))
        template = env.get_template(f'{template_file}')
        clusterBluePrintRender = template.render(context)
        vars_file_path = f"{output_path}"
        with open(vars_file_path, 'w') as file:
            file.write(clusterBluePrintRender)
    except Exception as e:
        print(f"Error rendering template: {e}")
        exit(1)
    print(f"vars file generated successfully and saved at location: \n{output_path}\n")

# Generate playbooks for the resources 
def generate_playbook(play_vars_file, template_dir, play_template_file, playBookDirectory, resourcename, clustername, sitename):
    print(f"Generating playbooks for {resourcename} resources")
    try:
        with open(play_vars_file, 'r') as f:
            vars_data = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: The file {play_vars_file} does not exist.")
        exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file {play_vars_file}: {e}")
        exit(1)
    if resourcename == "networks":
        resources = vars_data.get('pcd', {}).get('prod', {}).get('network', {})
        resources_names = list(resources.keys())
    else:
        resources = vars_data.get('pcd', {}).get('prod', {}).get(f'{resourcename}', {})
        resources_names = list(resources.keys())
    try:
        env = Environment(loader=FileSystemLoader(f'{template_dir}'))
        playbook_template = env.get_template(play_template_file)
    except Exception as e:
        print(f"Error loading template: {e}")
        exit(1)
    template_data = {
        "vars_files_path": f"../vars/{clustername}-{sitename}_{resourcename}_vars.yaml",
        resourcename: resources_names
    }
    try:
        resourcePrintPlayRender = playbook_template.render(template_data)
    except Exception as e:
        print(f"Error rendering template: {e}")
        exit(1)
    output_path = f"{playBookDirectory}/{clustername}-{resourcename}_deploy.yaml"
    try:
        with open(output_path, 'w') as file:
            file.write(resourcePrintPlayRender)
    except OSError as e:
        print(f"Error writing to file {output_path}: {e}")
        exit(1)
    print(f"{resourcename} cluster playbook generated successfully and saved at location: \n{output_path}\n")

# Get cloud auth details:
def fetch_openstack_auth_data(file_path, regionname):
    try:
        checkTemplateDir = subprocess.run(['stat', f'{file_path}'], stdout=subprocess.PIPE)
        if checkTemplateDir.returncode != 0:
            print(f"No user defined templates directory named {file_path}")
            sys.exit(1)
        with open(file_path, 'r') as file:
            data = yaml.safe_load(file)
        clouds = data.get('clouds', {})
        cloud_details = clouds.get(regionname, {})
        if cloud_details:
            auth_details = cloud_details.get('auth', {})
            auth_url = auth_details.get('auth_url')
            password = auth_details.get('password')
            cloud_username = auth_details.get('username')
            cloud_project_name = auth_details.get('project_name')
            cloud_region_name = cloud_details.get('region_name')

            return auth_url, password, cloud_username, cloud_project_name, cloud_region_name
        else:
            return None, None
    except Exception as e:
        print(f"Error getting clouds credentails details: {e}")
        exit(1)

# Run all shell commands:
def getShellOutput(cmd, printSet=False, output_file=None):
    sys.stdout.flush()
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, shell=True, universal_newlines=True)
    ret = []
    out = process.stdout.readline()
    if out == "":
      out = process.stderr.readline()
    while out != "" or process.poll() is None:
        if out:
            ret.append(out.strip())
            if printSet:
                print(out.strip())
            if output_file:
                with open(output_file, 'a') as file:
                    file.write(out)
        out = process.stdout.readline()
        if out == "":
          out = process.stderr.readline()
    rc = process.poll()
    return ret, rc

# Generate node config data from user provided yaml file:

def render_userconfig_templates(yaml_file_path, jinja_template_path, output_file_path):
    with open(yaml_file_path, 'r') as yaml_file:
        yaml_data = yaml.safe_load(yaml_file)
    environment_name = yaml_data.get('environment', 'default_environment')
    for host_ip, host_data in yaml_data.get("hosts", {}).items():
        if "persistent_storage" in host_data:
            print(f"Processing persistent_storage for {host_ip}: {host_data['persistent_storage']}")
    with open(jinja_template_path, 'r') as template_file:
        template = Template(template_file.read())
    rendered_output = template.render(
        cloud=yaml_data['cloud'],
        hosts=yaml_data['hosts'],
        url=yaml_data['url'],
        environment_name=environment_name
    )
    os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
    with open(output_file_path, 'w') as output_file:
        output_file.write(rendered_output)
    print(f"Rendered output saved to: {output_file_path}")

#Function to accept and remove a host from specific env or remove all hosts with ENV name, exclude node-onboard
def deauthorize_host_role(inventorypath, playbookpath,cloud_name,enviroment, role, rolestate, ipaddr=None):
    role_dict= {
        "hypervisor": "hypervisor",
        "image-library": "image",
        "persistent-storage": "storage"
    }
    #excluded_roles = [role_map.get(r, r) for r in all_pcd_roles if r != role]
    if  role == "node_onboard" or role == "node-onboard":
        print(f"cannot remove {role} which is the primary role.. ")
        sys.exit(1)
    if  role == " " or role is None :
        print("No roles provided.. provide role name which takes  any one of hypervisor/image/storage as input and try again.")
        sys.exit(1)
    if inventorypath is None or inventorypath == " " :
        print("No inventory file provided.. provide the correct inventory file and try again..")
        sys.exit(1)
    if playbookpath is None or playbookpath == " " :
        print("No playbook file provided.. provide the correct playbook file and try again..")
        sys.exit(1)
    if cloud_name is None or cloud_name == " " :
        print("No  cloud name  provided.. provide the correct cloudname value and try again..")
        sys.exit(1)
    if cloud_name is None or cloud_name == " " :
        print("No  cloud name  provided.. provide the correct cloudname value and try again..")
        sys.exit(1)
    if rolestate is None or rolestate == " " :
        print("No role state provided.. set it to absent or present for specific role and try again..")
        sys.exit(1)
    for key in role_dict.keys():
      if key == role:
        pcd_role = key
        int_role = role_dict[key]

    if str(ipaddr) is not None or str(ipaddr) != " ":
        ansible_command = ["ansible-playbook","-i", f"{inventorypath}",f"{playbookpath}","-e", f"cloud_name={cloud_name}","-e",f"cloudname={cloud_name}","-e", f"environment={enviroment}","-e",f"excluded_roles={pcd_role}", "-e", f"{int_role}={rolestate}",f'--limit=localhost,{str(ipaddr)}', "-v"]
    else:
        ansible_command = ["ansible-playbook","-i", f"{inventorypath}",f"{playbookpath}","-e", f"cloud_name={cloud_name}","-e", f"cloudname={cloud_name}","-e", f"environment={enviroment}","-e", f"excluded_roles={pcd_role}","-e", f"{int_role}={rolestate}","-v"]
    process = subprocess.Popen(ansible_command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True, bufsize=1, universal_newlines=True)
    for line in process.stdout:
        print(line, end="")
    process.wait()
    return process.returncode

# Check the URL in the yaml file to ensure its not tampered
def check_yaml_url(dir, prefix, string):
    print("Verifying URL string in the user config..")
    for file in os.listdir(dir):
        if file.startswith(prefix) and (file.endswith('.yaml') or file.endswith('.yml')):
            file_path = os.path.join(dir, file)
            try:
                with open(file_path, 'r') as file:
                    data = yaml.safe_load(file)
                    url = data.get('pcd', {}).get('prod', {}).get('url', '')
                    if string not in url:
                        print("region name difference found.")
                        print(f"Affected vars file: {file.name}") 
                        print(f"The DU in the URL section found in the file: {url}")
                        print(f"Supplied DU name in the command line option: {string}")
                        return False
                    print("string match and found..")
                return True
            except Exception as e:
                print(f"Error processing file '{file}': {e}")

# support function for using with -env-file option:
def loadEnvFile(env_file):
    try:
        with open(env_file, "r") as file:
            data = yaml.safe_load(file)
            return data or {}
    except FileNotFoundError:
        print(f"Error: File '{env_file}' not found.", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}", file=sys.stderr)
        sys.exit(1)

# take inputs from user to render the enviornment file
def renderEnvtemplate(template_path, output_path, portal, region, env, url):
    with open(template_path, "r") as file:
        template_content = file.read()
    template = Template(template_content)
    rendered_content = template.render(portal=portal, region=region, env=env, url=url)
    with open(output_path, "w") as output_file:
        output_file.write(rendered_content)
    print(f"Template rendered successfully and saved to: {output_path}")
