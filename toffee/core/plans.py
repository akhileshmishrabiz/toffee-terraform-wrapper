"""Record which environment a saved Terraform plan was created for.

A saved plan embeds its own backend configuration, so applying it through a
different environment still changes the original environment's state.

Records are signed with a random per-user key kept outside the project, so a
record edited by hand, or created by another user or machine, is not trusted.
"""

import hashlib
import hmac
import json
import os
import secrets
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PLAN_FILE_SIGNATURE = b"PK\x03\x04"
RECORD_SUFFIX = ".toffee.json"
SIGNING_KEY_NAME = "plan-signing.key"
_SIGNATURE_CONTEXT = "toffee-plan-record-v1"
_KEY_BYTES = 32


class PlanRecordError(ValueError):
    """Raised when a plan origin record exists but cannot be read."""


class SigningKeyError(Exception):
    """Raised when the plan-signing key cannot be created or trusted."""


@dataclass
class PlanRecord:
    environment: str
    sha256: str
    signature: Optional[str] = None


def is_plan_file(path: str) -> bool:
    """Saved plans are zip archives; anything else is not applied as a plan."""
    try:
        with open(path, "rb") as plan_file:
            return plan_file.read(len(PLAN_FILE_SIGNATURE)) == PLAN_FILE_SIGNATURE
    except OSError:
        return False


def record_path(plan_path: str) -> str:
    return plan_path + RECORD_SUFFIX


def file_digest(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as plan_file:
        for chunk in iter(lambda: plan_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def signing_key_path() -> str:
    try:
        home = str(Path.home())
    except (RuntimeError, KeyError) as e:
        raise SigningKeyError(f"cannot locate the home directory: {e}") from e
    return os.path.join(home, ".toffee", SIGNING_KEY_NAME)


def load_signing_key(create: bool = False) -> bytes:
    """Return this user's plan-signing key, creating it only when asked."""
    path = signing_key_path()
    if create and not os.path.lexists(path):
        _create_signing_key(path)
    try:
        with open(path, "r", encoding="ascii") as key_file:
            status = os.fstat(key_file.fileno())
            text = key_file.read()
    except FileNotFoundError as e:
        raise SigningKeyError(f"{path} does not exist") from e
    except (OSError, UnicodeDecodeError) as e:
        raise SigningKeyError(f"cannot read {path}: {e}") from e
    if not stat.S_ISREG(status.st_mode):
        raise SigningKeyError(f"{path} is not a regular file")
    if os.name == "posix" and status.st_mode & 0o077:
        raise SigningKeyError(
            f"{path} is accessible by other users; run: chmod 600 {path}"
        )
    try:
        key = bytes.fromhex(text.strip())
    except ValueError:
        key = b""
    if len(key) < _KEY_BYTES:
        raise SigningKeyError(f"{path} does not contain a valid key")
    return key


def _create_signing_key(path: str) -> None:
    directory = os.path.dirname(path)
    temporary = None
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(handle, "w", encoding="ascii") as key_file:
            key_file.write(secrets.token_hex(_KEY_BYTES) + "\n")
        # Linking never replaces a key another process created meanwhile.
        os.link(temporary, path)
    except FileExistsError:
        pass
    except OSError as e:
        raise SigningKeyError(f"cannot create {path}: {e}") from e
    finally:
        if temporary and os.path.exists(temporary):
            os.remove(temporary)


def _signature(key: bytes, environment: str, sha256: str) -> str:
    message = json.dumps([_SIGNATURE_CONTEXT, environment, sha256]).encode("ascii")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def write_record(plan_path: str, environment: str) -> None:
    """Write a signed record; raises OSError or SigningKeyError on failure."""
    sha256 = file_digest(plan_path)
    key = load_signing_key(create=True)
    record = {
        "environment": environment,
        "sha256": sha256,
        "signature": _signature(key, environment, sha256),
    }
    target = record_path(plan_path)
    handle, temporary = tempfile.mkstemp(
        dir=os.path.dirname(os.path.abspath(target)), suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "w") as record_file:
            json.dump(record, record_file, indent=2)
            record_file.write("\n")
        os.replace(temporary, target)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


def remove_record(plan_path: str) -> None:
    try:
        os.remove(record_path(plan_path))
    except FileNotFoundError:
        pass


def read_record(plan_path: str) -> Optional[PlanRecord]:
    """Return the plan's origin record, or None when there is none."""
    path = record_path(plan_path)
    if not os.path.lexists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as record_file:
            data = json.load(record_file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise PlanRecordError(f"cannot read {path}: {e}") from e
    if not (
        isinstance(data, dict)
        and isinstance(data.get("environment"), str)
        and isinstance(data.get("sha256"), str)
    ):
        raise PlanRecordError(f"{path} is not a valid Toffee plan record")
    signature = data.get("signature")
    return PlanRecord(
        data["environment"],
        data["sha256"],
        signature if isinstance(signature, str) else None,
    )


def signature_problem(record: PlanRecord) -> Optional[str]:
    """Return why a record's signature cannot be trusted, or None if it can."""
    if not record.signature:
        return "its Toffee record is not signed"
    try:
        key = load_signing_key()
    except SigningKeyError as e:
        return f"this user's plan-signing key is unavailable ({e})"
    expected = _signature(key, record.environment, record.sha256)
    provided = record.signature.encode("utf-8", "surrogatepass")
    if not hmac.compare_digest(expected.encode("ascii"), provided):
        return (
            "its Toffee record was not signed with this user's plan-signing key "
            "(it was edited, or created by another user or machine)"
        )
    return None
