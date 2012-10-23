.PHONY: build check install doc dist rpm_sources srpm rpm clean

PROJECT := psh
PYTHON := python
TEST_ENV_PATH := test-env
CHECK_PYTHON_VERSIONS := 2 3
RPM_SOURCES_PATH := ~/rpmbuild/SOURCES

build:
	$(PYTHON) setup.py build

check:
	@mkdir -p "$(TEST_ENV_PATH)"
	@set -e; for version in $(CHECK_PYTHON_VERSIONS); do \
		echo; echo "Testing $(PROJECT) with python$$version..."; echo; \
		env_path="$(TEST_ENV_PATH)/python$$version"; \
		if [ ! -e "$$env_path" ]; then \
			virtualenv --python python$$version --distribute "$$env_path" && \
				"$$env_path/bin/pip" install pytest || { rm -rf "$$env_path"; false; }; \
		fi; \
		"$$env_path/bin/python" setup.py test; \
	done

install:
	$(PYTHON) setup.py install

doc:
	make -C doc html

dist: clean
	$(PYTHON) setup.py sdist

rpm_sources: dist
	cp dist/* $(RPM_SOURCES_PATH)/

srpm: rpm_sources
	rpmbuild -bs python-$(PROJECT).spec

rpm: rpm_sources
	rpmbuild -ba python-$(PROJECT).spec

pypi: clean
	$(PYTHON) setup.py sdist upload

clean:
	@make -C doc clean
	rm -rf build dist $(PROJECT).egg-info $(TEST_ENV_PATH)
