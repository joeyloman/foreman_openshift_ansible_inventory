# Foreman OpenShift Ansible Inventory


This script can be used as an Ansible dynamic inventory[1] for OpenShift installations.
The connection parameters are set up via a configuration
file *foreman.ini*. *foreman.ini* is found using the following
order of discovery.

    * `/etc/ansible/foreman.ini`
    * Current directory of your inventory script.
    * `FOREMAN_INI_PATH` environment variable.

## Variables and Parameters

The data returned from Foreman for each host with a "openshift-role" host parameter is stored in a OpenShift ansible inventory group structure. The groupnames are created from the "openshift-role" comma seperated values, for example: openshift-role=masters,etcd,nodes


    {
      "_meta": {
        "hostvars": {
          "openshift-master1.example.com": {
            "kt_activation_keys": "openshift-example", 
            "openshift-role": "masters,etcd,nodes", 
            "region": "infra", 
            "zone": "default"
          }, 
          "openshift-master2.example.com": {
            "kt_activation_keys": "openshift-example", 
            "openshift-role": "masters,etcd,nodes", 
            "region": "infra", 
            "zone": "default"
          }, 
          "openshift-master3.example.com": {
            "kt_activation_keys": "openshift-example", 
            "openshift-role": "masters,etcd,nodes", 
            "region": "infra", 
            "zone": "default"
          }, 
          "openshift-node1.example.com": {
            "kt_activation_keys": "openshift-example", 
            "openshift-role": "nodes", 
            "region": "infra", 
            "zone": "default"
          }, 
          "openshift-node2.example.com": {
            "kt_activation_keys": "openshift-example", 
            "openshift-role": "nodes", 
            "region": "infra", 
            "zone": "default"
          }
        }
      }, 
      "etcd": [
        "openshift-master1.example.com", 
        "openshift-master2.example.com", 
        "openshift-master3.example.com"
      ], 
      "masters": [
        "openshift-master1.example.com", 
        "openshift-master2.example.com", 
        "openshift-master3.example.com"
      ], 
      "nodes": [
        "openshift-master1.example.com", 
        "openshift-master2.example.com", 
        "openshift-master3.example.com", 
        "openshift-node1.example.com", 
        "openshift-node2.example.com"
      ]
    }


[1]: http://docs.ansible.com/intro_dynamic_inventory.html

