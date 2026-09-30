"""Plan and write a new Toffee project from the built-in or a local template.

Planning validates everything and reads the target directory without writing,
so a validation error leaves the file system untouched. Values already present
in the target (backend type, provider, project, region, environments) are
reused as defaults, which keeps reruns consistent with the first run.
"""

import difflib
import fnmatch
import os
import re
import stat
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import hcl
from . import scaffold_templates as templates
from .backend import UNKNOWN_BACKEND, find_backend_or_unknown, settings_from_text
from .config import PROJECT_CONFIG_NAME, Config, ConfigError, read_config_file
from .environment import EnvironmentManager
from .placeholders import PLACEHOLDER, placeholder_keys
from .safety import PROTECTED_ENVIRONMENT_NAMES, is_protected_environment
from .text import printable

ENV_TOKEN = "__env__"
TOKENS = ("project", "env", "region", "provider", "backend", "vars_dir", "placeholder")
_TOKEN = re.compile(r"\{\{\s*(" + "|".join(TOKENS) + r")\s*\}\}")
_PROJECT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_REGION = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]*")
_PATH_SEGMENT = re.compile(r"[A-Za-z0-9._-]+")
_PROVIDER_ALIASES = {"gcp": "google", "azure": "azurerm", "amazon": "aws"}
_BACKEND_ALIASES = {"aws": "s3", "google": "gcs", "gcp": "gcs", "azure": "azurerm"}

CREATE = "create"
APPEND = "append"
SKIP = "skip"


class ScaffoldError(ValueError):
    """Raised for invalid input; nothing has been written."""


@dataclass
class Options:
    directory: Optional[str] = None
    name: Optional[str] = None
    envs: Optional[str] = None
    provider: Optional[str] = None
    backend: Optional[str] = None
    region: Optional[str] = None
    template: Optional[str] = None
    agents: bool = False


@dataclass
class FileChange:
    path: str
    action: str
    content: bytes = b""
    mode: Optional[int] = None
    added_lines: int = 0


@dataclass
class Plan:
    root: str
    project: str
    envs: List[str]
    vars_dir: str
    changes: List[FileChange]
    # Built-in Terraform files left out because the project already has Terraform.
    omitted: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def with_action(self, action: str) -> List[FileChange]:
        return [change for change in self.changes if change.action == action]

    def full_path(self, path: str) -> str:
        return os.path.join(self.root, *path.split("/"))


@dataclass
class _Existing:
    backend: Optional[str] = None
    provider: Optional[str] = None
    project: Optional[str] = None
    region: Optional[str] = None
    envs: List[str] = field(default_factory=list)
    protected: List[str] = field(default_factory=list)
    # Variables the root module declares; None when it has no Terraform files.
    variables: Optional[set] = None


def plan_project(options: Options) -> Plan:
    """Validate options and decide what to create, append to, or skip."""
    root = os.path.abspath(options.directory or ".")
    if os.path.lexists(root) and not os.path.isdir(root):
        raise ScaffoldError(f"{printable(options.directory)} exists and is not a directory.")

    config = _existing_config(root)
    vars_dir = _vars_dir(config)
    found = _inspect(root, vars_dir, config)

    provider = _choice(
        "--provider", options.provider, templates.PROVIDERS, _PROVIDER_ALIASES
    ) or found.provider or "aws"
    backend = _choice("--backend", options.backend, templates.BACKENDS, _BACKEND_ALIASES)
    if backend and found.backend and backend != found.backend:
        raise ScaffoldError(
            f"--backend {backend} does not match the backend \"{found.backend}\" "
            f"declared in the root module. Omit --backend to use {found.backend}."
        )
    backend = backend or found.backend or templates.BACKEND_FOR_PROVIDER[provider]
    region = (
        _region(options.region)
        or found.region
        or templates.default_region(provider, backend)
    )
    project = _project(options.name, found.project, root)
    envs = _envs(options.envs, found.envs, os.path.join(root, vars_dir))

    tokens = {
        "project": project,
        "region": region,
        "provider": provider,
        "backend": backend,
        "vars_dir": vars_dir,
        "placeholder": PLACEHOLDER,
    }
    omitted = []
    if options.template is None:
        sources = []
        for path, content in templates.builtin_files(provider, backend):
            path = _in_vars_dir(path, vars_dir)
            if found.variables is not None:
                exists = os.path.lexists(os.path.join(root, *path.split("/")))
                if _is_terraform_file(path) and not exists:
                    omitted.append(path)
                    continue
                if path.endswith(".tfvars"):
                    content = _declared_only(content, found.variables)
            sources.append((path, content.encode("utf-8"), None))
    else:
        sources = _read_template(options.template)
    if options.agents and not any(path == "AGENTS.md" for path, _, _ in sources):
        sources.append(("AGENTS.md", templates.AGENTS_MD.encode("utf-8"), None))

    root_real = os.path.realpath(root)
    changes = []
    seen = set()
    for path, content, mode in _render_all(sources, envs, tokens):
        if path.casefold() in seen:
            raise ScaffoldError(f"The template renders more than one file to {path}.")
        seen.add(path.casefold())
        changes.append(_classify(root, root_real, path, content, mode))

    return Plan(
        root=root,
        project=project,
        envs=envs,
        vars_dir=vars_dir,
        changes=changes,
        omitted=omitted,
        warnings=_protection_warnings(
            envs if options.envs is not None else [], found.protected
        ),
    )


def write_plan(plan: Plan) -> None:
    """Stage every file under a temporary name, then move them into place.

    New files are linked into place so an existing file is never replaced,
    even if one appears after planning. Raises OSError or ScaffoldError.
    """
    root_real = os.path.realpath(plan.root)
    umask = _umask()
    staged = []
    try:
        for change in plan.changes:
            if change.action == SKIP:
                continue
            target = plan.full_path(change.path)
            directory = os.path.dirname(target)
            os.makedirs(directory, exist_ok=True)
            _check_writable(plan.root, root_real, change.path)
            handle, temporary = tempfile.mkstemp(
                dir=directory, prefix=".toffee-new-", suffix=".tmp"
            )
            staged.append((change, temporary, target))
            with os.fdopen(handle, "wb") as staged_file:
                staged_file.write(change.content)
            mode = change.mode if change.mode is not None else 0o666 & ~umask
            os.chmod(temporary, mode)
        for change, temporary, target in staged:
            if change.action == APPEND:
                os.replace(temporary, target)
            else:
                _link_new(temporary, target, change.path)
    finally:
        for _change, temporary, _target in staged:
            if os.path.lexists(temporary):
                os.remove(temporary)


def placeholder_refs(plan: Plan) -> List[Tuple[str, List[str]]]:
    """Return (path, keys) for this run's environment files still holding the marker."""
    refs = []
    for env in plan.envs:
        for suffix in (".tfbackend", ".tfvars"):
            path = f"{plan.vars_dir}/{env}{suffix}"
            text = _final_text(plan, path)
            if text is None:
                continue
            try:
                keys = placeholder_keys(settings_from_text(text))
            except hcl.HCLError:
                continue
            if keys:
                refs.append((path, keys))
    return refs


def env_is_complete(plan: Plan, env: str) -> bool:
    """Return whether both environment files exist once the plan is written."""
    return all(
        _final_text(plan, f"{plan.vars_dir}/{env}{suffix}") is not None
        for suffix in (".tfvars", ".tfbackend")
    )


def render(text: str, tokens: Dict[str, Optional[str]], source: str = "") -> str:
    """Replace {{token}} markers; Terraform's ${...} and %{...} are untouched."""

    def replace(match: "re.Match") -> str:
        value = tokens.get(match.group(1))
        if value is None:
            raise ScaffoldError(
                f"Template file {printable(source)} uses {{{{{match.group(1)}}}}}, "
                f"which is only available in files whose path contains {ENV_TOKEN}."
            )
        return value

    return _TOKEN.sub(replace, text)


def _render_all(sources, envs: List[str], tokens: Dict[str, str]):
    """Render sources in order; adjacent per-environment files stay grouped by env."""
    index = 0
    while index < len(sources):
        group = [sources[index]]
        while (
            ENV_TOKEN in group[0][0]
            and index + len(group) < len(sources)
            and ENV_TOKEN in sources[index + len(group)][0]
        ):
            group.append(sources[index + len(group)])
        index += len(group)
        for env in envs if ENV_TOKEN in group[0][0] else [None]:
            for path, content, mode in group:
                target = path.replace(ENV_TOKEN, env) if env else path
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError:
                    data = content
                else:
                    data = render(text, {**tokens, "env": env}, path).encode("utf-8")
                yield target, data, mode


def _classify(
    root: str, root_real: str, path: str, content: bytes, mode: Optional[int]
) -> FileChange:
    target = os.path.join(root, *path.split("/"))
    if path == ".gitignore" and os.path.lexists(target):
        _check_writable(root, root_real, path)
        return _gitignore_change(target, content)
    if os.path.lexists(target):
        if os.path.isdir(target) and not os.path.islink(target):
            raise ScaffoldError(f"{path} exists and is a directory.")
        return FileChange(path, SKIP)
    _check_writable(root, root_real, path)
    return FileChange(path, CREATE, content, mode)


def _check_writable(root: str, root_real: str, path: str) -> None:
    """Refuse symlinks and anything that would land outside the project."""
    current = root
    for part in path.split("/"):
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise ScaffoldError(
                f"Refusing to write through symlink: {printable(path)}."
            )
    parent = os.path.dirname(current)
    if os.path.lexists(parent) and not os.path.isdir(parent):
        raise ScaffoldError(f"{printable(path)}: a parent path is not a directory.")
    real = os.path.realpath(current)
    if os.path.commonpath([real, root_real]) != root_real:
        raise ScaffoldError(f"Refusing to write outside the project: {printable(path)}.")


def _gitignore_change(target: str, template_content: bytes) -> FileChange:
    try:
        with open(target, "rb") as gitignore:
            existing = gitignore.read().decode("utf-8")
    except UnicodeDecodeError:
        return FileChange(".gitignore", SKIP)
    present = {line.strip() for line in existing.splitlines()}
    wanted = [
        line.strip()
        for line in template_content.decode("utf-8", errors="replace").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    missing = [line for line in dict.fromkeys(wanted) if line not in present]
    if _ignores_project_config(existing.splitlines() + missing):
        missing.append(f"!/{PROJECT_CONFIG_NAME}")
    if not missing:
        return FileChange(".gitignore", SKIP)
    separator = "\n" if existing and not existing.endswith("\n") else ""
    spacer = "\n" if existing.strip() else ""
    content = (
        existing + separator + spacer + "# Added by toffee new\n" + "\n".join(missing) + "\n"
    )
    return FileChange(
        ".gitignore",
        APPEND,
        content.encode("utf-8"),
        stat.S_IMODE(os.stat(target).st_mode),
        len(missing),
    )


def _ignores_project_config(lines: List[str]) -> bool:
    """Approximate whether gitignore lines ignore the root .toffee.json."""
    ignored = False
    for line in lines:
        pattern = line.strip()
        if not pattern or pattern.startswith("#") or pattern.endswith("/"):
            continue
        negated = pattern.startswith("!")
        pattern = pattern[1:] if negated else pattern
        if pattern.startswith("**/"):
            pattern = pattern[3:]
        pattern = pattern.lstrip("/")
        if "/" not in pattern and fnmatch.fnmatchcase(PROJECT_CONFIG_NAME, pattern):
            ignored = not negated
    return ignored


def _link_new(temporary: str, target: str, path: str) -> None:
    try:
        os.link(temporary, target)
    except FileExistsError:
        raise ScaffoldError(
            f"{printable(path)} appeared while writing; it was not overwritten."
        ) from None
    except OSError:
        # Some file systems do not support hard links.
        if os.path.lexists(target):
            raise
        os.replace(temporary, target)


def _final_text(plan: Plan, path: str) -> Optional[str]:
    for change in plan.changes:
        if change.path == path and change.action != SKIP:
            return change.content.decode("utf-8", errors="replace")
    full = plan.full_path(path)
    if not os.path.isfile(full):
        return None
    try:
        with open(full, "r", encoding="utf-8") as existing:
            return existing.read()
    except (OSError, UnicodeDecodeError):
        return ""


def _existing_config(root: str) -> Dict[str, object]:
    try:
        return read_config_file(os.path.join(root, PROJECT_CONFIG_NAME))
    except ConfigError as e:
        raise ScaffoldError(f"Cannot use the existing {PROJECT_CONFIG_NAME}: {e}") from e


def _vars_dir(config: Dict[str, object]) -> str:
    value = str(config.get("vars_dir", "vars"))
    parts = os.path.normpath(value).replace("\\", "/").split("/")
    if os.path.isabs(value) or not all(
        _PATH_SEGMENT.fullmatch(part) and part not in (".", "..") for part in parts
    ):
        raise ScaffoldError(
            f"{PROJECT_CONFIG_NAME} sets vars_dir to {printable(value)!r}; toffee new "
            "needs a simple relative path inside the project, such as vars."
        )
    return "/".join(parts)


def _in_vars_dir(path: str, vars_dir: str) -> str:
    return vars_dir + path[len("vars") :] if path.startswith("vars/") else path


def _inspect(root: str, vars_dir: str, config: Dict[str, object]) -> _Existing:
    found = _Existing(protected=list(config.get("protected_environments", [])))
    try:
        found.protected += Config().global_values.get("protected_environments", [])
    except ConfigError:
        pass
    if not os.path.isdir(root):
        return found

    backend, _problem = find_backend_or_unknown(root)
    if backend is not None and backend is not UNKNOWN_BACKEND:
        if backend.type not in templates.BACKENDS:
            raise ScaffoldError(
                f"The root module declares backend \"{printable(backend.type)}\", but "
                f"toffee new only writes {', '.join(templates.BACKENDS)} settings. "
                "Add environments with: toffee env create <name>"
            )
        found.backend = backend.type
    found.provider, found.variables = _declarations(root)

    manager = EnvironmentManager(vars_dir=os.path.join(root, vars_dir))
    found.envs = manager.get_environment_names()
    for name in found.envs:
        values = _string_settings(manager.get_environment(name).vars_file)
        project, region = values.get("project"), values.get("region")
        if found.project is None and project and _PROJECT_NAME.fullmatch(project):
            found.project = project
        if found.region is None and region and _REGION.fullmatch(region):
            found.region = region
    return found


def _declarations(root: str) -> Tuple[Optional[str], Optional[set]]:
    """Return the root module's first known provider and its variable names.

    Variables are None when there are no Terraform files, and every built-in
    name when they cannot all be read, so nothing useful is left out.
    """
    names = sorted(os.listdir(root))
    if not any(_is_terraform_file(name) for name in names):
        return None, None
    providers: List[str] = []
    variables = set()
    complete = True
    for name in names:
        if not name.endswith(".tf"):
            complete = complete and not name.endswith(".tf.json")
            continue
        try:
            items = hcl.read_items(os.path.join(root, name))
        except (OSError, UnicodeDecodeError, hcl.HCLError):
            complete = False
            continue
        for item in items:
            if item.is_block and item.key == "variable" and len(item.labels) == 1:
                variables.add(item.labels[0])
            if not (item.is_block and item.key == "terraform"):
                continue
            for nested in hcl.parse(item.raw):
                if nested.is_block and nested.key == "required_providers":
                    providers += [entry.key for entry in hcl.parse(nested.raw)]
    if not complete:
        variables |= {"project", "project_id", "environment", "region"}
    provider = next((name for name in templates.PROVIDERS if name in providers), None)
    return provider, variables


def _is_terraform_file(path: str) -> bool:
    return path.endswith((".tf", ".tf.json")) or path.startswith("modules/")


def _declared_only(tfvars: str, variables: set) -> str:
    """Keep only assignments to variables the existing root module declares."""
    kept = [
        line for line in tfvars.splitlines(keepends=True)
        if line.split("=", 1)[0].strip() in variables
    ]
    return "".join(kept) or "# Terraform variables for {{env}}.\n"


def _string_settings(path: str) -> Dict[str, str]:
    try:
        items = hcl.read_items(path)
    except (OSError, UnicodeDecodeError, hcl.HCLError):
        return {}
    values = {}
    for item in items:
        value = None if item.is_block else hcl.string_value(item.raw)
        if value is not None:
            values[item.key] = value
    return values


def _choice(label: str, value: Optional[str], choices, aliases) -> Optional[str]:
    if value is None:
        return None
    folded = value.strip().lower()
    if folded in choices:
        return folded
    guess = aliases.get(folded) or next(
        iter(difflib.get_close_matches(folded, choices, n=1, cutoff=0.5)), None
    )
    hint = f" Did you mean '{guess}'?" if guess else ""
    raise ScaffoldError(
        f"Unknown {label} '{printable(value)}'.{hint} "
        f"Choose from: {', '.join(choices)}."
    )


def _region(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not _REGION.fullmatch(value):
        raise ScaffoldError(
            f"--region '{printable(value)}' may contain only letters, digits, "
            "spaces, '.', '_', and '-', for example --region us-east-1."
        )
    return value


def _project(name: Optional[str], inferred: Optional[str], root: str) -> str:
    if name is not None:
        if not _PROJECT_NAME.fullmatch(name):
            raise ScaffoldError(
                f"--name '{printable(name)}' must start with a letter or digit and "
                "contain only letters, digits, '.', '_', and '-'."
            )
        return name
    if inferred:
        return inferred
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", os.path.basename(root)).strip("-._")
    if not _PROJECT_NAME.fullmatch(slug):
        raise ScaffoldError(
            "Cannot derive a project name from the directory name; pass one with "
            "--name, for example --name my-service."
        )
    return slug


def _envs(raw: Optional[str], existing: List[str], vars_path: str) -> List[str]:
    if raw is None:
        return existing or ["dev"]
    names = [name.strip() for name in raw.split(",")]
    if not all(names):
        raise ScaffoldError(
            "--envs needs comma-separated names without empty entries, "
            "for example --envs dev,prod."
        )
    manager = EnvironmentManager(vars_dir=vars_path)
    unique: List[str] = []
    for name in dict.fromkeys(names):
        valid, error = manager.validate_env_name(name)
        if not valid:
            raise ScaffoldError(f"--envs: {error}.")
        twin = next((other for other in unique if other.casefold() == name.casefold()), None)
        conflict = twin or manager.case_conflict(name)
        if conflict:
            raise ScaffoldError(
                f"--envs: '{name}' and '{conflict}' differ only by case; environment "
                "names must be unique ignoring case."
            )
        unique.append(name)
    return unique


def _protection_warnings(envs: List[str], protected: List[str]) -> List[str]:
    warnings = []
    for name in envs:
        if is_protected_environment(name, protected):
            continue
        close = difflib.get_close_matches(
            name.casefold(), sorted(PROTECTED_ENVIRONMENT_NAMES), n=1, cutoff=0.75
        )
        if close:
            warnings.append(
                f"'{name}' is not protected like '{close[0]}'. If it is production, "
                f"name it '{close[0]}' or add it to protected_environments in "
                f"{PROJECT_CONFIG_NAME}."
            )
    return warnings


def _read_template(template: str) -> List[Tuple[str, bytes, Optional[int]]]:
    base = os.path.abspath(template)
    if not os.path.isdir(base):
        raise ScaffoldError(f"Template directory not found: {printable(template)}")
    files = []
    for current, dirs, names in os.walk(base):
        dirs.sort()
        for name in list(dirs):
            if name == ".git":
                dirs.remove(name)
            elif os.path.islink(os.path.join(current, name)):
                raise ScaffoldError(_template_symlink(base, current, name))
        for name in sorted(names):
            full = os.path.join(current, name)
            if os.path.islink(full):
                raise ScaffoldError(_template_symlink(base, current, name))
            info = os.lstat(full)
            relative = os.path.relpath(full, base).replace(os.sep, "/")
            if not stat.S_ISREG(info.st_mode):
                raise ScaffoldError(
                    f"Template entry is not a regular file: {printable(relative)}"
                )
            with open(full, "rb") as source:
                files.append((relative, source.read(), stat.S_IMODE(info.st_mode)))
    if not files:
        raise ScaffoldError(f"Template directory has no files: {printable(template)}")
    return files


def _template_symlink(base: str, current: str, name: str) -> str:
    relative = os.path.relpath(os.path.join(current, name), base).replace(os.sep, "/")
    return f"Template contains a symlink, which toffee new does not copy: {printable(relative)}"


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask
