# pcd_ansible

Ansible collection and playbooks for working with Private Cloud Director

## Setup

### Prerequisites

* Python 3.6+
* Python version manager [pyenv](https://github.com/pyenv/pyenv?tab=readme-ov-file#installation)
* Make

### Install PCD Ansible Collection


All the required dependencies, including the Ansible binaries and PCD Collection, can be installed using the following command:
(Everything will be installed in a virtual environment in the `pyenv` directory.)

```bash
make install_collection
```

### Configure Ansible OpenStack Cloud Plugin

Merge the following configuration into your `~/.config/openstack/clouds.yaml` file or create it if 
it doesn't exist:

```
clouds:
  my_pcd:
    auth:
      auth_url: https://<PCD_FQDN_OF_INFRA_REGION>/keystone/v3
      project_name: <PROJECT|TENANT_NAME> e.g. "service"
      username: <USERNAME>
      password: <PASSWORD>
      user_domain_name: Default
      project_domain_name: Default
    region_name: regionone
    interface: public
    identity_api_version: 3
    compute_api_version: 2
    volume_api_version: 3
    image_api_version: 2
    identity_interface: public
    volume_interface: public
    image_interface: public
```

### Test the connection

To test the openstack cli connection to the PCD API, run the following command:
```bash
openstack --os-cloud my_pcd token issue
```

Additionally, you can test the Ansible connection to the PCD API by running the following command:
```bash
make test_connection
```

## Run the playbooks

### Define a Blueprint

```yaml
---
- hosts: localhost
  connection: local
  become: no
  vars:
    cloud: my_pcd
  gather_facts: false
  tasks:
    - import_tasks: ../tasks/token.yml

    - name: Set default PCD Blueprint Config
      pf9.pcd.blueprint:
        state: present
        mgmt_url: "{{ pcd.prod.url }}"
        token: "{{ hostvars.localhost.keystone_token }}"
        config: "{{ pcd.prod.blueprints.default }}"
```

### Create Hostconfig

```yaml
---
- hosts: localhost
  connection: local
  become: no
  vars:
    cloud: my_pcd
  gather_facts: false
  tasks:
    - import_tasks: ../tasks/token.yml

    - name: Set PCD Host Config
      pf9.pcd.hostconfig:
        state: present
        mgmt_url: "{{ pcd.prod.url }}"
        token: "{{ hostvars.localhost.keystone_token }}"
        config: "{{ pcd.prod.hostconfigs.hypervisor }}"

```

### Create Network

```yaml
---
- hosts: localhost
  connection: local
  become: no
  vars:
    cloud: my_pcd
  gather_facts: false
  tasks:
    - import_tasks: ../tasks/token.yml

    - name: Set PCD Network
      pf9.pcd.network:
        state: present
        mgmt_url: "{{ pcd.prod.url }}"
        token: "{{ hostvars.localhost.keystone_token }}"
        config: "{{ pcd.prod.networks.vmnet5 }}"
```

### Create a Subnet

```yaml
---
- hosts: localhost
  connection: local
  become: no
  vars:
    cloud: my_pcd
  gather_facts: false
  tasks:
    - import_tasks: ../tasks/token.yml

    - name: Set PCD Subnet
      pf9.pcd.subnet:
        state: present
        mgmt_url: "{{ pcd.prod.url }}"
        token: "{{ hostvars.localhost.keystone_token }}"
        config: "{{ pcd.prod.subnets.subnet5 }}"
```
