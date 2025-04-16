### Howto Use this script?

#### 02-ansible_scripts/01-example_instance_E2E
This sample can do following things:
- Deploy independent images to glance
- Deploy networks and subnet as a fresh
- Deploy single nova instance with boot from Volume  backend


Steps to execute:
- Install ansible packages: `sudo apt-get install ansible`
- Install ansible provider/collections: `ansible-galaxy collection install openstack.cloud`
- Install/update the openstacksdk packages: `pip3 install --upgrade openstacksdk`
- Configure the local `clouds.yaml` file with the required credentials of the cloud. Ensure there is one profile for admin and one for public interface:
```bash
cat /home/ubuntu/.config/openstack/clouds.yaml
clouds:
  sa-demo_public:
    auth:
      auth_url: https://<DU-URL>/keystone/v3
      username: ""
      password: ""
      project_name: "service"
      user_domain_name: "Default"
      project_domain_name: "Default"
    region_name: "region2"
    identity_api_version: 3
    interface: "public"
    verify: false
  sa-demo_admin:
    auth:
      auth_url: https://<DU-URL>/keystone/v3
      username: ""
      password: ""
      project_name: "service"
      user_domain_name: "Default"
      project_domain_name: "Default"
    region_name: "region2"
    identity_api_version: 3
    interface: admin
    verify: false
```
- From inside this example directory trigger the deployment action with:
```bash
ansible-playbook -i inventory.yaml  Deploy_instance_e2e.yaml -e network=test-net -e subnet=subnet -e state=present -v
```
- To remove all the resources after test RUn the delete resource playbook:
```bash
 ansible-playbook -i inventory.yaml  remove_instance.yml -e network=test-net -e subnet=subnet -e state=absent  -v
```
