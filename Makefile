.PHONY: help
help:
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

render-chart: ## render helm chart to _out
	mkdir -p _out
	helm template ./aged-machines-pruner > _out/rendered.yaml

install:  ## install chart
	helm install aged-machines-pruner ./aged-machines-pruner

upgrade:  ## upgrade chart
	helm install aged-machines-pruner ./aged-machines-pruner

delete: ## delete chart
	helm delete aged-machines-pruner