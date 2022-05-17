import os
import subprocess, json, sys, tempfile, datetime, logging
from distutils import util
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
MACHINE_MAX_AGE_HOURS = float(os.environ.get("MACHINE_MAX_AGE_HOURS", 168))  # 7 days
DRY_RUN = util.strtobool(os.getenv("DRY_RUN", 'true'))
DEFAULT_FILTER_LABELS = (
    "machine.openshift.io/cluster-api-machine-type=worker",
    "machine.openshift.io/cluster-api-machine-role=worker"
)
ADDITIONAL_FILTER_LABELS = tuple((label for label in os.getenv("ADDITIONAL_LABELS", "").split(",") if label))
FILTER_LABELS = DEFAULT_FILTER_LABELS + ADDITIONAL_FILTER_LABELS
MAX_DELETING_AT_ONCE = int(os.getenv("MAX_DELETING_AT_ONCE", 1))

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format='%(asctime)s %(levelname)-8s %(message)s')
log = logging.getLogger("aged-machines-pruner")


class SimpleMachine:
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
    log.info("Trying to get machines via OC")
    with tempfile.NamedTemporaryFile(mode="w", suffix="gotmpl", encoding="UTF-8", delete=False) as tmp:
        tmp.write(MACHINES_GO_TEMPLATE)
    machines_result = subprocess.run([
        "oc",
        "get",
        "machines",
        "-n", "openshift-machine-api",
        "-l",
        f"{','.join(DEFAULT_FILTER_LABELS + ADDITIONAL_FILTER_LABELS)}",
        "-o", f"go-template-file={tmp.name}"
    ], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if machines_result.returncode != 0:
        log_subprocess_err(machines_result)
        exit(1)
    machines = json.loads(machines_result.stdout, object_hook=lambda x: SimpleMachine(**x))
    log.info(f"{len(machines)} worker machines found")
    return machines


def filter_machines(machines: List[SimpleMachine]) -> List[SimpleMachine]:
    deleting_machines = list(filter(lambda machine: machine.phase == "Deleting", machines))
    if deleting_machines:
        log.info(f"Machines in deleting phase: {[m.name for m in deleting_machines]}, Total: {len(deleting_machines)}")
        if len(deleting_machines) >= MAX_DELETING_AT_ONCE:
            log.info("Deleting machines limit exhausted, nothing would be mark for deletion")
            return []
    else:
        log.info("No machines in deleting phase")

    to_delete = list(filter(
        lambda machine: machine.age_hours > MACHINE_MAX_AGE_HOURS and machine.phase == "Running",
        machines
    ))
    log.info(f"{len(to_delete)} machines found for deletion. It's number will be limited with {MAX_DELETING_AT_ONCE}")
    return to_delete[:MAX_DELETING_AT_ONCE]


def delete_machines(machines: List[SimpleMachine]):
    if machines:
        log.info(f"Try delete machines: {', '.join([m.name for m in machines])}")
        log.info(f"DRY_RUN is {DRY_RUN}")
        for machine in machines:
            log.info(f"Trying delete {machine.name}")
            args = [
                "oc",
                "delete",
                "machine",
                f"{machine.name}",
                "-n", "openshift-machine-api",
                "--wait=false",
            ]
            if DRY_RUN:
                args.append("--dry-run=client")
            delete_result = subprocess.run(args, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if delete_result.returncode != 0:
                log_subprocess_err(delete_result)
                exit(1)
    else:
        log.info("No machines marked for deletion")


def log_settings():
    log.info(f""" 
    Run parameters:
        Max machine age in hours: {MACHINE_MAX_AGE_HOURS}
        Max machines allowed in deleting phase allowed: {MAX_DELETING_AT_ONCE}   
        Filter labels: {', '.join(DEFAULT_FILTER_LABELS + ADDITIONAL_FILTER_LABELS)}
        Deletion dry run: {DRY_RUN}""")


def log_subprocess_err(process: subprocess.CompletedProcess):
    log.error(f"""
    OC command finished with non zero return code:
        COMMAND: {subprocess.list2cmdline(process.args)}
        STDOUT:{str(process.stdout)}
        STDERR:{str(process.stderr)}
        CODE:{process.returncode}""")


if __name__ == '__main__':
    log_settings()
    delete_machines(
        filter_machines(get_machines())
    )
