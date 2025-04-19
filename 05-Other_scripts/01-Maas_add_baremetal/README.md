## Summary

This script helps automate the process of enrolling baremetals into MaaS and onboard them to the PCD environment

## How to use?

- Download the script locally.
- Create/modify the required cloud-init file inside `cloud-inits/` directory.
  - Ensure the name of the cloud-init file has the desired host name as suffix e.g `test-host1_cloud-init.yaml`, `test-host2_cloud-init.yaml` etc.
- Create a `hardware-config.csv` by copying the sample file provided and add the host details to it:
```bash
hostname,architecture,mac_addresses,power_type,power_user,power_pass,power_driver,power_address,cipher_suite_id,power_boot_type,privilege_level,k_g,cloud_init_path
haas-bm-03,amd64,3c:ec:ef:5f:5e:00,ipmi,ADMIN,Platform9,LAN_2_0,192.168.100.4,3,efi,ADMIN,"",cloud-inits/haas-bm-03_cloud-init.yaml
haas-bm-04,amd64,3c:ec:ef:1c:df:3e,ipmi,ADMIN,Platform9,LAN_2_0,192.168.100.5,3,efi,ADMIN,"",cloud-inits/haas-bm-04_cloud-init.yaml
```
- Login through command line into MaaS using the api-key:
```bash
maas login admin http://10.10.62.254:5240/MAAS/ < $(sudo maas apikey --username=admin)
```
- Execute the `add-baremetal.py` script with:
```bash
python3 add_baremetal.py --maas-user admin --csv-file hardware-config.csv
```

There will a `deploy_logs` directory created which will contain a timestamped log file for the log capturing.