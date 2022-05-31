# Pruning aged machines automation for OpenShift 4+ cluster

## Abstract

For some OpenShift deployments, with certain business requirements or technical challenges, users may desire to
recreate Machines upon reaching a certain age.
For example, a user may wish to replace Machines once they are older than 7 days.

Replacing the Machines periodically like this may help to ensure that applications are resilient to Node or
infrastructure failures or to standard upgrade procedures in which Machines are cycled frequently.
This article describes an approach to automate this procedure using OpenShift's built-in APIs.

### Introduction

The OpenShift Machine API allows users to manage cluster worker machines by using declarative Kubernetes-style APIs.
As Machines are a Kubernetes-style construct, it is possible to customize and extend lifecycle management using other built-in OpenShift mechanisms as well as external tooling, such as:

- [CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/) / [Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
- [MachineSets](https://docs.openshift.com/container-platform/4.10/machine_management/creating_machinesets/creating-machineset-aws.html#machine-api-overview_creating-machineset-aws)
- [Helm3](https://helm.sh/) for simplify our automation management
- [OpenShift CLI](https://docs.openshift.com/container-platform/4.10/cli_reference/openshift_cli/getting-started-cli.html#cli-getting-started)

This article is intended to describe an approach to manipulating Machines using CronJobs, the `oc` CLI tool, and a bit
of Python scripting.

#### MachineSet

A MachineSet is a group of Machines with the purpose to maintain a stable set of Machines running at any given time.
In other words, if one of the Machines belonging to a MachineSet is deleted, the MachineSet controller will create a
replacement Machine to maintain the desired number of replicas.

#### CronJob / Job

A CronJob creates Jobs on a repeating, user-defined schedule. The Job itself creates a Pod and will continue to retry
the execution of this Pod until it successfully completes.

The main idea of our automation is to invoke OpenShift CLI within a Job's Pod, list Machines, check their age, and mark
old ones for deletion based on the age policy.


### Preparing an example CronJob

To demonstrate this approach, we will make a CronJob that will list and then log all Machines in a cluster, every 5 minutes.
Note, for simplicity of the example, the `default` namespace will be used.

#### Prerequisites

- OpenShift CLI (oc) is installed
- Cluster Admin privileges or Admin privileges over the openshift-machine-api namespace (to create an additional role)

#### Roles and ServiceAccounts

To be able to interact with Machine objects within a cluster, it is necessary to create a Role, appropriate ServiceAccount, and a RoleBinding.

We will need a ServiceAccount to interact with the API server.

```yaml
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: machines-lister
  namespace: default
```  

Since Machine objects are namespaced, an additional role is required in the `openshift-machine-api` namespace.
When necessary, the allowed verbs list may be extended with "delete" and "update". For now, we will restrict this role to read-only permissions.

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

#### OpenShift CLI container image

There are three possible choices for appropriate images to access the OpenShift CLI:

- The [OpenShift CLI image](https://catalog.redhat.com/software/containers/openshift4/ose-cli/5cd9ba3f5a13467289f4d51d) from the RedHat catalog - `registry.redhat.io/openshift4/ose-cli` (recommended as it contains a working Python environment)
- The built-in in-cluster image (check out `oc get imagestreams --all-namespaces | grep cli`) (good for disconnected environments)
- The [origin-cli](https://quay.io/repository/openshift/origin-cli)

Choose whichever image is most readily available for your application.

#### Machine Lister CronJob

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

To retrieve information about the Jobs you can use either the OpenShift web console or the `oc` command-line tool.
Below are some of the useful commands:

* `oc get cronjobs -o wide` - for getting a list of CronJobs
* `oc get jobs -o wide` - for getting list of Jobs
* `oc logs -n default $(oc get pods -n default -l parent=machines-lister --sort-by=.metadata.creationTimestamp -o 'jsonpath={.items[-1].metadata.name}')` - for getting the latest performed Job logs

#### Cleanup

Do not forget to clean up our experiment results:

- `oc delete cronjob machines-lister`
- `oc delete sa machines-lister`
- `oc delete rolebinding machines-lister -n openshift-machine-api`
- `oc delete role machines-lister -n openshift-machine-api`


### Extending the CronJob with more sophisticated logic

To perform more complex actions, it may be necessary to invoke some sort of script in the Job.
This can be done by placing the script code into a ConfigMap or Secret.
This ConfigMap or Secret can then be mounted as a Pod volume for execution within the Job.

To demonstrate this, let's extend the `machine-lister` Job.
The `ose-cli` image contains a Python interpreter and we can use it without any extra setup.

We can create a ConfigMap with a Python program that does the same as the previous example:

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

The CronJob manifest requires some small updates too:

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

The Job's console output should remain the same. This approach allows us to program more sophisticated automation
without the necessity to build a container image and organize its delivery.
However, for complex programs, it would be better to build a separate image,
leveraging Openshift's [BuildConfigs and ImageStreams](https://docs.openshift.com/container-platform/4.10/cicd/builds/understanding-buildconfigs.html)
might be a good way to do this.


### Wrap all into a helm chart

[Helm](https://helm.sh/) is a great tool for managing Kubernetes applications which helps to manage complexity and deal with an application lifecycle
such as installation, deletion, upgrade, and so on.  
Note, that writing charts is a large topic and it would be beneficial to familiarize yourself with the [Helm documentation](https://helm.sh/docs/) beforehand.
In the following section, we will briefly touch on the initial steps of chart development.

We can create a chart with `helm init chart` command, which will scaffold a chart template:

```
chart/
├── .helmignore   # Contains patterns to ignore when packaging Helm charts.
├── Chart.yaml    # Information about your chart
├── values.yaml   # The default values for your templates
├── charts/       # Charts that this chart depends on
└── templates/    # The template files
    └── tests/    # The test files
```

We then need to adjust `Chart.yaml` and `values.yaml` as well as delete the scaffolded templates.
Keep `_helpers.tpl` since it contains a bunch of useful helpers which will help us to prepare a metadata section for our manifests.
Then move the previously prepared CronJob and supporting manifests into the template folder, adjusting the metadata.labels section of each manifest as follows:

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

To make adjustments in a more convenient way, it might make sense to move the automation script out of the ConfigMap template:

```
chart/
├── .helmignore   
├── Chart.yaml    
├── values.yaml   
├── src           # our src assets folder
|    └── machines_lister.py # automation script
└── templates/    # The template files
```

And change `templates/configmap.yaml` by reading ConfigMap data content from the file

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


### Aged Machines pruner

Now that we have prepared a convenient deployment and cleanup procedure, we are ready to write some Python code to
detect old machines and mark them for deletion.

The main idea of this program is to get all Machines with the `oc` tool, in JSON format, check the age of each Machine,
and markn Machines with older than a certain age for deletion.

For brevity, the program source code is separate from this document. However, below are a couple of snippets that describe interactions with  the `oc` tool:

* [Using go templates for customizing oc output](https://cloud.redhat.com/blog/customizing-oc-output-with-go-templates). It would help us to prepare machine-readable output.
* [Python subprocess documentation](https://docs.python.org/3/library/subprocess.html)

Here is an example of how to get and unmarshal Machines into objects within a Python program.
Note that in this example, axillary functionality, such as logging, have been omitted.

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

From here, we can iterate over the `SimpleMachine`s array, check each Machine's age, and mark it for deletion.

The complete program code for aged machines pruning along with a Helm chart can be found in this [Github repository](https://github.com/openshift-cloud-team/aged-machines-pruner/blob/main/aged-machines-pruner/src/main.py).

### Conclusion

As was shown, it is possible to automate a large subset of tasks with CronJobs and simple scripting (using bash, python, or other scripting languages).
Using Helm to organize the development and deployment workflow can also be quite beneficial.

A ready to install chart, with the full version of the pruner program can be found on GitHub: https://github.com/openshift-cloud-team/aged-machines-pruner/

Finally, some additional useful documentation links and materials relevant to this article, for further reading:

- [CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/) / [Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
- [MachineSets](https://docs.openshift.com/container-platform/4.10/machine_management/creating_machinesets/creating-machineset-aws.html#machine-api-overview_creating-machineset-aws)
- [Helm3 docs](https://helm.sh/docs/)
- [OpenShift CLI](https://docs.openshift.com/container-platform/4.10/cli_reference/openshift_cli/getting-started-cli.html#cli-getting-started)
