"""YAML loading with YAML 1.2 booleans.

PyYAML implements YAML 1.1, where the bare words `on`, `off`, `yes`, `no`, `y`, `n` are booleans.
Behavior packs use `on: fallen` (CLAUDE.md §6.2), and the Studio's `yaml` package speaks 1.2,
so the runtime must read those words as strings too. Only `true`/`false` remain booleans.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


class Yaml12Loader(yaml.SafeLoader):
    pass


Yaml12Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)
# Drop the YAML 1.1 bool resolver (registered for the first letters y Y n N o O t T f F).
for first in "yYnNoOtTfF":
    resolvers = Yaml12Loader.yaml_implicit_resolvers.get(first, [])
    Yaml12Loader.yaml_implicit_resolvers[first] = [
        (tag, regexp)
        for tag, regexp in resolvers
        if tag != "tag:yaml.org,2002:bool" or regexp.pattern.startswith("^(?:true|True|TRUE")
    ]


def load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return yaml.load(fh, Loader=Yaml12Loader)  # noqa: S506 - SafeLoader subclass


def load_yaml_str(text: str) -> Any:
    return yaml.load(text, Loader=Yaml12Loader)


class Yaml12Dumper(yaml.SafeDumper):
    """Writes what the loader reads: bare `on:` keys, block style, indented lists."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        return super().increase_indent(flow, False)


Yaml12Dumper.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)
for first in "yYnNoOtTfF":
    resolvers = Yaml12Dumper.yaml_implicit_resolvers.get(first, [])
    Yaml12Dumper.yaml_implicit_resolvers[first] = [
        (tag, regexp)
        for tag, regexp in resolvers
        if tag != "tag:yaml.org,2002:bool" or regexp.pattern.startswith("^(?:true|True|TRUE")
    ]


def dump_yaml(data: Any) -> str:
    return yaml.dump(
        data,
        Dumper=Yaml12Dumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=100,
    )
