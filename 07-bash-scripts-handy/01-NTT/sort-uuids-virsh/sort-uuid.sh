#!/usr/bin/env bash
set -euo pipefail

xml_uuids=$(ls /etc/libvirt/qemu/*.xml 2>/dev/null | xargs -I{} basename {} .xml | sort)
virsh_names=$(virsh list --all --name 2>/dev/null | grep -v '^$' | sort)

only_xml=$(comm -23 <(echo "$xml_uuids") <(echo "$virsh_names"))
only_virsh=$(comm -13 <(echo "$xml_uuids") <(echo "$virsh_names"))

[[ -n "$only_xml" ]]   && echo -e "=== XML only (no virsh entry) ===\n$only_xml"
[[ -n "$only_virsh" ]] && echo -e "=== virsh only (no XML file) ===\n$only_virsh"
[[ -z "$only_xml" && -z "$only_virsh" ]] && echo "No differences."

xml_count=$(echo "$xml_uuids" | grep -c .)
virsh_count=$(echo "$virsh_names" | grep -c .)
echo -e "\n=== Totals ===\nnum_vm_configs_local    $xml_count\ntotal_vms_virsh:        $virsh_count"


