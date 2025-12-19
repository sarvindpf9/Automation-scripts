# About
The script uses the openstack sdk to connect to the environment and produce a csv file with details of VM name,UUID,interface,security group and its affliated tenant.

# Howto
- Setup the clouds.yaml file in the environment:
```  clouds:
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
- copy and run this script with options like below:
```
get-port-status.py --cloud <name of the region> --output vm-port-state.csv
```
