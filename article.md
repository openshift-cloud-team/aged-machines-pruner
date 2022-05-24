# Pruning aged machines automation for OpenShift 4+ cluster 

## Abstract

For some business reasons, it might be needed to recreate Machines upon reaching a certain age, 7 days for example.
It might help to ensure that applications are resilient to node or infrastructure failures.
Also, It helps ensure applications are resilient when underlying nodes go through whatever manipulations.
This article intended to describe an example application which perform aged machines pruning via user-defined cron job which checks machines age and mark aged machines for deletion.


### Introduction 

Openshift built in Machine API allows users to manage cluster's worker (at the moment of writing) machines by using declarative Kubernetes-style APIs.
Due to nature of Machine objects it's quite possible customize and extend lifecycle management using other built in Openshift mechanisms as well as external tooling, such as:

- [CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/) / [Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
- [MachineSets](https://docs.openshift.com/container-platform/4.10/machine_management/creating_machinesets/creating-machineset-aws.html#machine-api-overview_creating-machineset-aws)
- [Helm3](https://helm.sh/) for simplify our automation management 
- [OpenShift CLI](https://docs.openshift.com/container-platform/4.10/cli_reference/openshift_cli/getting-started-cli.html#cli-getting-started)

This article intended to describe an example application which perform aged machines pruning via user-defined cron job which checks machines age and mark aged machines for deletion.

#### MachineSet
A MachineSet it's a group of Machines with purpose to maintain a stable set of Machines running at any given time.
In other words, if one of Machines which belongs to MachineSet was deleted, MachineSet controller will recreate it.

#### CronJob / Job
A CronJob creates Jobs on a repeating, user-defined schedule. Job itself is just create an arbitrary pod and will
continue to retry execution of this pod until it will successfully terminate.

The main idea of our automation is to invoke OpenShift CLI within a Job's pod, list machines, check its age and mark aged one for deletion. 


### Preparing simple CronJob

For demonstrate an approach, in this part we will make a simple cron job which will list all the machines from a cluster to a job logs every 5 minutes.
For simplify our experiments a bit here, `default` namespace will be used. Do not forget to cleanup 

#### Prerequisites
- Openshift CLI (oc) is installed
- Cluster admin privileged (for create additional role in openshift-machine-api namespace)

#### Roles and ServiceAccounts

For being able to interact with Machine objects within a cluster it's necessary to create a Role, appropriate service account and RoleBinding.

We will need a service account for interact with an API server.
```yaml
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: machines-lister
  namespace: default
```  

Since Machine objects are namespaced, additional role is required in `openshift-machine-api` namespace.
```yaml
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: machines-lister
  namespace: openshift-machine-api
rules:
  - apiGroups:
      - machine.openshift.io
    resources:
      - machines
    verbs:
      - get
      - list
      - delete
```

Bind Role to our service account.
```yaml
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: machines-lister
  namespace: openshift-machine-api
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: machines-lister
subjects:
  - kind: ServiceAccount
    name: machines-lister
    namespace: default
```

#### OpenShift CLI container image image

I would advise to use the [Openshift CLI image](https://catalog.redhat.com/software/containers/openshift4/ose-cli/5cd9ba3f5a13467289f4d51d) from the RedHat catalog - `registry.redhat.io/openshift4/ose-cli`.
However, built in in-cluster image or [origin-cli](https://quay.io/repository/openshift/origin-cli) one will be suitable too. 


#### Simple Machines Lister CronJob

Lets write a simple CronJob manifest:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: machines-lister
spec:
  schedule: "*/5 * * * *"
  concurrencyPolicy: "Forbid"
  startingDeadlineSeconds: 30
  suspend: false
  successfulJobsHistoryLimit: 2
  failedJobsHistoryLimit: 2
  jobTemplate:
    spec:
      template:
        metadata:
          labels:
            parent: machines-lister # needed for obtain latest job logs
        spec:
          restartPolicy: Never
          serviceAccountName: machines-lister
          containers:
            - name: machines-lister
              image: registry.redhat.io/openshift4/ose-cli:v4.10
              imagePullPolicy: IfNotPresent
              command: ["oc", "get", "machines", "-n", "openshift-machine-api", "-o", "wide"]
```

For getting information about the jobs you can use either Openshfit web console or `oc` command line tool, here is some of a useful commands:

* `oc get cronjobs -o wide` - for getting list of cronjobs
* `oc get jobs -o wide` - for getting list of jobs
* `oc logs -n default $(oc get pods -n default -l parent=machines-lister --sort-by=.metadata.creationTimestamp -o 'jsonpath={.items[-1].metadata.name}')` - for getting the latest performed job logs


------------