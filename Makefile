.PHONY: help
help:
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

render-chart: ## render helm chart to _out for further review
	mkdir -p _out
	helm template ./aged-machines-pruner --debug > _out/rendered.yaml

install:  ## install chart
	helm install aged-machines-pruner ./aged-machines-pruner --namespace aged-machines-pruner --create-namespace

upgrade:  ## upgrade chart
	helm upgrade aged-machines-pruner ./aged-machines-pruner --namespace aged-machines-pruner

disable-dry-run: ## upgrades chart with disabled dry-run mode
	helm upgrade aged-machines-pruner ./aged-machines-pruner --namespace aged-machines-pruner --set agedMachinesPruner.DRY_RUN=0

enable-dry-run: ## upgrades chart with enabled dry-run mode
	helm upgrade aged-machines-pruner ./aged-machines-pruner --namespace aged-machines-pruner --set agedMachinesPruner.DRY_RUN=1

delete: ## delete chart
	helm delete aged-machines-pruner --namespace aged-machines-pruner