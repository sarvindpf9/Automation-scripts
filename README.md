### Howto Use this script?

#### 02-deploy-instance_E2E
This sample can do following things:
- Deploy independent images to glance based on user inputs and uses that to deploy the actual instance  
- Deploy networks and subnet and attach to instance
- Deploy single nova instance
- Deploy independent cinder volume and attach to the instance
- The cinder and image can be individually  excluded/included with apply command.

Steps to execute:
- Ensure `opentofu` packages are installed on the host and the host has access to the PCD environment. 
- Ensure latest python3-openstackclient and python3-octaviaclient packages are installed:
```bash
sudo apt-get install python3-openstackclient python3-octaviaclient -y
```
- Download the required directory locally host.
- From inside the directory, run:
```bash
tofu init
```
- Configure the `testdeploy.tfvars` file to have the necessary openstack auth configuration along with image and  glance config:
```bash
openstack_user_name = "<User-name>"
openstack_tenant_name = "<tenant_name>"
openstack_password = "<password>"
openstack_auth_url = "https://portal_url/keystone/v3"
openstack_region = "<region_name>"
image_name = "<name_of_the_image_available>"
flavor_name = "<flavor_name_available>"
glance_image_name = "<name_of_the_image_to_be_uploaded>"

```
- Copy the required glance image inside this directory.
- Run plan and apply command with tofu. To include volume and image deployment:
```bash
tofu  plan  -var-file testdeploy.tfvars -var="deploy_image=true" -var="deploy_volume=true"
tofu  apply  -var-file testdeploy.tfvars -var="deploy_image=true" -var="deploy_volume=true" 
```
Type `yes` for the apply action. 
- To deploy without image or volume creation test:
```bash
tofu  plan  -var-file testdeploy.tfvars 
tofu  apply  -var-file testdeploy.tfvars 
```