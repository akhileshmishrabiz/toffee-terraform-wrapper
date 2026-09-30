"""Dependency-free reader for the small HCL subset used by Terraform settings files.

This is not an HCL evaluator. It understands enough structure (strings,
comments, heredocs, and bracket nesting) to find top-level assignments and
blocks without misreading their contents.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_-]*"
_HEREDOC_START = re.compile(r"<<(-?)(" + _IDENTIFIER + r")[ \t]*\r?\n")
_ASSIGNMENT = re.compile(r"(" + _IDENTIFIER + r")[ \t]*=(?!=)[ \t]*")
_BLOCK = re.compile(
    r"(" + _IDENTIFIER + r')((?:[ \t]+(?:"x*"|' + _IDENTIFIER + r"))*)[ \t]*\{"
)
_LABEL = re.compile(r'"((?:[^"\\]|\\.)*)"|(' + _IDENTIFIER + r")")
_STRING_LITERAL = re.compile(r'"((?:\$\$\{|%%\{|[^"\\$%\n]|\\.|\$(?!\{)|%(?!\{))*)"')
_ESCAPE = re.compile(r"\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|.)")
_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
_OPENERS = "([{"
_CLOSERS = ")]}"


class HCLError(ValueError):
    """Raised when a file cannot be read without guessing at its structure."""


@dataclass
class Item:
    """A top-level assignment (``key = value``) or block (``key "label" { }``)."""

    key: str
    labels: Tuple[str, ...]
    value: str
    raw: str
    is_block: bool
    line: int
    start: int
    end: int


@dataclass
class _Scanned:
    code: str
    skeleton: str
    strings: List[Tuple[int, int]]
    heredocs: Dict[int, int]


def read_assignments(path: str) -> Dict[str, str]:
    """Return normalized top-level values keyed by name; later keys win."""
    return {item.key: item.value for item in read_items(path)}


def read_items(path: str) -> List[Item]:
    with open(path, "r", encoding="utf-8") as config_file:
        return parse(config_file.read())


def parse(text: str) -> List[Item]:
    """Parse top-level assignments and blocks, ignoring unrecognized lines."""
    scanned = _scan(text)
    skeleton = scanned.skeleton
    items: List[Item] = []
    position = 0
    length = len(text)

    while position < length:
        while position < length and skeleton[position].isspace():
            position += 1
        if position >= length:
            break

        assignment = _ASSIGNMENT.match(skeleton, position)
        if assignment:
            value_start = assignment.end()
            value_end = _expression_end(scanned, value_start, assignment.group(1))
            raw = scanned.code[value_start:value_end]
            if not raw.strip():
                raise HCLError(
                    f"missing value for '{assignment.group(1)}' on line "
                    f"{_line(text, position)}"
                )
            items.append(
                Item(
                    key=assignment.group(1),
                    labels=(),
                    value=_normalize(raw),
                    raw=raw,
                    is_block=False,
                    line=_line(text, position),
                    start=value_start,
                    end=value_end,
                )
            )
            position = value_end
            continue

        block = _BLOCK.match(skeleton, position)
        if block:
            open_brace = block.end() - 1
            close_brace = _block_end(scanned, open_brace, block.group(1))
            labels = tuple(
                quoted if quoted else bare
                for quoted, bare in _LABEL.findall(
                    scanned.code[block.end(1) : open_brace]
                )
            )
            items.append(
                Item(
                    key=block.group(1),
                    labels=labels,
                    value=_normalize(scanned.code[open_brace : close_brace + 1]),
                    raw=scanned.code[open_brace + 1 : close_brace],
                    is_block=True,
                    line=_line(text, position),
                    start=open_brace,
                    end=close_brace + 1,
                )
            )
            position = close_brace + 1
            continue

        line_end = skeleton.find("\n", position)
        position = length if line_end == -1 else line_end + 1

    return items


def string_literals(text: str) -> List[Tuple[int, int]]:
    """Return spans of quoted strings outside comments and heredocs."""
    return _scan(text).strings


def string_value(raw: str) -> Optional[str]:
    """Decode a plain quoted string; return None for anything else."""
    match = _STRING_LITERAL.fullmatch(raw.strip())
    if not match:
        return None
    decoded = _ESCAPE.sub(_unescape, match.group(1))
    return decoded.replace("$${", "${").replace("%%{", "%{")


def setting_value(raw: str) -> str:
    """Return a string's decoded value, or the literal source text otherwise."""
    value = string_value(raw)
    return value if value is not None else _normalize(raw)


def _unescape(match: "re.Match") -> str:
    escape = match.group(1)
    if escape[0] in "uU" and len(escape) > 1:
        code_point = int(escape[1:], 16)
        return chr(code_point) if code_point <= 0x10FFFF else match.group(0)
    return _ESCAPES.get(escape, match.group(0))


def _normalize(raw: str) -> str:
    if raw.lstrip().startswith("<<"):
        return raw.strip().replace("\r\n", "\n")
    return " ".join(line.strip() for line in raw.split("\n") if line.strip())


def _line(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _scan(text: str) -> _Scanned:
    code = list(text)
    skeleton = list(text)
    strings: List[Tuple[int, int]] = []
    heredocs: Dict[int, int] = {}
    index = 0
    length = len(text)

    def blank(start: int, end: int, *targets: list) -> None:
        for position in range(start, end):
            if text[position] != "\n":
                for target in targets:
                    target[position] = " "

    while index < length:
        character = text[index]
        if character == "#" or text.startswith("//", index):
            end = text.find("\n", index)
            end = length if end == -1 else end
            blank(index, end, code, skeleton)
            index = end
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end == -1:
                raise HCLError(
                    f"unterminated comment starting on line {_line(text, index)}"
                )
            blank(index, end + 2, code, skeleton)
            index = end + 2
        elif character == '"':
            end = _string_end(text, index)
            for position in range(index + 1, end - 1):
                if text[position] != "\n":
                    skeleton[position] = "x"
            strings.append((index, end))
            index = end
        elif text.startswith("<<", index) and _HEREDOC_START.match(text, index):
            header = _HEREDOC_START.match(text, index)
            end = _heredoc_end(text, header)
            blank(header.end(), end, skeleton)
            heredocs[index] = end
            index = end
        else:
            index += 1

    return _Scanned("".join(code), "".join(skeleton), strings, heredocs)


def _string_end(text: str, start: int) -> int:
    index = start + 1
    length = len(text)
    while index < length:
        character = text[index]
        if character == "\\":
            index += 2
        elif character == '"':
            return index + 1
        elif character == "\n":
            break
        elif text.startswith("$${", index) or text.startswith("%%{", index):
            index += 3
        elif text.startswith("${", index) or text.startswith("%{", index):
            index = _template_end(text, index + 2, start)
        else:
            index += 1
    raise HCLError(f"unterminated string starting on line {_line(text, start)}")


def _template_end(text: str, index: int, string_start: int) -> int:
    depth = 1
    length = len(text)
    while index < length:
        character = text[index]
        if character == '"':
            index = _string_end(text, index)
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise HCLError(f"unterminated string starting on line {_line(text, string_start)}")


def _heredoc_end(text: str, header: "re.Match") -> int:
    marker = header.group(2)
    position = header.end()
    length = len(text)
    while position <= length:
        line_end = text.find("\n", position)
        line_end = length if line_end == -1 else line_end
        if text[position:line_end].strip() == marker:
            return line_end
        if line_end == length:
            break
        position = line_end + 1
    raise HCLError(
        f"unterminated heredoc <<{marker} starting on line "
        f"{_line(text, header.start())}"
    )


def _expression_end(scanned: _Scanned, start: int, key: str) -> int:
    skeleton = scanned.skeleton
    depth = 0
    index = start
    length = len(skeleton)
    while index < length:
        if index in scanned.heredocs:
            index = scanned.heredocs[index]
            continue
        character = skeleton[index]
        if character in _OPENERS:
            depth += 1
        elif character in _CLOSERS:
            depth -= 1
            if depth < 0:
                return index
        elif character == "\n" and depth == 0:
            return index
        index += 1
    if depth > 0:
        raise HCLError(
            f"unterminated value for '{key}' starting on line {_line(skeleton, start)}"
        )
    return length


def _block_end(scanned: _Scanned, open_brace: int, key: str) -> int:
    skeleton = scanned.skeleton
    depth = 0
    index = open_brace
    length = len(skeleton)
    while index < length:
        if index in scanned.heredocs:
            index = scanned.heredocs[index]
            continue
        character = skeleton[index]
        if character in _OPENERS:
            depth += 1
        elif character in _CLOSERS:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise HCLError(
        f"unterminated block '{key}' starting on line {_line(skeleton, open_brace)}"
    )
