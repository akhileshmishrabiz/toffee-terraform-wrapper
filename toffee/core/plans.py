"""Record which environment a saved Terraform plan was created for.

A saved plan embeds its own backend configuration, so applying it through a
different environment still changes the original environment's state.
"""

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from typing import Optional

PLAN_FILE_SIGNATURE = b"PK\x03\x04"
RECORD_SUFFIX = ".toffee.json"


class PlanRecordError(ValueError):
    """Raised when a plan origin record exists but cannot be trusted."""


@dataclass
class PlanRecord:
    environment: str
    sha256: str


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


def write_record(plan_path: str, environment: str) -> None:
    record = {"environment": environment, "sha256": file_digest(plan_path)}
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
    return PlanRecord(data["environment"], data["sha256"])
