.PHONY: clean build test lint tag-release publish release-check release help

# Get version from pyproject.toml
VERSION := $(shell grep -m 1 version pyproject.toml | cut -d '"' -f 2)

help:
	@echo "Toffee Makefile commands:"
	@echo "  clean        - Remove build artifacts and Python cache files"
	@echo "  build        - Build source and wheel distributions"
	@echo "  test         - Run tests"
	@echo "  lint         - Run code linters"
	@echo "  tag-release  - Create and push a Git tag for the current version"
	@echo "  publish      - Upload the package to PyPI"
	@echo "  release      - Full release process: test, build, tag, and publish"
	@echo "  release-check - Check if the current version is properly set for release"
	@echo ""
	@echo "Current version: $(VERSION)"

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete

build: clean
	python -m build

# test:
# 	pytest

lint:
	flake8 toffee tests
	black --check toffee tests
	isort --check toffee tests

release-check:
	@echo "Checking version..."
	@if git tag | grep -q "v$(VERSION)"; then \
		echo "Error: Tag v$(VERSION) already exists. Update version in pyproject.toml."; \
		exit 1; \
	fi
	@echo "Version v$(VERSION) is ready for release."

tag-release: release-check
	git tag -a "v$(VERSION)" -m "Release v$(VERSION)"
	git push origin "v$(VERSION)"
	@echo "Tagged and pushed v$(VERSION)"

publish: build
	twine check dist/*
	twine upload dist/*

release: test lint build tag-release publish
	@echo "Release v$(VERSION) completed!"

# Install development dependencies
dev-setup:
	pip install -r requirements-dev.txt
	pip install -e .