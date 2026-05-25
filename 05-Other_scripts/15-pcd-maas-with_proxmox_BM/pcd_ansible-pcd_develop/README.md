## pcdExpress framework
This repo  contains the automation scripts for working with Private Cloud Director deployment and lifecycle management that is applied via pcdExpress wrapper which uses python3. The framework is built on three elements:

- *pcdExpress python script*: It offers provides a user-driven approach to generate and apply user provided inputs to PCD control resources as well onboarding hosts in to PCD. 
- *Ansible*: It serves as the core engine to apply the playbooks on respective resources. 
- *PF9 ansible collections*: These are the custom ansible collections that work with the ansible openstack provider to apply and modify resources like the `blueprint`, `hostconfigs` and others within the PCD ecosystem.
---

Table of content:
- [pcdExpress framework](#pcdexpress-framework)
- [Setup](#setup)
  - [Prerequisites](#prerequisites)
  - [Install PCD Ansible Collection](#install-pcd-ansible-collection)
  - [Configure Ansible OpenStack Cloud Plugin](#configure-ansible-openstack-cloud-plugin)
  - [Test the connection](#test-the-connection)
  - [Resource configuration references](#resource-configuration-references)
    - [1. Blueprint resource configuration](#1-blueprint-resource-configuration)
    - [2. hostconfigs resource configuration](#2-hostconfigs-resource-configuration)
    - [3. Network resource configuration](#3-network-resource-configuration)
    - [4. Host/node onboarding under DU management](#4-hostnode-onboarding-under-du-management)
      - [Onboarding host steps for SaaS based controlplane deployments](#onboarding-host-steps-for-saas-based-controlplane-deployments)
        - [Adding hypervisor role to nodes](#adding-hypervisor-role-to-nodes)
        - [Adding image-libary role to nodes](#adding-image-libary-role-to-nodes)
        - [Adding persistent-storage role to nodes](#adding-persistent-storage-role-to-nodes)
      - [Removing Roles from group of nodes from an environment or single node in specific environment group](#removing-roles-from-group-of-nodes-from-an-environment-or-single-node-in-specific-environment-group)
    - [Steps to Onboard hosts  for on-prem based controlplane deployments](#steps-to-onboard-hosts--for-on-prem-based-controlplane-deployments)
- [Quick command references](#quick-command-references)
  - [Flags and options](#flags-and-options)
  - [Blueprint creation and management](#blueprint-creation-and-management)
  - [Hostconfigs creation and management](#hostconfigs-creation-and-management)
  - [Network creation and management](#network-creation-and-management)
  - [Onboarding and assigning Roles to nodes For SaaS based deployments](#onboarding-and-assigning-roles-to-nodes-for-saas-based-deployments)
  - [Onboarding and assigning Roles to nodes For On-prem based deployments](#onboarding-and-assigning-roles-to-nodes-for-on-prem-based-deployments)


## Setup

### Prerequisites

* Ubuntu 22 based host
* Python 3.6+

### Install PCD Ansible Collection

* Clone this current repo locally onto a host which has access to the PCD environment. 

All the required dependencies, including the Ansible binaries and PCD Collection, can be installed using the following command:

```bash
./pcdExpress.py -portal <region> -region <location> --url "<URL Of the DU portal>" --env <env_type> --ostype ubuntu --setup-environment yes

example: adding a single site with a region
$ ./pcdExpress -portal ACME -region nyc --env staging --ostype ubuntu --setup-environment yes
ACME-play_data/nyc/
├── collections
│   ├── README.md
│   ├── galaxy.yml
│   ├── meta
│   │   └── runtime.yml
│   ├── plugins
│   │   ├── README.md
│   │   ├── module_utils
│   │   │   ├── __init__.py
│   │   │   ├── helper.py
│   │   │   └── logger.py
│   │   └── modules
│   │       ├── __init__.py
│   │       ├── blueprint.py
│   │       ├── hostconfig.py
│   │       ├── network.py
│   │       └── roles.py
│   ├── requirements.txt
│   └── requirements.yml
├── group_vars
├── inventory
│   └── staging
├── logs
│   └── pcd.log
├── playbooks
│   └── roles
│       ├── common
│       │   └── tasks
│       │       ├── hostid.yml
│       │       └── token.yml
│       └── node_onboard
│           └── tasks
│               ├── cloud-ctl.yml
│               ├── hostagent.yml
│               └── main.yml
├── tasks
└── vars
```

This will perform below tasks:

* Create two directories `user_configs` and `portal-plays` in the current location. Each of these directories will have hiararchy if sub-directories containing required files where some  files in the user_configs/ directory will have some of the values populated with the given inputs. 
* Setup the python3 environment with required libraries like openstack along with a custom PF9 ansible collection modules that will be responisble to apply and manage PCD related configurations. The modules will reside in the the collections directory of respective `region` directory.
* Places some of the required tasks and play files for setting up the PCD deployment workflows.
  
This command can further be extended to create and maintain multiple enviroments from the same host like for example, if there is another region to be created, the command can be:
```
example: add more site to a region
$ ./pcdExpress -portal ACME -region nyc-2 --env staging --setup-environment yes

ACME-play_data/
├── nyc
│   ├── collections
│   │   ├── meta
│   │   └── plugins
│   │       ├── module_utils
│   │       └── modules
│   ├── group_vars
│   ├── inventory
│   │   └── staging
│   ├── logs
│   ├── playbooks
│   │   └── roles
│   │       ├── common
│   │       │   └── tasks
│   │       └── node_onboard
│   │           └── tasks
│   ├── tasks
│   └── vars
└── nyc-2
    ├── collections
    │   ├── meta
    │   └── plugins
    │       ├── module_utils
    │       └── modules
    ├── group_vars
    ├── inventory
    │   └── staging
    ├── logs
    ├── playbooks
    │   └── roles
    │       ├── common
    │       │   └── tasks
    │       └── node_onboard
    │           └── tasks
    ├── tasks
    └── vars
```

After creation of these directories the resource of interest and any further configuration, we will focus on the `user_configs` directory which will now be available in the current location with the required hiararchy and sample files that would need to be configured as per the environment:
```
user_configs
├── ACME
│   └── nyc
│       ├── control_plane
│       │   ├── acme-nyc-blueprints-config.yaml
│       │   ├── acme-nyc-hostconfigs.yaml
│       │   └── acme-nyc-networks.yaml
│       ├── data_plane
│       ├── node-onboarding
│       │   └── acme-nyc-nodesdata.yaml
│       ├── sarvind-nyc-develop-environment.yaml
```
Each site in the `user_config/` directyory has Three sub-directories which will be referred by the script during deployment phase:

* `control_plane`: Should contain the configuration yaml files for the contolplane resources such as the Blueprint, hostconfigs, cinder and glance backends.
* `data_plane`: Should contain confiiguration YAML files for the hypervisor nodes that are to be onboarded to specific KDU region. 
* `node-onboarding`: This will basically contain sample file which user need to modify and enter the hosts/nodes data that needs to be onboarded.

To populate the required YAML configuraton, copy the sample YAML from  the `user_resource_examples/` directory to the newly created `user_configs`directory under respective sub-directories. This example directory contains examples of the required parameters that will be necessary to setup and and configure the respective resource items on control or on the data plane side:
```
user_resource_examples
├── DIR_CLOUD_NAME
│   └── DIR_REGION_NAME
│       ├── control_plane
│       │   ├── CLOUD-SITENAME-subnets-config.yaml
│       │   ├── CLOUDNAME-SITENAME-blueprints-config.yaml
│       │   ├── CLOUDNAME-SITENAME-hostconfigs.yaml
│       │   └── CLOUDNAME-SITENAME-networks.yaml
│       └── data_plane
│           └── REGION-SITENAME-hostagentconfigs.yaml
├── environment-file.yaml.j2
└── host_onboard_data.yaml
```
**NOTE**:

* It is important to name the files as *regionname-site* as prefix  
* The `cloudname` is the regioname.
* `environment-file.yaml.j2` should not be modied under this resource directory. It is for internal script action purposes. 

### Configure Ansible OpenStack Cloud Plugin

Merge the following configuration into your `~/.config/openstack/clouds.yaml` which will be used by the openstack ansible provider. Create it if it doesn't exist:
```
clouds:
  titan:
    auth:
     auth_url: https://<DU-name>.app.staging-pcd.platform9.com/keystone/v3
     project_name: service
     username: abc@ACME.com
     password: *********
     user_domain_name: default
     project_domain_name: default
    region_name: titan
    interface: public
    identity_api_version: 3
    compute_api_version: 2
    volume_api_version: 3
    image_api_version: 2
    identity_interface: public
    volume_interface: public
```

### Test the connection

To test the openstack cli connection to the PCD API, run the following command:
```bash
openstack --os-cloud my_pcd token issue
```

### Resource configuration references

#### 1. Blueprint resource configuration

* Modify the `CLOUDNAME-SITENAME-blueprints-config.yaml` file from the sample location to the `user_configs` under the `control_plane`to the specification for the blueprint settings:
```
example: regionname-sitename here being sarvind-titan
cat user_configs/ACME-plays/nyc/control_plane/acme-nyc-blueprints-config.yaml
```
* Edit this file to match the requirements of the blueprint resource deployment:
```
prod:
  url: 'https://acme-nyc.app.staging-pcd.platform9.com' <-- URL of DU
  cloud: my_pcd
  blueprints:
    titan:
      name: titan-cluster <-- name of your cluster
      networkingType: ovn
      enableDistributedRouting: 'true'
      dnsDomainName: titan-cluster.localdomain <-- Domain required
      virtualNetworking:
        enabled: 'true'
        underlayType: geneve
        vnidRange: '4000:5000'
      vmHighAvailability:
        enabled: 'false'
      autoResourceRebalancing:
        enabled: 'true'
        rebalancingStrategy: vm_workload_consolidation
        rebalancingFrequencyMins: '20'
      imageLibraryStorage: /var/opt/image/library/data
      vmStorage: /opt/data/instances/
      storageBackends:
        ceph:
          test-backend:
            driver: Ceph
            config: {rbd_pool: libvirt-pool, rbd_user: "", volumes_dir: "", rbd_ceph_conf: /etc/ceph/ceph.conf, rbd_secret_uuid: "", rbd_max_clone_depth: '5', rbd_store_chunk_size: '4', rbd_flatten_volume_from_snapshot: 'false'}
        netapp-2:
          test-netapp:
            driver: NetApp
            config: {netappServerHostname: netapp2.example.com, netappLogin: admin}
```
* The `--setup-environment` action will create a file `user_configs/PORTAL/REGION/PORTAL-REGION-environment.yaml` file which will contain the key portal, region and env details can be referred to run the `--create` or the `--apply` commands for setting up the resources 
* Run the blueprint template create action using:
```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml  --create-blueprints yes

Generating blueprint vars files..
vars file generated successfully and saved at location:
ACME-play_data/nyc/vars/ACME-nyc_blueprints_vars.yaml

Generating playbooks for blueprints resources
blueprints cluster playbook generated successfully and saved at location:
ACME-play_data/nyc/playbooks/ACME-blueprints_deploy.yaml
```

This will produce a vars and a play file with the rendered user values which will be placed under the specific `portal-region/` directory:
```
ACME-play_data/nyc/
├── group_vars
├── inventory
│   └── staging
├── logs
│   └── pcd.log
├── playbooks
│   ├── ACME-blueprints_deploy.yaml <---
│   └── roles
│       ├── common
│       │   └── tasks
│       │       ├── hostid.yml
│       │       └── token.yml
│       └── node_onboard
│           └── tasks
│               ├── cloud-ctl.yml
│               ├── hostagent.yml
│               └── main.yml
├── tasks
└── vars
    └── ACME-nyc_blueprints_vars.yaml <--
```
**Alternate command**: `python3 pcdExpress.py -portal acme -region nyc  --env staging --create-blueprints yes`

* Run the plays using options:
```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml --apply-blueprints yes

example:
cloud region credential directory..
User defined templates directory found at user_configs
None
User defined region templates directory found..
User defined site templates directory found..
Applying blueprint config templates..
Using /Users/sarvind/git-local/pcd_ansible/ansible.cfg as config file

PLAY [localhost] ***************************************************************

TASK [Get Auth Token] **********************************************************
ok: [localhost] => {"ansible_facts": {"discovered_interpreter_python": "/Users/sarvind/git-local/pcd_ansible/pyenv/bin/python3.13"}, "auth_token": "gAAAAABnmKh8b6lqNmmQzw4FcTO-lgTRxw9Z6ZVY2Hux4drNesgz19mVzWu7QPH1lmJNj78ryZXha0lHc5Y-1P2E-LdAnqIlOdiiUTob-l70owm7Azd6rvJiYS0Quu_eZlml3HZQzHfIO3uHWxOFXB8ey7wBAhn4sJbkWyr9ich8TOG3yXLR9iQ", "changed": false}

TASK [set_fact] ****************************************************************
ok: [localhost] => {"ansible_facts": {"keystone_token": "gAAAAABnmKh8b6lqNmmQzw4FcTO-lgTRxw9Z6ZVY2Hux4drNesgz19mVzWu7QPH1lmJNj78ryZXha0lHc5Y-1P2E-LdAnqIlOdiiUTob-l70owm7Azd6rvJiYS0Quu_eZlml3HZQzHfIO3uHWxOFXB8ey7wBAhn4sJbkWyr9ich8TOG3yXLR9iQ"}, "changed": false}

TASK [Set default Config for titan] ********************************************
ok: [localhost] => {"changed": false, "new_config": "", "original_config": "{\"name\": \"titan-cluster\", \"networkingType\": \"ovn\", \"enableDistributedRouting\": true, \"dnsDomainName\": \"titan-cluster.localdomain\", \"virtualNetworking\": {\"enabled\": true, \"underlayType\": \"geneve\", \"vnidRange\": \"4000:5000\"}, \"vmHighAvailability\": {\"enabled\": false}, \"autoResourceRebalancing\": {\"enabled\": true, \"rebalancingStrategy\": \"vm_workload_consolidation\", \"rebalancingFrequencyMins\": 20}, \"imageLibraryStorage\": \"/var/opt/image/library/data\", \"vmStorage\": \"/opt/data/instances/\", \"storageBackends\": {\"ceph\": {\"test-backend\": {\"config\": {\"rbd_pool\": \"libvirt-pool\", \"rbd_user\": \"\", \"volumes_dir\": \"\", \"rbd_ceph_conf\": \"/etc/ceph/ceph.conf\", \"rbd_secret_uuid\": \"\", \"rbd_max_clone_depth\": \"5\", \"rbd_store_chunk_size\": \"4\", \"rbd_flatten_volume_from_snapshot\": \"false\"}, \"driver\": \"Ceph\"}}, \"netapp-2\": {\"test-netapp\": {\"config\": {\"netappLogin\": \"admin\", \"netappServerHostname\": \"netapp2.example.com\"}, \"driver\": \"NetApp\"}}}}"}

PLAY RECAP *********************************************************************
localhost                  : ok=3    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```
Additionally the changes can further be viewed from the UI to ensure the required changes are in place. 

#### 2. hostconfigs resource configuration

* Modify/edit the  `CLOUDNAME-SITENAME-hostconfigs-config.yaml` file under in the `user_configs` under the `control_plane` sub-directory of the required region/site with the regioname-sitename as the prefix. can takeup multiple section of config and different interface maps in conjunction to the configuration available in the UI:
```
Example: 2 separate hostconfigs with network labeling
cat user_configs/ACME/nyc/control_plane/ACME-nyc-hostconfigs-config.yaml
prod:
  url: 'https://acme-nyc.app.staging-pcd.platform9.com'
  cloud: my_pcd
  hostconfigs:
    BM_HC_novirt:
      name: BM_HC_novirt
      clusterName: titan-cluster
      networkLabels:
        ext_net: vlan.301
        int_net: vlan.305
      vmConsoleInterface: vlan.301
      hostLivenessInterface: vlan.301
      tunnelingInterface: vlan.301
      imagelibInterface: vlan.301
      mgmtInterface: vlan.301
    VMhostNet:
      name: VMhostNet
      clusterName: titan-cluster
      networkLabels:
        physnet1: ens3
      vmConsoleInterface: ens3
      hostLivenessInterface: ens3
      tunnelingInterface: ens3
      imagelibInterface: ens3
      mgmtInterface: ens3
```
* Run the playbooks and vars creation command to produce the actual plays with the above configurations:
```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml --create-hostconfigs yes

Generating hostconfigs vars files..
vars file generated successfully and saved at location:
ACME-play_data/nyc/vars/ACME-nyc_hostconfigs_vars.yaml

Generating playbooks for hostconfigs resources
hostconfigs cluster playbook generated successfully and saved at location:
ACME-play_data/nyc/playbooks/ACME-hostconfigs_deploy.yaml

example:
ACME-play_data/nyc/
├── group_vars
├── inventory
│   └── staging
├── logs
│   └── pcd.log
├── playbooks
│   ├── ACME-blueprints_deploy.yaml
│   ├── ACME-hostconfigs_deploy.yaml <--
│   └── roles
│       ├── common
│       │   └── tasks
│       │       ├── hostid.yml
│       │       └── token.yml
│       └── node_onboard
│           └── tasks
│               ├── cloud-ctl.yml
│               ├── hostagent.yml
│               └── main.yml
├── tasks
└── vars
    ├── ACME-nyc_blueprints_vars.yaml
    └── ACME-nyc_hostconfigs_vars.yaml <--
```
**Alternate Command**: `python3 pcd-install.py -portal ACME  -region nyc  --env development  --create-hostconfigs yes`

* Generate the vars and playbook using the express options:
```
./pcdExpress -env-file user_configs/acme/nyc/acme-nyc-environment.yaml -create-hostconfigs yes 

cloud region credential directory..
User defined templates directory found at user_configs
None
User defined region templates directory found..
User defined site templates directory found..
Generating hostconfigs vars files..
vars file generated successfully and saved at location:
sarvind-play_data/titan/vars/sarvind-titan_hostconfigs_vars.yaml

Generating playbooks for hostconfigs resources
hostconfigs cluster playbook generated successfully and saved at location:
sarvind-play_data/titan/playbooks/sarvind-hostconfigs_deploy.yaml
```
**Alternate method**: python3 pcdExpress.py -portal sarvind -region titan  -create-hostconfigs yes 

* Apply the playbook after verify if they are right as per the needs:
```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml -apply-hostconfigs yes 

cloud region credential directory..
User defined templates directory found at user_configs
None
User defined region templates directory found..
User defined site templates directory found..
Applying hostconfigs templates..
Using /Users/sarvind/git-local/pcd_ansible/ansible.cfg as config file

PLAY [localhost] ***************************************************************

TASK [Get Auth Token] **********************************************************
ok: [localhost] => {"ansible_facts": {"discovered_interpreter_python": "/Users/sarvind/git-local/pcd_ansible/pyenv/bin/python3.13"}, "auth_token": "gAAAAABnmNP0u6OI1Cumvngly9vYqki-WjlG6LUsCQNtrgSDbcDxy9H6nflqWKolLybd-YYlYmFigNATkqfwa-NCS4EwXxCntVA0N0i3nbdL8wIT37bBoz1G4MC69DBN3eoCtsCtNluThR8v0S9qMdZhEEmjoIIhlb3wvoKtdBEwjnWlBlBZfrs", "changed": false}

TASK [set_fact] ****************************************************************
ok: [localhost] => {"ansible_facts": {"keystone_token": "gAAAAABnmNP0u6OI1Cumvngly9vYqki-WjlG6LUsCQNtrgSDbcDxy9H6nflqWKolLybd-YYlYmFigNATkqfwa-NCS4EwXxCntVA0N0i3nbdL8wIT37bBoz1G4MC69DBN3eoCtsCtNluThR8v0S9qMdZhEEmjoIIhlb3wvoKtdBEwjnWlBlBZfrs"}, "changed": false}

TASK [Set default Config for "BM_HC_novirt"] ***********************************
ok: [localhost] => {"changed": false, "new_config": "", "original_config": ""}

TASK [Set default Config for "VMhostNet"] **************************************
ok: [localhost] => {"changed": false, "new_config": "", "original_config": "{\"id\": \"2ba4448a-0cc8-4ec6-9902-4a98c19f534d\", \"name\": \"VMhostNet\", \"mgmtInterface\": \"ens3\", \"vmConsoleInterface\": \"ens3\", \"hostLivenessInterface\": \"ens3\", \"tunnelingInterface\": \"ens3\", \"imagelibInterface\": \"ens3\", \"networkLabels\": {\"physnet1\": \"ens3\"}, \"clusterName\": \"titan-cluster\"}"}

PLAY RECAP *********************************************************************
localhost                  : ok=4    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0

```
**Alternate command**: `python3 pcdExpress.py -portal sarvind -region titan  -apply-hostconfigs yes`

#### 3. Network resource configuration

This configuration allows to create or modify network resources that are related to the underlay provider (one to which the hypervisor is connected to):
```
example:
 cat user_configs/ACME/nyc/control_plane/ACME-nyc-networks.yaml
prod:
  url: 'https://acme-nyc.app.staging-pcd.platform9.com'
  cloud: my_pcd
  networks:
    testnet2:
        name: testnet2
        admin_state_up: true
        mtu: 1500
        shared: true
        availability_zone_hints: []
        availability_zones: []
        ipv4_address_scope: null
        ipv6_address_scope: null
        'router:external': true
        description: 'test configuration'
        port_security_enabled: true
        is_default: false
        tags: []
        'provider:network_type': vlan
        'provider:physical_network': physnet1
        'provider:segmentation_id': 2012
    testnet3:
        name: testnet3
        admin_state_up: true
        mtu: 1500
        shared: true
        availability_zone_hints: []
        availability_zones: []
        ipv4_address_scope: null
        ipv6_address_scope: null
        'router:external': true
        description: 'test configuration'
        port_security_enabled: true
        is_default: false
        tags: []
        'provider:network_type': vlan
        'provider:physical_network': physnet2
        'provider:segmentation_id': 2025
```
* Generate the playbooks and respective vars from the templates using command:
```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml create-networks yes 

cloud region credential directory..
User defined templates directory found at user_configs
None
User defined region templates directory found..
User defined site templates directory found..
Generating network vars files..
vars file generated successfully and saved at location:
acme-play_data/nyc/vars/sarvind-titan_networks_vars.yaml

Generating playbooks for networks resources
networks cluster playbook generated successfully and saved at location:
acme-play_data/nyc/playbooks/sarvind-networks_deploy.yaml
```
**Alternate command**: `python3 pcdExpress.py -portal acme -region nyc  -create-networks yes `

* Apply the playbooks using the option:
```
python3 pcdExpress.py -env-file user_configs/acme/nyc/acme-nyc-environment.yaml  -apply-networks yes 
                                                            
cloud region credential directory..
User defined templates directory found at user_configs
None
User defined region templates directory found..
User defined site templates directory found..
Applying blueprint config templates..
Using /Users/sarvind/git-local/pcd_ansible/ansible.cfg as config file

PLAY [localhost] ***************************************************************

TASK [Get Auth Token] **********************************************************
ok: [localhost] => {"ansible_facts": {"discovered_interpreter_python": "/Users/sarvind/git-local/pcd_ansible/pyenv/bin/python3.13"}, "auth_token": "gAAAAABnmNGKrn1Tv6nPVe0RcIT8VXliFVTVcYWMYtiCQ2N0hT5SzGVsxfzhOnzcsLMBvFz2n8fZMY_g3daWZ7JDMSf2TTOT8CaiL_Xkb7Zko9g05AIyq28Z2nvfKOdc2UjBJtvP2yYKpT2FgzDKCeRhVpxI1hBEc11ofUIfv1qfrNgq_haH6XA", "changed": false}

TASK [set_fact] ****************************************************************
ok: [localhost] => {"ansible_facts": {"keystone_token": "gAAAAABnmNGKrn1Tv6nPVe0RcIT8VXliFVTVcYWMYtiCQ2N0hT5SzGVsxfzhOnzcsLMBvFz2n8fZMY_g3daWZ7JDMSf2TTOT8CaiL_Xkb7Zko9g05AIyq28Z2nvfKOdc2UjBJtvP2yYKpT2FgzDKCeRhVpxI1hBEc11ofUIfv1qfrNgq_haH6XA"}, "changed": false}

TASK [Set default Config for testnet2] *****************************************
changed: [localhost] => {"changed": true, "new_config": "{\"network\": {\"name\": \"testnet2\", \"admin_state_up\": true, \"mtu\": 1500, \"shared\": true, \"router:external\": true, \"description\": \"test configuration\", \"port_security_enabled\": true, \"is_default\": false, \"provider:network_type\": \"vlan\", \"provider:physical_network\": \"physnet1\", \"provider:segmentation_id\": 2012}}", "original_config": ""}

TASK [Set default Config for testnet3] *****************************************
changed: [localhost] => {"changed": true, "new_config": "{\"network\": {\"name\": \"testnet3\", \"admin_state_up\": true, \"mtu\": 1500, \"shared\": true, \"router:external\": true, \"description\": \"test configuration\", \"port_security_enabled\": true, \"is_default\": false, \"provider:network_type\": \"vlan\", \"provider:physical_network\": \"physnet2\", \"provider:segmentation_id\": 2025}}", "original_config": ""}

PLAY RECAP *********************************************************************
localhost                  : ok=4    changed=2    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```
**Alternate command**: `python3 pcdExpress.py -portal sarvind -region titan  -apply-networks yes `        
This configuration can be applied before or after node onboarding operations.

#### 4. Host/node onboarding under DU management

##### Onboarding host steps for SaaS based controlplane deployments

To onboard hosts, modify the  `{Portal}-{region}-nodesdata.yaml` under the `user_resource_examples/node_onboarding` directory and modify this file to contain the cloud or the region name , the URL of the DU, environment type which can be anything that will help to group the hosts like dev, staging or production. It can be any name string that will help to uniquely identify a group of hosts so configuration can be applied in a batch and any changes will only affect a smaller group of nodes. A sample output of this file:
```
cloud: "nyc"
url: "https://acme-nyc.app.staging-pcd.platform9.com/"
environment: "production"
hosts:
  172.29.21.227:
    ansible_ssh_user:  "ubuntu"
    ansible_ssh_private_key_file: ssh-hypervisior.key
    roles:
      - "node_onboard"
    hostconfigs: "VMhostNet"
```
**NOTE**: This yaml file would require the `hostconfigs`, and `roles` definition set correctly for the next step to be executed properly

- Create/render this file with options as below to produce the required file that will help create the vars and playbooks in the next step:

```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml -render-userconfig user_resource_examples/node_onboarding/{portal}-{region}-nodesdata.yaml
```
**Alternate command**: `./pcdExpress  -portal acme -region nyc -env development -render-userconfig user_resource_examples/node_onboarding/{portal}-{region}-nodesdata.yaml`

  **NOTE**: 
    -  For maintaining different environment with names like `develop` `production1`, or `staging`  the `host_onboard_data.yaml` has been be created separate for each  environment. There is no dependency of the naming of this user provided file. 
    - If the ansible user and key is not provided these values will be set to something default which will not be suitable for accessing those host. 
    - This operation will not create/add any users to the hosts.  The ansible user should be added and available before the operation and it should have passwordless sudo configured. 
  

* Create the required inventory file and the playbook templates using option:
```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml --create-hostagents-configs yes

cloud region credential directory present. proceeding...
Generating inventory files..
vars file generated successfully and saved at location:
acme-play_data/nyc/inventory/staging/hosts

vars file generated successfully and saved at location:
acme-play_data/nyc/playbooks/acme-nyc-production-node-onboard.yaml

``` 
**Alternate command**: `./pcdExpress  -portal acme -region nyc  --env production  --create-hostagents-configs yes`

* To onboard the host run:
  
```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml --apply-hosts-onboard yes

Triggering node onboarding playbooks..
Using /Users/sarvind/git-local/pcd_ansible/ansible.cfg as config file

PLAY [localhost] ***************************************************************

TASK [Read configuration for requested cloud] **********************************
ok: [localhost] => {"censored": "the output has been hidden due to the fact that 'no_log: true' was specified for this result", "changed": false}

TASK [Find index of cloud name in cloud_config] ********************************
ok: [localhost] => {"censored": "the output has been hidden due to the fact that 'no_log: true' was specified for this result", "changed": false}

TASK [Set the cloud variable] **************************************************
ok: [localhost] => {"censored": "the output has been hidden due to the fact that 'no_log: true' was specified for this result", "changed": false}

PLAY [develop] *****************************************************************

TASK [Get roles for servers] ***************************************************
ok: [172.29.21.227] => {"ansible_facts": {"rolenames": ["node_onboard"]}, "changed": false}

TASK [Include roles for the nodes] *********************************************
included: node_onboard for 172.29.21.227 => (item=node_onboard)

TASK [node_onboard : include_tasks] ********************************************
included: /Users/sarvind/git-local/pcd_ansible/sarvind-play_data/titan/playbooks/roles/node_onboard/tasks/cloud-ctl.yml for 172.29.21.227

TASK [node_onboard : Download latest cloud-ctl] ********************************
ok: [172.29.21.227] => {"ansible_facts": {"discovered_interpreter_python": "/usr/bin/python3.10"}, "changed": false, "checksum_dest": "64cc35b332b26a0cd9dbcdd8f08f729263d31bda", "checksum_src": "64cc35b332b26a0cd9dbcdd8f08f729263d31bda", "dest": "/usr/bin/cloud-ctl", "elapsed": 0, "gid": 1000, "group": "ubuntu", "md5sum": "c401d7a1b4f888d092a3614ddeee2473", "mode": "01363", "msg": "OK (17539224 bytes)", "owner": "ubuntu", "size": 17539224, "src": "/home/ubuntu/.ansible/tmp/ansible-tmp-1738133003.8358028-18062-247412855117050/tmpyfrng0r2", "state": "file", "status_code": 200, "uid": 1000, "url": "https://cloud-ctl.s3.us-west-1.amazonaws.com/cloud-ctl"}

TASK [node_onboard : include_tasks] ********************************************
included: /Users/sarvind/git-local/pcd_ansible/sarvind-play_data/titan/playbooks/roles/node_onboard/tasks/hostagent.yml for 172.29.21.227

TASK [node_onboard : Check for existing host_id] *******************************
ok: [172.29.21.227] => {"changed": false, "stat": {"atime": 1738132008.546754, "attr_flags": "e", "attributes": ["extents"], "block_size": 4096, "blocks": 8, "charset": "us-ascii", "checksum": "7ab717cbd38943e37efa5706bc531aefea95e3f9", "ctime": 1738132007.3027747, "dev": 64513, "device_type": 0, "executable": false, "exists": true, "gid": 1001, "gr_name": "pf9group", "inode": 259221, "isblk": false, "ischr": false, "isdir": false, "isfifo": false, "isgid": false, "islnk": false, "isreg": true, "issock": false, "isuid": false, "mimetype": "text/plain", "mode": "0644", "mtime": 1738132007.3027747, "nlink": 1, "path": "/etc/pf9/host_id.conf", "pw_name": "pf9", "readable": true, "rgrp": true, "roth": true, "rusr": true, "size": 58, "uid": 1001, "version": "4000528697", "wgrp": false, "woth": false, "writeable": true, "wusr": true, "xgrp": false, "xoth": false, "xusr": false}}

TASK [node_onboard : Set Cloud-ctl Config] *************************************
skipping: [172.29.21.227] => {"changed": false, "false_condition": "not host_id_conf.stat.exists", "skip_reason": "Conditional result was False"}

TASK [node_onboard : Prep Node] ************************************************
skipping: [172.29.21.227] => {"changed": false, "false_condition": "not host_id_conf.stat.exists", "skip_reason": "Conditional result was False"}

PLAY RECAP *********************************************************************
172.29.21.227              : ok=6    changed=0    unreachable=0    failed=0    skipped=2    rescued=0    ignored=0
localhost                  : ok=3    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```
**Alternate command**: `./pcdExpress -portal acme -region nyc  --env production  --apply-hosts-onboard yes`
At this point the host should be visible in the  UI in `unauthorized` state which can then be assigned a role to make it operational further. 

###### Adding hypervisor role to nodes
Each of the node data in the user provided yaml file can have specific roles assigned which will then be called and applied during the play execution. To assign hypervisor role to now visible host in the DU by setting the `hypervisor` in the roles section of user config:
```yaml
cloud: "nyc"
url: "https://acme-nyc.app.staging-pcd.platform9.com/"
environment: "production"
hosts:
  172.29.21.227:
    ansible_ssh_user:  "ubuntu"
    ansible_ssh_private_key_file: ssh-hypervisior.key
    roles:
      - "node_onboard"
      - "hypervisor"
    hostconfigs: "VMhostNet"
```

- Re-run the render command to update the playbooks:
```bash
python3 pcdExpress.py -env-file user_configs/acme/nyc/acme-nyc-environment.yaml -render-userconfig user_configs/env_host.yaml
$ python3 pcdExpress.py -env-file user_configs/acme/nyc/acme-nyc-environment.yaml  --create-hostagents-configs yes
```
- Apply the plays using:
```
python3 pcdExpress.py -env-file user_configs/acme/nyc/acme-nyc-environment.yaml --apply-hosts-onboard yes

PLAY [localhost] ***************************************************************

TASK [Read configuration for requested cloud] **********************************
ok: [localhost] => {"censored": "the output has been hidden due to the fact that 'no_log: true' was specified for this result", "changed": false}

TASK [Get Auth Token] **********************************************************
ok: [localhost] => {"auth_token": "gAAAAABnpERubPnuOP2MZB_LzLzDZ-nXQhccAKbA6Cd1OIZc_ysjwdtCRcvi_5VrSTpQC4Qvm7Z86DI9VXnT5NN9c-HZzvXgcSQmhUpy-fepIS-gvIDn0drNIsFsRhvIQfC_L5GsCtQwwd0tCoE2ohINt6sJI_Yoduo4j3kZHmk8iQ5NVlcfngM", "changed": false}

TASK [set_fact] ****************************************************************
ok: [localhost] => {"ansible_facts": {"keystone_token": "gAAAAABnpERubPnuOP2MZB_LzLzDZ-nXQhccAKbA6Cd1OIZc_ysjwdtCRcvi_5VrSTpQC4Qvm7Z86DI9VXnT5NN9c-HZzvXgcSQmhUpy-fepIS-gvIDn0drNIsFsRhvIQfC_L5GsCtQwwd0tCoE2ohINt6sJI_Yoduo4j3kZHmk8iQ5NVlcfngM"}, "changed": false}

TASK [Save keystone token for the current operation] ***************************
changed: [localhost] => {"censored": "the output has been hidden due to the fact that 'no_log: true' was specified for this result", "changed": true}

TASK [Find index of cloud name in cloud_config] ********************************
ok: [localhost] => {"censored": "the output has been hidden due to the fact that 'no_log: true' was specified for this result", "changed": false}

TASK [Set the cloud variable] **************************************************
ok: [localhost] => {"censored": "the output has been hidden due to the fact that 'no_log: true' was specified for this result", "changed": false}

PLAY [staging] *****************************************************************

TASK [Get roles for servers] ***************************************************
ok: [172.29.21.227] => {"ansible_facts": {"rolenames": ["node_onboard", "hypervisor"]}, "changed": false}

TASK [export network hostconfigs names] ****************************************
ok: [172.29.21.227] => {"ansible_facts": {"hostconfig": "VMhostNet"}, "changed": false}

TASK [set_fact] ****************************************************************
ok: [172.29.21.227] => {"censored": "the output has been hidden due to the fact that 'no_log: true' was specified for this result", "changed": false}

TASK [set_fact] ****************************************************************
ok: [172.29.21.227] => {"ansible_facts": {"cloud_name": "titan"}, "changed": false}

TASK [Include roles for the nodes] *********************************************
included: node_onboard for 172.29.21.227 => (item=node_onboard)
included: hypervisor for 172.29.21.227 => (item=hypervisor)

TASK [node_onboard : include_tasks] ********************************************
included: /Users/sarvind/test-dir/04-build-testing/pcd_ansible-pcd_develop/sarvind-play_data/titan/playbooks/roles/node_onboard/tasks/cloud-ctl.yml for 172.29.21.227

TASK [node_onboard : Download latest cloud-ctl] ********************************
ok: [172.29.21.227] => {"ansible_facts": {"discovered_interpreter_python": "/usr/bin/python3.10"}, "changed": false, "checksum_dest": "64cc35b332b26a0cd9dbcdd8f08f729263d31bda", "checksum_src": "64cc35b332b26a0cd9dbcdd8f08f729263d31bda", "dest": "/usr/bin/cloud-ctl", "elapsed": 0, "gid": 0, "group": "root", "md5sum": "c401d7a1b4f888d092a3614ddeee2473", "mode": "01363", "msg": "OK (17539224 bytes)", "owner": "root", "size": 17539224, "src": "/home/ubuntu/.ansible/tmp/ansible-tmp-1738818671.735422-29799-202808820838857/tmp30e38aj9", "state": "file", "status_code": 200, "uid": 0, "url": "https://cloud-ctl.s3.us-west-1.amazonaws.com/cloud-ctl"}

TASK [node_onboard : include_tasks] ********************************************
included: /Users/sarvind/test-dir/04-build-testing/pcd_ansible-pcd_develop/sarvind-play_data/titan/playbooks/roles/node_onboard/tasks/hostagent.yml for 172.29.21.227

TASK [node_onboard : Check for existing host_id] *******************************
ok: [172.29.21.227] => {"changed": false, "stat": {"atime": 1738776117.7027795, "attr_flags": "e", "attributes": ["extents"], "block_size": 4096, "blocks": 8, "charset": "us-ascii", "checksum": "191bbbd7ad170058b55a68a34d2a07a24797c8c4", "ctime": 1738776116.4628005, "dev": 64513, "device_type": 0, "executable": false, "exists": true, "gid": 1001, "gr_name": "pf9group", "inode": 277849, "isblk": false, "ischr": false, "isdir": false, "isfifo": false, "isgid": false, "islnk": false, "isreg": true, "issock": false, "isuid": false, "mimetype": "text/plain", "mode": "0644", "mtime": 1738776116.4628005, "nlink": 1, "path": "/etc/pf9/host_id.conf", "pw_name": "pf9", "readable": true, "rgrp": true, "roth": true, "rusr": true, "size": 58, "uid": 1001, "version": "937140732", "wgrp": false, "woth": false, "writeable": true, "wusr": true, "xgrp": false, "xoth": false, "xusr": false}}

TASK [node_onboard : Set Cloud-ctl Config] *************************************
skipping: [172.29.21.227] => {"changed": false, "false_condition": "not host_id_conf.stat.exists", "skip_reason": "Conditional result was False"}

TASK [node_onboard : Prep Node] ************************************************
skipping: [172.29.21.227] => {"changed": false, "false_condition": "not host_id_conf.stat.exists", "skip_reason": "Conditional result was False"}

TASK [hypervisor : shell] ******************************************************
changed: [172.29.21.227] => {"changed": true, "cmd": "grep host_id /etc/pf9/host_id.conf | cut -d '=' -f2 | sed -e 's/ //g'", "delta": "0:00:00.004352", "end": "2025-02-06 05:11:28.612326", "msg": "", "rc": 0, "start": "2025-02-06 05:11:28.607974", "stderr": "", "stderr_lines": [], "stdout": "b667ee48-9c0d-4bc2-8e01-46d295879369", "stdout_lines": ["b667ee48-9c0d-4bc2-8e01-46d295879369"]}

TASK [hypervisor : Set fact for Host ID] ***************************************
ok: [172.29.21.227] => {"ansible_facts": {"hostid": "b667ee48-9c0d-4bc2-8e01-46d295879369", "tags": "hostid"}, "changed": false}

TASK [hypervisor : Display Host ID] ********************************************
ok: [172.29.21.227] => {
    "hostid": "b667ee48-9c0d-4bc2-8e01-46d295879369"
}

TASK [hypervisor : Set Keystone Token Fact] ************************************
ok: [172.29.21.227] => {"ansible_facts": {"keystone_token": "gAAAAABnpERubPnuOP2MZB_LzLzDZ-nXQhccAKbA6Cd1OIZc_ysjwdtCRcvi_5VrSTpQC4Qvm7Z86DI9VXnT5NN9c-HZzvXgcSQmhUpy-fepIS-gvIDn0drNIsFsRhvIQfC_L5GsCtQwwd0tCoE2ohINt6sJI_Yoduo4j3kZHmk8iQ5NVlcfngM"}, "changed": false}

TASK [hypervisor : Set PCD Roles] **********************************************
ok: [172.29.21.227] => {"changed": false, "msg": "Role 'hypervisor' is already applied. No changes made."}

PLAY RECAP *********************************************************************
172.29.21.227               : ok=15   changed=1    unreachable=0    failed=0    skipped=2    rescued=0    ignored=0
localhost                  : ok=6    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0

```

###### Adding image-libary role to nodes
To assign `image-libary` role to now visible host in the DU by setting the `hypervisor` in the roles section of user config:
```yaml
cloud: "nyc"
url: "https://acme-nyc.app.staging-pcd.platform9.com/"
environment: "production"
hosts:
  172.29.21.227:
    ansible_ssh_user:  "ubuntu"
    ansible_ssh_private_key_file: ssh-hypervisior.key
    roles:
      - "node_onboard"
      - "hypervisor"
      - "image-library"
    hostconfigs: "VMhostNet"
```
**NOTE**: When setting the `image-library role` based on the backend storage requirements, **the `persistent-storage` role along with the backend labels must be passed to ensure the glance or the image-library role has the backend mapping done properly.** 

- Re-run the render command to update the playbooks:
```bash
$ ./pcdExpress -env-file user_configs/acme/nyc/acme-nyc-environment.yaml -render-userconfig user_configs/env_host.yaml
$ ./pcdExpress -env-file user_configs/acme/nyc/acme-nyc-environment.yaml   --create-hostagents-configs yes
```
- Apply the playbook using:
```bash
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml  --apply-hosts-onboard yes
....
TASK \[Include roles for the nodes\] *********************************************
included: node_onboard for 172.29.21 => (item=node_onboard)
included: hypervisor for 172.29.21.227 => (item=hypervisor)
included: image-library for 172.29.21.227 => (item=image-library)
...
PLAY RECAP *********************************************************************
172.29.21.227               : ok=15   changed=1    unreachable=0    failed=0    skipped=2    rescued=0    ignored=0
localhost                  : ok=6    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```
**NOTE: As of writing image-library role can only be applied to one node in the group of nodes.**

###### Adding persistent-storage role to nodes
To assign `persistent-storage` role to now visible host in the DU by setting the `persistent-storage` in the roles section and a section named `persistent_storage` with the list of backends in the `backends` section under it of user config:
```yaml
cloud: "nyc"
url: "https://acme-nyc.app.staging-pcd.platform9.com/"
environment: "production"
hosts:
  172.29.21.227:
    ansible_ssh_user:  "ubuntu"
    ansible_ssh_private_key_file: ssh-hypervisior.key
    roles:
      - "node_onboard"
      - "hypervisor"
      - "image-library"
      - "persistent-storage"
    persistent_storage:
      backends:
        - test-netapp
        - ceph-storage-1
    hostconfigs: "VMhostNet"
```
**NOTE: The backend name mentioned in the yaml should already be created and active via the blueprint configuration for the plays to get applied successfully. This role strictly depend on the backends configuration so it is required to be added.**

- Re-run the render command to update the playbooks:
```bash
$ ./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml  -render-userconfig user_configs/env_host.yaml
$ ./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml  --create-hostagents-configs yes
```

- Apply the playbook using:
```bash
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml  --apply-hosts-onboard yes
....
TASK [Include roles for the nodes] *********************************************
included: node_onboard for 172.29.21 => (item=node_onboard)
included: hypervisor for 172.29.21.227 => (item=hypervisor)
included: image-library for 172.29.21.227 => (item=image-library)
included: persistent-storage for 172.29.21.227 => (item=persistent-storage)
...
PLAY RECAP *********************************************************************
172.29.21.227               : ok=15   changed=1    unreachable=0    failed=0    skipped=2    rescued=0    ignored=0
localhost                  : ok=6    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

##### Removing Roles from group of nodes from an environment or single node in specific environment group

The steps mentioned in this section will de-authorize the nodes by striping the assigned roles. To fully remove the nodes from PCD, the general procedure of running `cloud-ctl decommission-node` from each of those nodes will be required.

* To remove hosts grouped in an environment, ensure the role is deleted from the `nodesdata.yaml` under the `user_configs/node_onboarding/` directory. 
* Run the `--render-userconfig` option with the pcdExpress script to update the template file under the `user_configs/<portalname>/data_plane` directory
* Run the `--create-hostagents-configs yes` option to produce the new inventory and playbooks

There are two choices that will de-auth the role:

1. Using the environment name with hosts belonging to specific environment group can be  can be de-authorized with:
```bash
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml  --deauth-role yes -role hypervisor -state absent
```
This will remove the entire hosts in the given group one by one.

2. Similarly if a single host needs to be removed or de-authorized from the environment, the `-ip` or `--ip` flag with the ip address of the host  can be utilized as below with the `pcdExpress` script:
```bash
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml --deauth-role yes -role hypervisor -state absent -ip 172.29.21.52
```
**NOTE**:
  - The command process aim to ensure the user delete the role one by one consciously. 
  - Re-running the command will exit normally since the playbook will refer to the state of the resources. 
  - Support role options:
    - `image-library`
    - `persistent-storage`
    - `hypervisor`

#### Steps to Onboard hosts  for on-prem based controlplane deployments

After deployment of on-prem controlplane is completed and the portal is reachable, use the below steps to start the oboarding of the hosts

- Similar to the  SaaS based deployments, modify the  `{Portal}-{region}-nodesdata.yaml` under the `user_resource_examples/node_onboarding` directory and modify this file to contain the cloud or the region name , the URL of the DU, environment type which can be anything that will help to group the hosts like dev, staging or production. It can be any name string that will help to uniquely identify a group of hosts so configuration can be applied in a batch and any changes will only affect a smaller group of nodes. A sample output of this file:
```
cloud: "nyc"
url: "https://acme-nyc.app.staging-pcd.platform9.com/"
environment: "production"
hosts:
  172.29.21.227:
    ansible_ssh_user:  "ubuntu"
    ansible_ssh_private_key_file: ssh-hypervisior.key
    roles:
      - "node_onboard"
    hostconfigs: "VMhostNet"
```
**NOTE**: This yaml file would require the `hostconfigs`, and `roles` definition set correctly for the next step to be executed properly

- Create/render this file with options as below to produce the required file that will help create the vars and playbooks in the next step:

```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml -render-userconfig user_resource_examples/node_onboarding/{portal}-{region}-nodesdata.yaml
```
**Alternate command**: `./pcdExpress  -portal acme -region nyc -env development -render-userconfig user_resource_examples/node_onboarding/{portal}-{region}-nodesdata.yaml`

  **NOTE**: 
    -  For maintaining different environment with names like `develop` `production1`, or `staging`  the `host_onboard_data.yaml` has been be created separate for each  environment. There is no dependency of the naming of this user provided file. 
    - If the ansible user and key is not provided these values will be set to something default which will not be suitable for accessing those host. 
    - This operation will not create/add any users to the hosts.  The ansible user should be added and available before the operation and it should have passwordless sudo configured. 
  

* Create the required inventory file and the playbook templates using option:
```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml --create-hostagents-configs yes

cloud region credential directory present. proceeding...
Generating inventory files..
vars file generated successfully and saved at location:
acme-play_data/nyc/inventory/staging/hosts

vars file generated successfully and saved at location:
acme-play_data/nyc/playbooks/acme-nyc-production-node-onboard.yaml

``` 
**Alternate command**: `./pcdExpress  -portal acme -region nyc  --env production  --create-hostagents-configs yes`


- Run the express tool with the below option to inject the on-prem DU certificates and make the portal accessible from every hosts to be onboarded:
```bash
./pcdExpress -env-file user_configs/acme/nyc/acme-nyc-environment.yaml -onprem yes -ip-addr <vip/extIP> -fqdn <fqdn-region> -fqdninfra <fqdn-infra>
```

* To onboard the host run:
  
```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml --apply-hosts-onboard yes

Triggering node onboarding playbooks..
Using /Users/sarvind/git-local/pcd_ansible/ansible.cfg as config file

PLAY [localhost] ***************************************************************

TASK [Read configuration for requested cloud] **********************************
ok: [localhost] => {"censored": "the output has been hidden due to the fact that 'no_log: true' was specified for this result", "changed": false}

TASK [Find index of cloud name in cloud_config] ********************************
ok: [localhost] => {"censored": "the output has been hidden due to the fact that 'no_log: true' was specified for this result", "changed": false}

TASK [Set the cloud variable] **************************************************
ok: [localhost] => {"censored": "the output has been hidden due to the fact that 'no_log: true' was specified for this result", "changed": false}

PLAY [develop] *****************************************************************

TASK [Get roles for servers] ***************************************************
ok: [172.29.21.227] => {"ansible_facts": {"rolenames": ["node_onboard"]}, "changed": false}

TASK [Include roles for the nodes] *********************************************
included: node_onboard for 172.29.21.227 => (item=node_onboard)

TASK [node_onboard : include_tasks] ********************************************
included: /Users/sarvind/git-local/pcd_ansible/sarvind-play_data/titan/playbooks/roles/node_onboard/tasks/cloud-ctl.yml for 172.29.21.227

TASK [node_onboard : Download latest cloud-ctl] ********************************
ok: [172.29.21.227] => {"ansible_facts": {"discovered_interpreter_python": "/usr/bin/python3.10"}, "changed": false, "checksum_dest": "64cc35b332b26a0cd9dbcdd8f08f729263d31bda", "checksum_src": "64cc35b332b26a0cd9dbcdd8f08f729263d31bda", "dest": "/usr/bin/cloud-ctl", "elapsed": 0, "gid": 1000, "group": "ubuntu", "md5sum": "c401d7a1b4f888d092a3614ddeee2473", "mode": "01363", "msg": "OK (17539224 bytes)", "owner": "ubuntu", "size": 17539224, "src": "/home/ubuntu/.ansible/tmp/ansible-tmp-1738133003.8358028-18062-247412855117050/tmpyfrng0r2", "state": "file", "status_code": 200, "uid": 1000, "url": "https://cloud-ctl.s3.us-west-1.amazonaws.com/cloud-ctl"}

TASK [node_onboard : include_tasks] ********************************************
included: /Users/sarvind/git-local/pcd_ansible/sarvind-play_data/titan/playbooks/roles/node_onboard/tasks/hostagent.yml for 172.29.21.227

TASK [node_onboard : Check for existing host_id] *******************************
ok: [172.29.21.227] => {"changed": false, "stat": {"atime": 1738132008.546754, "attr_flags": "e", "attributes": ["extents"], "block_size": 4096, "blocks": 8, "charset": "us-ascii", "checksum": "7ab717cbd38943e37efa5706bc531aefea95e3f9", "ctime": 1738132007.3027747, "dev": 64513, "device_type": 0, "executable": false, "exists": true, "gid": 1001, "gr_name": "pf9group", "inode": 259221, "isblk": false, "ischr": false, "isdir": false, "isfifo": false, "isgid": false, "islnk": false, "isreg": true, "issock": false, "isuid": false, "mimetype": "text/plain", "mode": "0644", "mtime": 1738132007.3027747, "nlink": 1, "path": "/etc/pf9/host_id.conf", "pw_name": "pf9", "readable": true, "rgrp": true, "roth": true, "rusr": true, "size": 58, "uid": 1001, "version": "4000528697", "wgrp": false, "woth": false, "writeable": true, "wusr": true, "xgrp": false, "xoth": false, "xusr": false}}

TASK [node_onboard : Set Cloud-ctl Config] *************************************
skipping: [172.29.21.227] => {"changed": false, "false_condition": "not host_id_conf.stat.exists", "skip_reason": "Conditional result was False"}

TASK [node_onboard : Prep Node] ************************************************
skipping: [172.29.21.227] => {"changed": false, "false_condition": "not host_id_conf.stat.exists", "skip_reason": "Conditional result was False"}

PLAY RECAP *********************************************************************
172.29.21.227              : ok=6    changed=0    unreachable=0    failed=0    skipped=2    rescued=0    ignored=0
localhost                  : ok=3    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```
**Alternate command**: `./pcdExpress -portal acme -region nyc  --env production  --apply-hosts-onboard yes`
At this point the host should be visible in the  UI in `unauthorized` state which can then be assigned a role to make it operational further. 

The rest of the steps to customise the roles for the hosts will remain the same as of SaaS based deployments.

## Quick command references

### Flags and options
```bash
usage: pcdExpress [-h] [-portal PORTAL] [-region REGION] [-env ENV] [-render-userconfig RENDER_USERCONFIG] [-show-dir SHOW_DIR] [-setup-environment SETUP_ENVIRONMENT]
                  [-create-templates-json CREATE_TEMPLATES_JSON] [-create-blueprints CREATE_BLUEPRINTS] [-apply-blueprints APPLY_BLUEPRINTS] [-create-hostconfigs CREATE_HOSTCONFIGS]
                  [-apply-hostconfigs APPLY_HOSTCONFIGS] [-create-networks-configs CREATE_NETWORKS_CONFIGS] [-apply-networks-configs APPLY_NETWORKS_CONFIGS] [-apply-playbooks-all APPLY_PLAYBOOKS_ALL]
                  [-create-hostagents-configs CREATE_HOSTAGENTS_CONFIGS] [-apply-hosts-onboard APPLY_HOSTS_ONBOARD] [-update-role-config UPDATE_ROLE_CONFIG] [-ostype  OSTYPE] [-env-file  ENV_FILE] [-url  URL]
                  [-deauth-role  DEAUTH_ROLE] [-role  ROLE] [-state  STATE] [-ip  IP] [-onprem  ONPREM] [-ip-addr IP_ADDR] [-fqdn FQDN] [-fqdninfra FQDNINFRA]

Utility to configure PCD and enrol nodes

options:
  -h, --help            show this help message and exit
  -portal PORTAL, --portal PORTAL
                        takes region name as input (REQUIRED) (default: None)
  -region REGION, --region REGION
                        takes site name as input to form DU name. DU=<portal>-<region> (REQUIRED) (default: None)
  -env ENV, --env ENV   takes a string value to segregate hosts in the side. Value: STRING (default: None)
  -render-userconfig RENDER_USERCONFIG, --render-userconfig RENDER_USERCONFIG
                        takes filepath of user config for host onboarding. Value: FILEPATH (default: None)
  -show-dir SHOW_DIR, --show-dir SHOW_DIR
                        to list required dir view of regions sub-dirs. Values: yes|no (default: None)
  -setup-environment SETUP_ENVIRONMENT, --setup-environment SETUP_ENVIRONMENT
                        Setup environment for ansible play exec and management (REQUIRED). Values: yes|no (default: None)
  -create-templates-json CREATE_TEMPLATES_JSON, --create-templates-json CREATE_TEMPLATES_JSON
                        save all userconfig in a json file locally inside jsonsave/directory (OPTIONAL) (default: None)
  -create-blueprints CREATE_BLUEPRINTS, --create-blueprints CREATE_BLUEPRINTS
                        start blueprint template generation. values: yes|no (default: None)
  -apply-blueprints APPLY_BLUEPRINTS, --apply-blueprints APPLY_BLUEPRINTS
                        Deploy the blueprint templates. Values: yes|no (default: None)
  -create-hostconfigs CREATE_HOSTCONFIGS, --create-hostconfigs CREATE_HOSTCONFIGS
                        start hostconfigs template generation Values: yes|no (default: )
  -apply-hostconfigs APPLY_HOSTCONFIGS, --apply-hostconfigs APPLY_HOSTCONFIGS
                        deploy the hostconfigs template. Values: yes|no (default: None)
  -create-networks-configs CREATE_NETWORKS_CONFIGS, --create-networks-configs CREATE_NETWORKS_CONFIGS
                        Create network templates from the user configs Values: yes|no (default: None)
  -apply-networks-configs APPLY_NETWORKS_CONFIGS, --apply-networks-configs APPLY_NETWORKS_CONFIGS
                        Create network templates from the user configs Values: yes|no (default: None)
  -apply-playbooks-all APPLY_PLAYBOOKS_ALL, --apply-playbooks-all APPLY_PLAYBOOKS_ALL
                        Deploy all playbooks with DU name prefix from the playbooks directory. Values: yes|no (default: None)
  -create-hostagents-configs CREATE_HOSTAGENTS_CONFIGS, --create-hostagents-configs CREATE_HOSTAGENTS_CONFIGS
                        Create/render node onboarding playbooks with user input. Values: yes|no (default: None)
  -apply-hosts-onboard APPLY_HOSTS_ONBOARD, --apply-hosts-onboard APPLY_HOSTS_ONBOARD
                        Create/render node onboarding playbooks with user input. Values: yes|no (default: None)
  -update-role-config UPDATE_ROLE_CONFIG, --update-role-config UPDATE_ROLE_CONFIG
                        re-render the templates with updated role details. Values: yes|no (default: None)
  -ostype  OSTYPE, --ostype OSTYPE
                        take input to get os flavor of local environment to setup the ecosystem . Values: mac|ubuntu (default: None)
  -env-file  ENV_FILE, --env-file ENV_FILE
                        provide file containing portal,region and env as yaml . Values: YAML file (default: None)
  -url  URL, --url URL  Set portal URL for blueprint/hostconfigs/network resources (default: None)
  -deauth-role  DEAUTH_ROLE, --deauth-role DEAUTH_ROLE
                        De-authorize/remove a role from specific host or an environment (default: None)
  -role  ROLE, --role ROLE
                        pass role name with -deauth-role argument. Values: hypervisor|image|storage (default: None)
  -state  STATE, --state STATE
                        pass state info of play with -deauth-role argument. Values: absent|present (default: None)
  -ip  IP, --ip IP      pass ip with -deauth-role argument. Values: string (OPTIONAL). env value will take precdence if not provided. (default: None)
  -onprem  ONPREM, --onprem ONPREM
                        select onprem yes|on based. (default: None)
  -ip-addr IP_ADDR, --ip-addr IP_ADDR
                        The IP address to add to /etc/hosts. (default: None)
  -fqdn FQDN, --fqdn FQDN
                        The FQDN of the host. (default: None)
  -fqdninfra FQDNINFRA, --fqdninfra FQDNINFRA
                        The Infra FQDN of the host. (default: None)
```

Before executing any steps, ensure to run the setup-environment command first:
```bash
./pcdExpress -portal acme -region europa -env production -url https://acme-europa.app.staging-pcd.platform9.com/ --setup-environment yes

```

### Blueprint creation and management
**Total steps needed**: **03**
- Modify the blueprint file in `user_configs`
- Run the --create-blueprints command
- Run the --apply-blueprints command 

**Pre-requistes**:
- `user_configs/<portal>/<region>/control_plane/` directory contains the `<portal>-<region>-blueprints-config.yaml` file with required configuration yaml file.

**Create blueprint command**:
```
./pcdExpress  -portal <name> -region <name>  --env staging --create-blueprints yes
```

**Apply blueprint comand:**
```
./pcdExpress  -portal <name> -region <name>  --env staging --apply-blueprints yes
```

**Modifying blueprint**:
- Make the necessary changes in the `<portal>-<region>-blueprints-config.yaml` file under the `user_configs` directory.

- Re-run the `create-blueprints` option followed by the `apply-blueprints` option


**NOTE**:
Once the Roles are assigned to the hypervisor most of the options in blueprint cannot be modified hence running any modified plays will not work. 
Changes are only to be made before the role assignments. 

### Hostconfigs creation and management
**Total steps needed**: **03**
- Modify the hostconfigs file in `user_configs`
- Run the `--create-hostconfigs` command
- Run the `--apply-hostconfigs` command 
  
**Pre-requistes**:
- `user_configs/<portal>/<region>/control_plane/` directory contains the `<portal>-<region>-hosconfigs.yaml` file with required configuration yaml file.

**Create hostconfigs command**:
```
./pcdExpress  -portal <name> -region <name>  --env staging --create-hostconfigs yes
```

**Apply hostconfigs comand:**
```
./pcdExpress  -portal <name> -region <name>  --env staging --apply-hostconfigs yes
```

**Modifying hostconfigs**:
- Make the necessary changes in the `<portal>-<region>-networks-config.yaml` file under the `user_configs` directory.

- Re-run the `create-networks` option followed by the `apply-networks` option

**Deleting current hostconfigs in the existing playbook**

- Go to `<region>-play_data/<site>/playbooks/<region>-hostconfigs_deploy.yaml` and set the specific config value to `absent`

- Run the apply command again:
```
./pcdExpress  -portal <name> -region <name>  --env staging --apply-hostconfigs yes
```
**NOTE**:
- Every interface to be used in the cluster communication should either be labelled or should atleast have one network traffic flow mapped to it for the hostconfigs to be applied successfully for that interface.
- If the hostconfigs resources to be deleted are being consumed, the process will fail with an API error.
- Re-applying the play as it is will not generate any errors. 


### Network creation and management
**Total steps needed**: **03**
- Modify the networks file in `user_configs`
- Run the `--create-networks` command
- Run the `--apply-networks` command 

**Pre-requistes**:
- `user_configs/<portal>/<region>/control_plane/` directory contains the `<portal>-<region>-networks.yaml` file with required configuration yaml file.

**Create networks command**:
```
./pcdExpress  -portal <name> -region <name>  --env staging --create-networks yes
```

**Apply networks comand:**
```
./pcdExpress  -portal <name> -region <name>  --env staging --apply-networks yes
```

**Modifying networks**:
- Make the necessary changes in the `<portal>-<region>-networks-config.yaml` file under the `user_configs` directory.

- Re-run the `create-networks` option followed by the `apply-networks` option

**Deleting current networks in the existing playbook**

- Go to `<region>-play_data/<site>/playbooks/<region>-networks_deploy.yaml` and set the specific config value to `absent`

- Run the apply command again:
```
python3 pcdExpress.py -portal <name> -region <name>  --env staging --apply-networks yes
```

### Onboarding and assigning Roles to nodes For SaaS based deployments
**Total steps needed**: **04**
- Modify the networks file in `user_configs/node_onboarding/`
- Run the `--render-userconfig` command to generate the template file.
- Run the `--create-hostagents-configs` option to create the inventory and playbooks
-  Run the `--apply-hosts-onboard yes` option to apply the playbook for onboarding the hosts

**Pre-requistes**:
- `user_configs/node_onboarding/` directory contains the `nodedata.yaml` file with required configuration yaml file.
- Any changes to nodes data, only this file should be modified

**Render the nodesdata to produce the template yaml file**:
```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml  -render-userconfig user_configs/nodes_onboarding/acme-nyc-nodesdata.yaml
```

**Create  the vars and playbook for the hosts**:
```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml  --create-hostagents-configs yes
```

**Apply the playbook for the nodes**
```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml  -apply-hosts-onboard yes
```

**Modifying nodes**:
- Make the necessary changes in the `nodedata.yaml` file under the `user_configs/region/node-onboarding/` directory.
- Run through the steps in this section to create config,render templates and apply playbooks

### Onboarding and assigning Roles to nodes For On-prem based deployments
**Total steps needed**: **05**
- Modify the networks file in `user_configs/node_onboarding/`
- Run the `--render-userconfig` command to generate the template file.
- Run the `--create-hostagents-configs` option to create the inventory and playbooks
- Run the `-onprem yes -ip-addr <vip/extIP> -fqdn <fqdn-region> -fqdninfra <fqdn-infra>` option to set the certificates on the hosts.
-  Run the `--apply-hosts-onboard yes` option to apply the playbook for onboarding the hosts


**Pre-requistes**:
- The controlplane should be ready and the portal URL should be reachable
- `user_configs/node_onboarding/` directory contains the `nodedata.yaml` file with required configuration yaml file.
- Any changes to nodes data, only this file should be modified

**Render the nodesdata to produce the template yaml file**:
```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml  -render-userconfig user_configs/nodes_onboarding/acme-nyc-nodesdata.yaml
```

**Create  the vars and playbook for the hosts**:
```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml  --create-hostagents-configs yes
```

**Run the express tool with the below option to inject the on-prem DU
certificates:**
```
./pcdExpress -env-file user
configs/acme/nyc/acme-nyc-environment.yaml -onprem yes -ip-addr <vip/extIP> -fqdn <fqdn-region> -fqdninfra <fqdn-infra>
```

**Apply the playbook for the nodes**
```
./pcdExpress  -env-file user_configs/acme/nyc/acme-nyc-environment.yaml  -apply-hosts-onboard yes
```

**Modifying nodes**:
- Make the necessary changes in the `nodedata.yaml` file under the `user_configs/region/node-onboarding/` directory.
- Run through the steps in this section to create config,render templates and apply playbooks


