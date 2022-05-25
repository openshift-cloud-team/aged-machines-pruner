# Pruning aged machines automation for OpenShift 4+ cluster

## Abstract

For some business reasons, it might be needed to recreate Machines upon reaching a certain age, 7 days for example.
It might help to ensure that applications are resilient to node or infrastructure failures.
Also, It helps ensure applications are resilient when underlying nodes go through whatever manipulations.
This article intended to describe an approach to make such automation using Openshift's built-in APIs, such as CronJobs.

### Introduction

Openshift built-in Machine API allows users to manage cluster's worker (at the moment of writing) machines by using declarative Kubernetes-style APIs.
Due to the nature of Machine objects, it's quite possible to customize and extend lifecycle management using other built-in Openshift mechanisms as well as external tooling, such as:

- [CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/) / [Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
- [MachineSets](https://docs.openshift.com/container-platform/4.10/machine_management/creating_machinesets/creating-machineset-aws.html#machine-api-overview_creating-machineset-aws)
- [Helm3](https://helm.sh/) for simplify our automation management
- [OpenShift CLI](https://docs.openshift.com/container-platform/4.10/cli_reference/openshift_cli/getting-started-cli.html#cli-getting-started)

This article intended to describe an approach to manipulating machines using CronJobs and `oc` CLI tool and a bit of python scripting.

#### MachineSet
A MachineSet it's a group of Machines with the purpose to maintain a stable set of Machines running at any given time.
In other words, if one of the Machines which belongs to MachineSet was deleted, the MachineSet controller will recreate it.

#### CronJob / Job
A CronJob creates Jobs on a repeating, user-defined schedule. The job itself is just creating an arbitrary pod and will
continue to retry the execution of this pod until it will successfully terminate.

The main idea of our automation is to invoke OpenShift CLI within a Job's pod, list machines, check their age, and mark aged ones for deletion.


### Preparing simple CronJob

To demonstrate an approach, in this part we will make a simple cron job that will list all the machines from a cluster to a job log every 5 minutes.
To simplify our experiments a bit here, the `default` namespace will be used.

#### Prerequisites
- Openshift CLI (oc) is installed
- Cluster admin privileged (for create additional role in openshift-machine-api namespace)

#### Roles and ServiceAccounts

For being able to interact with Machine objects within a cluster it's necessary to create a Role, appropriate service account, and RoleBinding.

We will need a service account to interact with an API server.
```yaml
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: machines-lister
  namespace: default
```  

Since Machine objects are namespaced, an additional role is required in the `openshift-machine-api` namespace.
When necessary verbs list might be extended with "delete" and "edit". Now we will restrict this role with read-only permissions.
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
```

Bind the role to our service account.
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
However, built-in in-cluster image (check out `oc get imagestreams --all-namespaces | grep cli`) or [origin-cli](https://quay.io/repository/openshift/origin-cli) one will be suitable too.

#### Simple Machines Lister CronJob

Let's write a simple CronJob manifest:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: machines-lister
spec:
  schedule: "*/5 * * * *"
  concurrencyPolicy: "Forbid" # Forbid concurrency since we need only one instance of this running at a time
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
              command: ["oc", "get", "machines.machine.openshift.io", "-n", "openshift-machine-api", "-o", "wide"]
```

For getting information about the jobs you can use either Openshfit web console or the `oc` command-line tool, here are some of the useful commands:

* `oc get cronjobs -o wide` - for getting list of cronjobs
* `oc get jobs -o wide` - for getting list of jobs
* `oc logs -n default $(oc get pods -n default -l parent=machines-lister --sort-by=.metadata.creationTimestamp -o 'jsonpath={.items[-1].metadata.name}')` - for getting the latest performed job logs

#### Cleanup

Do not forget to clean up our experiment results:

- `oc delete cronjob machines-lister`
- `oc delete sa machines-lister`
- `oc delete rolebinding machines-lister -n openshift-machine-api`
- `oc delete role machines-lister -n openshift-machine-api`


### Extending CronJob with more sophisticated logic

For a bit more complex automation it might be necessary to invoke some sort of script in our job.
This might be done by putting script code into ConfigMap or Secret, mounting it as pod volume with further execution.

To demonstrate this let's extend our `machine-lister` thingy a bit. Luckily `ose-cli` image contains a Python interpreter
and we can use it without any extra manipulations.

ConfigMap with a python program that does the same as the previous example:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: machines-lister-script
data:
  machines_lister.py: |
    import subprocess
    if __name__ == '__main__':
      subprocess.run(
        ["oc", "get", "machines.machine.openshift.io", "-n", "openshift-machine-api", "-o", "wide"]
      )
```

Updated CronJob manifest:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: machines-lister
spec:
  schedule: "*/5 * * * *"
  concurrencyPolicy: "Forbid" # Forbid concurrency since we need only one instance of this running at a time
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
              command: ["python", "/opt/machines_lister.py"]
              volumeMounts:
              - name: machines-lister-script
                mountPath: /opt
          volumes:
            - name: machines-lister-script
              configMap:
                name: machines-lister-script
```

Jobs console output should remain the same. This approach would allow us to program more sophisticated automation
without the necessity to build a container image and organize its delivery.
However, for complex programs, it would be better to build a separate image,
leveraging Openshift's [BuildConfigs and ImageStreams](https://docs.openshift.com/container-platform/4.10/cicd/builds/understanding-buildconfigs.html)
might be a good way to do this.


### Wrap all into a helm chart

[Helm](https://helm.sh/) is a great tool for managing Kubernetes applications which helps to manage complexity and deal with an application lifecycle
such as installation, deletion, upgrade, and so on.  
Note, that charts writing is a quite large topic and it would be reasonable to familiarize yourself with [Helm documentation](https://helm.sh/docs/) beforehand.
Here I would just briefly touch initial steps of chart development.

You could create a chart with `helm init chart` command, which will scaffold a chart template for you:

```
chart/
├── .helmignore   # Contains patterns to ignore when packaging Helm charts.
├── Chart.yaml    # Information about your chart
├── values.yaml   # The default values for your templates
├── charts/       # Charts that this chart depends on
└── templates/    # The template files
    └── tests/    # The test files
```

You'll need to adjust `Chart.yaml` and `values.yaml` as well as delete scaffolded templates.
Keep `_helpers.tpl` since it contains a bunch of useful helpers which will help us to prepare a metadata section for our manifests.
Then you could move your manifests into the template folder with adjusting metadata.labels section of each manifest as follows.

```yaml
...
metadata:
...
  labels:
    {{- include "chart.labels" . | nindent 4 }} # this will include Helm related labels which it uses for chart resources lookup
...
```

Results should look somewhat like this:

```
chart/
├── .helmignore   # Contains patterns to ignore when packaging Helm charts.
├── Chart.yaml    # Information about your chart
├── values.yaml   # The default values for your templates
└── templates/    # The template files
    ├── _helpers.tpl
    ├── configmap.yaml
    ├── cronjob.yaml
    ├── roles.yaml
    ├── serviceaccount.yaml
    └── NOTES.txt
```

For making adjustments in a more convenient way it might make sense to move out automation script out of the configmap template:

```
chart/
├── .helmignore   
├── Chart.yaml    
├── values.yaml   
├── src           # our src assets folder
|    └── machines_lister.py # automation script
└── templates/    # The template files
```

And change `templates/configmap.yaml` by reading configmap data content from the file

```yaml templates/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: machines-lister-script
  labels:
    {{- include "chart.labels" . | nindent 4 }}
data:
  machines-lister.py: |
    {{ $.Files.Get "src/machines_lister.py" | nindent 4 }}
```

Now we can install/upgrade/delete our chart with helm:

- `helm install machines-lister ./chart` for chart installation
- `helm uninstall machines lister` for chart deletion


### Aged machines pruner

Now when we are managed to prepare a convenient deploy/cleanup procedure, we are ready to write some python code which
will detect aged machines and mark them for deletion.

The main idea of this program is to get all machines with `oc` tool in JSON format, check the age of each machine, and mark
machines with certain age for deletion.

I won't put there a whole program code, but want to show a couple of pieces that describe an interaction with `oc` tool:

* [Using go templates for customizing oc output](https://cloud.redhat.com/blog/customizing-oc-output-with-go-templates). It would help us to prepare machine-readable output.
* [Python subprocess documentation](https://docs.python.org/3/library/subprocess.html)


Here is an example of how to get and unmarshal machine into objects within a python program.
Note that in this example bunch of axillary things, such as logging, were omitted.

```python
import subprocess, json, tempfile, datetime
from typing import List

MACHINES_GO_TEMPLATE = """
[{{- range $i, $machine := .items -}}
{{if $i}},{{end}}
{
    "name": "{{$machine.metadata.name}}",
    "created": "{{$machine.metadata.creationTimestamp}}",
    "phase": "{{$machine.status.phase}}"
}
{{- end -}}]
"""

class SimpleMachine:
    """
    Intended for unmarshalling `oc get` results into it. Represents a single machine.
    """
    name: str
    created: datetime.datetime
    phase: str
    
    def __init__(self, name: str, created: str, phase: str):
        self.name = name
        self.created = datetime.datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ")
        self.phase = phase

    @property
    def age_hours(self):
        return (datetime.datetime.utcnow() - self.created).seconds / 3600
        
    
def get_machines() -> List[SimpleMachine]:
    print("Trying to get machines via OC")
    with tempfile.NamedTemporaryFile(mode="w", suffix="gotmpl", encoding="UTF-8", delete=False) as tmp:
        tmp.write(MACHINES_GO_TEMPLATE)
    machines_result = subprocess.run([
        "oc",
        "get",
        "machines",
        "-n", "openshift-machine-api",
        "-o", f"go-template-file={tmp.name}"
    ], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if machines_result.returncode != 0:
        print(machines_result)
        exit(1)
    machines = json.loads(machines_result.stdout, object_hook=lambda x: SimpleMachine(**x))
    print(f"{len(machines)} worker machines found")
    return machines
```

Then, it should be quite straightforward to iterate over `SimpleMachine`s array, check each machine's age, and mark it for deletion.

Entire program code for aged machines pruning along with a Helm chart might be found in [Github repository](https://github.com/openshift-cloud-team/aged-machines-pruner/blob/main/aged-machines-pruner/src/main.py).

### Conclusion

As was shown it is quite possible to automate a quite large subset of tasks with CronJobs and simple scripting (using bash, python, or other scripting languages).
Using Helm to organize development and deployment workflow is also quite beneficial.

Ready to install chart with the full version of the pruner program might be found on GitHub: https://github.com/openshift-cloud-team/aged-machines-pruner/

Some useful documentation links and materials for further reading: 

- [CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/) / [Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
- [MachineSets](https://docs.openshift.com/container-platform/4.10/machine_management/creating_machinesets/creating-machineset-aws.html#machine-api-overview_creating-machineset-aws)
- [Helm3 docs](https://helm.sh/docs/)
- [OpenShift CLI](https://docs.openshift.com/container-platform/4.10/cli_reference/openshift_cli/getting-started-cli.html#cli-getting-started)