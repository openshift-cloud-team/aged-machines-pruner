# Issue
For some business reasons, it might be needed to recreate Machines upon reaching a certain age, 7 days for example

# Resolution

This task might be performed by setting up a
[cron-job](https://www.redhat.com/sysadmin/create-kubernetes-cron-job-okd) which will run a program checking machines' age
and asking openshift to delete machines that reached a certain age.

To simplify such cron job deployment and its further life cycle management it's reasonable to use a helm chart there.
Working helm chart with a simple python program might be found on Github in [openshift-cloud-team/aged-machines-pruner](https://github.com/openshift-cloud-team/aged-machines-pruner).

Prerequisites for [openshift-cloud-team/aged-machines-pruner](https://github.com/openshift-cloud-team/aged-machines-pruner) usage:

* Helm 3 is installed. Installation guide: https://helm.sh/docs/intro/install/
* Administrative access to OpenShift cluster for being able to add additional roles into the `openhsift-machine-api` namespace.

Installation:

Option 1:

* Clone [openshift-cloud-team/aged-machines-pruner](https://github.com/openshift-cloud-team/aged-machines-pruner) repo
* Run `make install` for install helm chart

Note: By default, the chart is installed in DRY_RUN mode, machines will not be deleted. To enable actual machines deletion
run `make disable-dry-run`

Option 2:
// TODO prepare helm repo there