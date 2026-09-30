"""Find a root module's backend and work out where each environment keeps state."""

import json
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from . import hcl
from .environment_diff import is_sensitive_key
from .text import printable

DEFAULT_WORKSPACE = "default"

# Settings that decide which state object a backend reads and writes.
_IDENTITY_SETTINGS = {
    "s3": (("bucket", None), ("key", None)),
    "gcs": (("bucket", None), ("prefix", "")),
    "azurerm": (
        ("storage_account_name", None),
        ("container_name", None),
        ("key", None),
    ),
    "local": (("path", "terraform.tfstate"),),
    "remote": (
        ("hostname", "app.terraform.io"),
        ("organization", None),
        ("workspaces.name", None),
        ("workspaces.prefix", None),
    ),
    "cloud": (
        ("hostname", "app.terraform.io"),
        ("organization", None),
        ("workspaces.name", None),
        ("workspaces.tags", None),
        ("workspaces.project", None),
    ),
    "consul": (("path", None),),
    "http": (("address", None),),
    "kubernetes": (("secret_suffix", None), ("namespace", "default")),
    "pg": (("conn_str", None), ("schema_name", "terraform_remote_state")),
}
# These only separate state once a non-default workspace is selected.
_WORKSPACE_SETTINGS = {
    "s3": (("workspace_key_prefix", "env:"),),
    "local": (("workspace_dir", "terraform.tfstate.d"),),
}
_WITHOUT_WORKSPACES = frozenset({"http"})
_LOCAL_PATH_SETTINGS = frozenset({"path", "workspace_dir"})
_SECRET_SETTINGS = frozenset({"conn_str"})

Identity = Tuple[Tuple[str, Optional[str]], ...]


class BackendError(ValueError):
    """Raised when backend configuration cannot be read reliably."""


@dataclass
class Backend:
    type: str
    settings: Dict[str, object]
    source: str


# Stands in for a root module whose configuration could not be parsed.
UNKNOWN_BACKEND = Backend("unknown", {}, "")


def find_backend_or_unknown(root_dir: str) -> Tuple[Optional[Backend], Optional[str]]:
    """Return the root module's backend, or UNKNOWN_BACKEND and the reason."""
    try:
        return find_backend(root_dir), None
    except BackendError as e:
        return UNKNOWN_BACKEND, str(e)


def find_backend(root_dir: str) -> Optional[Backend]:
    """Return the backend or cloud block declared by the root module."""
    try:
        names = sorted(os.listdir(root_dir))
    except OSError as e:
        raise BackendError(f"cannot read {root_dir}: {e}") from e

    names = [name for name in names if name.endswith((".tf", ".tf.json"))]
    # Terraform merges override files last, and they replace the backend.
    ordered = [name for name in names if not _is_override(name)] + [
        name for name in names if _is_override(name)
    ]
    found = None
    for name in ordered:
        path = os.path.join(root_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            backends = (
                _json_backends(path) if name.endswith(".json") else _hcl_backends(path)
            )
        except (OSError, UnicodeDecodeError, ValueError) as e:
            raise BackendError(f"cannot read {path}: {e}") from e
        for backend in backends:
            if found is None or _is_override(name):
                found = backend
    return found


def read_settings(path: str) -> Dict[str, object]:
    """Read an environment's .tfbackend file into nested settings."""
    try:
        with open(path, "r", encoding="utf-8") as backend_file:
            return settings_from_text(backend_file.read())
    except (OSError, UnicodeDecodeError, hcl.HCLError) as e:
        raise BackendError(f"cannot read {path}: {e}") from e


def backend_config_overrides(args: List[str], root_dir: str) -> Dict[str, object]:
    """Load Terraform init -backend-config values in command-line order."""
    merged: Dict[str, object] = {}
    index = 0
    while index < len(args):
        argument = args[index]
        value = None
        for prefix in ("-backend-config=", "--backend-config="):
            if argument.startswith(prefix):
                value = argument[len(prefix) :]
                break
        if argument in ("-backend-config", "--backend-config"):
            if index + 1 >= len(args):
                raise BackendError("-backend-config requires a value")
            index += 1
            value = args[index]
        if value is not None:
            key, separator, setting = value.partition("=")
            if separator:
                if not key.strip():
                    raise BackendError("-backend-config has an empty setting name")
                merged[key.strip()] = setting
            else:
                path = value if os.path.isabs(value) else os.path.join(root_dir, value)
                merged.update(read_settings(path))
        index += 1
    return merged


def settings_from_text(text: str) -> Dict[str, object]:
    settings: Dict[str, object] = {}
    for item in hcl.parse(text):
        raw = item.raw.strip()
        if item.is_block:
            settings[item.key] = settings_from_text(item.raw)
        elif raw.startswith("{") and raw.endswith("}"):
            settings[item.key] = settings_from_text(raw[1:-1])
        else:
            settings[item.key] = hcl.setting_value(item.raw)
    return settings


def selected_workspace(data_dir: str) -> str:
    """Return the workspace Terraform will use with this TF_DATA_DIR."""
    workspace = os.environ.get("TF_WORKSPACE")
    if workspace:
        return workspace
    try:
        with open(os.path.join(data_dir, "environment"), "r") as workspace_file:
            return workspace_file.read().strip() or DEFAULT_WORKSPACE
    except (OSError, UnicodeDecodeError):
        return DEFAULT_WORKSPACE


def state_identity(
    backend: Optional[Backend],
    env_settings: Dict[str, object],
    root_dir: str,
    workspace: str = DEFAULT_WORKSPACE,
) -> Identity:
    """Return a value that, compared with same_state(), matches for two
    environments sharing state."""
    if backend is UNKNOWN_BACKEND:
        # The workspace is ignored because it may not separate this backend.
        return (("backend", backend.type),) + tuple(
            (name, value)
            for name, value in sorted(_flatten(env_settings).items())
            if not is_sensitive_key(name.rsplit(".", 1)[-1])
        )
    if backend is None:
        # Without a backend block Terraform ignores -backend-config entirely.
        return (
            ("backend", "local"),
            ("path", _local_path(root_dir, "terraform.tfstate")),
            ("workspace", workspace),
        )

    settings = {**backend.settings, **env_settings}
    identity: List[Tuple[str, Optional[str]]] = [("backend", backend.type)]
    known = _IDENTITY_SETTINGS.get(backend.type)
    if known is None:
        identity.extend(
            (name, value)
            for name, value in sorted(_flatten(settings).items())
            if not is_sensitive_key(name.rsplit(".", 1)[-1])
        )
    else:
        wanted = known
        if workspace != DEFAULT_WORKSPACE:
            wanted = known + _WORKSPACE_SETTINGS.get(backend.type, ())
        for name, default in wanted:
            value = _setting(settings, name, default)
            if value is not None and name in _LOCAL_PATH_SETTINGS:
                value = _local_path(root_dir, value)
            identity.append((name, value))
    if backend.type not in _WITHOUT_WORKSPACES:
        identity.append(("workspace", workspace))
    return tuple(identity)


def same_state(first: Identity, second: Identity) -> bool:
    return _comparable(first) == _comparable(second)


def _comparable(identity: Identity) -> Identity:
    # macOS and Windows file systems are case-insensitive by default.
    if identity[0] != ("backend", "local") or sys.platform not in ("darwin", "win32"):
        return identity
    return tuple(
        (name, value.casefold() if value and name in _LOCAL_PATH_SETTINGS else value)
        for name, value in identity
    )


def describe_identity(identity: Identity) -> str:
    """Summarize a state identity without secret values."""
    backend_type = identity[0][1]
    details = " ".join(
        f"{name}={value}"
        for name, value in identity[1:]
        if value is not None
        and name not in _SECRET_SETTINGS
        and not is_sensitive_key(name.rsplit(".", 1)[-1])
    )
    return printable(f"{backend_type} {details}".strip())


def describe(
    backend: Optional[Backend],
    env_settings: Dict[str, object],
    backend_name: str,
) -> str:
    """Return a concise backend destination without exposing credentials."""
    if backend is None:
        return "local://terraform.tfstate (no backend block in the root module)"
    if backend is UNKNOWN_BACKEND:
        return "unknown (could not parse configuration)"

    settings = {**backend.settings, **env_settings}

    def get(name: str, default: Optional[str] = None) -> Optional[str]:
        return _setting(settings, name, default)

    backend_type = backend.type
    if backend_type == "s3":
        summary = _uri("s3", get("bucket"), get("key"))
    elif backend_type == "gcs":
        summary = _uri("gs", get("bucket"), get("prefix"))
    elif backend_type == "azurerm":
        container = get("container_name")
        key = get("key")
        path = f"{container}/{key}" if container and key else container or key
        summary = _uri("azurerm", get("storage_account_name"), path)
    elif backend_type == "local":
        summary = f"local://{get('path', 'terraform.tfstate')}"
    elif backend_type in ("remote", "cloud"):
        workspace = get("workspaces.name") or (
            f"{get('workspaces.prefix')}*" if get("workspaces.prefix") else None
        )
        workspace = workspace or get("workspaces.tags")
        path = f"{get('organization')}/{workspace}" if workspace else None
        summary = _uri(backend_type, get("hostname", "app.terraform.io"), path)
    elif backend_type == "consul":
        summary = _uri("consul", get("address", "localhost:8500"), get("path"))
    elif backend_type == "http":
        summary = _redacted_url(get("address"))
    elif backend_type == "kubernetes":
        summary = _uri("kubernetes", get("namespace", "default"), get("secret_suffix"))
    elif backend_type == "pg":
        summary = f"pg (schema {get('schema_name', 'terraform_remote_state')})"
    else:
        summary = f"{backend_type} (configured by {backend_name})"
    return printable(summary)


def _hcl_backends(path: str) -> List[Backend]:
    backends = []
    for item in hcl.read_items(path):
        if not (item.is_block and item.key == "terraform" and not item.labels):
            continue
        for nested in hcl.parse(item.raw):
            if not nested.is_block:
                continue
            if nested.key == "backend" and len(nested.labels) == 1:
                backend_type = nested.labels[0]
            elif nested.key == "cloud" and not nested.labels:
                backend_type = "cloud"
            else:
                continue
            backends.append(Backend(backend_type, settings_from_text(nested.raw), path))
    return backends


def _json_backends(path: str) -> List[Backend]:
    with open(path, "r", encoding="utf-8") as json_file:
        document = json.load(json_file)
    if not isinstance(document, dict):
        return []
    backends = []
    for block in _as_list(document.get("terraform")):
        if not isinstance(block, dict):
            continue
        for backend in _as_list(block.get("backend")):
            if isinstance(backend, dict):
                for backend_type, config in backend.items():
                    backends.append(Backend(backend_type, _json_settings(config), path))
        for cloud in _as_list(block.get("cloud")):
            backends.append(Backend("cloud", _json_settings(cloud), path))
    return backends


def _json_settings(config: object) -> Dict[str, object]:
    config = _single_block(config)
    if not isinstance(config, dict):
        return {}
    settings: Dict[str, object] = {}
    for key, value in config.items():
        value = _single_block(value)
        if isinstance(value, dict):
            settings[key] = _json_settings(value)
        elif isinstance(value, str):
            settings[key] = value
        else:
            settings[key] = json.dumps(value, sort_keys=True)
    return settings


def _single_block(value: object) -> object:
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        return value[0]
    return value


def _as_list(value: object) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _is_override(name: str) -> bool:
    stem = name[: -len(".tf.json")] if name.endswith(".tf.json") else name[:-3]
    return stem == "override" or stem.endswith("_override")


def _setting(
    settings: Dict[str, object], dotted_name: str, default: Optional[str] = None
) -> Optional[str]:
    value: object = settings
    for part in dotted_name.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _flatten(settings: Dict[str, object], prefix: str = "") -> Dict[str, str]:
    flat: Dict[str, str] = {}
    for key, value in settings.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{name}."))
        else:
            flat[name] = str(value)
    return flat


def _local_path(root_dir: str, path: str) -> str:
    return os.path.normpath(os.path.join(os.path.realpath(root_dir), path))


def _uri(scheme: str, container: Optional[str], path: Optional[str]) -> str:
    if not container:
        return f"{scheme}:// (destination not configured)"
    if path:
        return f"{scheme}://{container}/{path.lstrip('/')}"
    return f"{scheme}://{container}"


def _redacted_url(address: Optional[str]) -> str:
    if not address:
        return "http:// (destination not configured)"
    try:
        parts = urlsplit(address)
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
    except ValueError:
        return "http (address configured)"
    if not parts.scheme:
        return "http (address configured)"
    return f"{parts.scheme}://{host}{parts.path}"
