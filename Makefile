tag=duckietown.sdk
PYTHON ?= python3
TEST_WORKERS ?= 8
PYTEST_ARGS ?=
export PYTHONPATH := $(CURDIR)/src$(if $(PYTHONPATH),:$(PYTHONPATH))

regular_packages=duckietown.sdk
test_packages=duckietown_sdk_tests
cover_packages=$(test_packages),$(regular_packages)


CIRCLE_NODE_INDEX ?= 0
CIRCLE_NODE_TOTAL ?= 1

out=out
coverage_dir=$(out)/coverage
tr=$(out)/test-results
xunit_output=$(tr)/pytest-$(CIRCLE_NODE_INDEX)-xunit.xml


test_files=src/duckietown_sdk_tests/test_world_sessions.py \
	src/duckietown_sdk_tests/test_shm_transport.py
coverage=--cov=$(regular_packages) --cov-branch --cov-report=term-missing --cov-report=html:$(coverage_dir)
pytest=$(PYTHON) -W default -m pytest $(test_files) -v $(coverage) --junitxml=$(xunit_output) $(PYTEST_ARGS)



all:
	@echo "You can try:"
	@echo
	@echo "  make build run"
	@echo "  make docs "
	@echo "  make test coverage-combine coverage-report"
	@echo "  "
	@echo "  make -C notebooks clean all"



black:
	black -l 110 --target-version py312 src

clean:
	$(PYTHON) -m coverage erase
	rm -rf $(out) $(coverage_dir) $(tr)

test: clean
	mkdir -p  $(tr)
	DISABLE_CONTRACTS=1 $(pytest)


test-parallel: clean
	mkdir -p  $(tr)
	DISABLE_CONTRACTS=1 $(pytest) -n $(TEST_WORKERS)


test-parallel-circle: test-parallel


coverage-combine:
	$(PYTHON) -m coverage report



build:
	docker build -t $(tag) .

build-no-cache:
	docker build --no-cache -t $(tag) .

test-docker: build
	docker run -it $(tag) make test


coverage-report:
	$(PYTHON) -m coverage html -d $(coverage_dir)

docs:
	sphinx-build src $(out)/docs


# Release code

bump-upload:
	$(MAKE) bump
	$(MAKE) upload

bump: # v2
	bumpversion patch
	git push --tags
	git push


upload:
	rm -f dist/*
	rm -rf src/*.egg-info
	python3 setup.py sdist
	twine upload --skip-existing --verbose dist/*
