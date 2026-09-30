---
title: Contributing
description: Develop, test, and build the Toffee documentation locally.
---

# Contributing

Clone the repository and create a development environment:

```bash
git clone https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git
cd toffee-terraform-wrapper
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the project checks:

```bash
pytest
ruff check .
ruff format --check .
terraform fmt -check -recursive
```

Build the documentation:

```bash
python -m pip install -r requirements-docs.txt
mkdocs build --strict
mkdocs serve
```

The repository owner must enable **Settings → Pages → Source: GitHub Actions**
after merging the documentation workflow. Until then, the expected Pages URL
will not publish.

Project resources:

- [Source](https://github.com/akhileshmishrabiz/toffee-terraform-wrapper)
- [Issues](https://github.com/akhileshmishrabiz/toffee-terraform-wrapper/issues)
- [Changelog](https://github.com/akhileshmishrabiz/toffee-terraform-wrapper/blob/main/CHANGELOG.md)
- [Roadmap](https://github.com/akhileshmishrabiz/toffee-terraform-wrapper/blob/main/ROADMAP.md)
- [MIT license](https://github.com/akhileshmishrabiz/toffee-terraform-wrapper/blob/main/LICENSE)
- [Testing guide](https://github.com/akhileshmishrabiz/toffee-terraform-wrapper/blob/main/TESTING.md)
