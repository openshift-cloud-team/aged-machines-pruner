# Aged machines pruner

This repo contains Openshift specific helm chart for automating the deletion of worker machines that did hit a certain age.

## Description
For some  reasons, it might be needed to recreate Machines upon reaching a certain age, 7 days for example

This task might be performed by setting up a
[cron-job](https://www.redhat.com/sysadmin/create-kubernetes-cron-job-okd) which will run a program checking machines' age
and asking openshift to delete machines that reached a certain age.

To simplify such cron job deployment and its further life cycle management it's reasonable to use a helm chart there.

The main logic of this program lives [within](aged-machines-pruner/src/main.py) the helm chart
and passes to the container as a config map for further execution.
This program requires `oc`(openshift-cli) binary presence in PATH and Python 3.6+.

## Usage
### Prerequisites

* Helm 3 is installed. Installation guide: https://helm.sh/docs/intro/install/
* Administrative access to OpenShift cluster for being able to add additional roles into the `openhsift-machine-api` namespace.

### Installation:

* Clone this repo
* Run `make install` for install helm chart

Note: By default, the chart is installed in DRY_RUN mode, machines will not be deleted. To enable actual machines deletion
run `make disable-dry-run`
