PCD_COLLECTION_VERSION = $(shell awk -F" " '/^version:/{print $$2}' ansible-collections-pf9/galaxy.yml)

setup_pyenv:
	@echo "Building virtualenv"
	python3 -m venv pyenv

install_deps: setup_pyenv
	@echo "Installing dependencies"
	. pyenv/bin/activate && pip install -r ./ansible-collections-pf9/requirements.txt
	. pyenv/bin/activate && ansible-galaxy collection install -r ./ansible-collections-pf9/requirements.yml --force

build_collection: install_deps
	@echo "Building PCD ansible collection"
	. pyenv/bin/activate && ansible-galaxy collection build -v ./ansible-collections-pf9 --force

install_collection: build_collection
	@echo "Installing PCD ansible collection"
	. pyenv/bin/activate && ansible-galaxy collection install -v ./pf9-pcd-$(PCD_COLLECTION_VERSION).tar.gz -p ./collections --upgrade

test_connection:
	@echo "Testing token auth"
	. pyenv/bin/activate && ansible-playbook -i inventory/hosts ./playbooks/test-token-retrieval.yml -v

lint:
	@echo "Linting"
	. pyenv/bin/activate && ruff check

deploy_hostagent:
	@echo "Deploying host agent"
	. pyenv/bin/activate && ansible-playbook -i inventory/hosts ./playbooks/examples/deploy-hostagent.yml -vv
