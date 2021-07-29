# Ansible Package Driver Flow
1. Receive JSON payload request for Ansible Execution - Either from Quali Server or 2G Service
2. Run Sanity check that Ansible is installed on ES by running "ansible --version" command. Throw Exception if not.
3. Parse JSON request into configuration object
4. Merge global inputs into app parameters - existing app level params over-ride globals
5. Run lookup operation to get resource name of target hosts from their IPs
    - Ideally the server should provide the resource name with the JSON request
    - The resource name is needed to set live status of resources in real time
    - Setting live status in driver instead of the server because the server does this incorrectly
        - sets the same failed message for ALL hosts in playbook list, even though we have the detailed failed info in hand in AnsibleResult object
6. Download playbook from repo. If this fails end driver with Exception.
7. Poll device connectivity of host list. Tag failed hosts with failed status on the config object
    - If ALL hosts in host list fail connectity check, throw exception and stop driver
    - For devices that failed connectivity check, they wont be added to ansible host list
8. Create Ansible files necessary for Execution
    - Ansible.cfg - local ansible.cfg that merges global cfg file
    - Inventory file - adding all host members in playbook request - assigning to inventory groups as defined on app
    - Host vars files - one for each member of host list
9. Run playbook, return result file with parsed results per host
10. Set Live status for each host
11. If failed hosts exist, post json report to Sandbox Data for setup script to later read from
12. Return Pass / Fail string result from driver