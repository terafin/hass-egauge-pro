"""Unit tests for eGauge Pro entity naming and legacy-device cleanup.

Two regressions are pinned here:

1. Entities must not declare ``device_info``. Home Assistant composes a
   device-bound entity's displayed name as ``"<device name> <entity name>"``,
   so declaring the meter as a device prefixed every Energy-dashboard label
   with "eGauge" ("eGauge Pool", "eGauge Jacuzzi", ...).

2. Installs upgraded from <= 0.2.6 still hold that device row in the registry.
   ``_remove_legacy_device`` must detach its entities and drop it, or the
   prefix survives the upgrade.

``entity.py`` imports Home Assistant helpers, which are not installed in this
test environment, so its source is asserted directly rather than imported.
"""

from __future__ import annotations

import ast
from pathlib import Path

_COMPONENTS = Path(__file__).resolve().parents[1] / "custom_components" / "egauge_pro"
_ENTITY_PY = _COMPONENTS / "entity.py"
_INIT_PY = _COMPONENTS / "__init__.py"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _base_class(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found")


def test_base_entity_does_not_assign_device_info() -> None:
    """No entity may attach itself to a device, or HA prefixes its name."""
    tree = _parse(_ENTITY_PY)
    cls = _base_class(tree, "EgaugeProEntity")

    offenders = [
        node.attr
        for node in ast.walk(cls)
        if isinstance(node, ast.Attribute) and node.attr == "_attr_device_info"
    ]
    assert offenders == [], (
        "EgaugeProEntity must not set _attr_device_info: a device-bound entity is "
        "rendered as '<device name> <entity name>', which put 'eGauge' in front of "
        "every Energy dashboard label"
    )


def test_base_entity_keeps_bare_friendly_name() -> None:
    """has_entity_name must stay False so the friendly name is the register."""
    tree = _parse(_ENTITY_PY)
    cls = _base_class(tree, "EgaugeProEntity")

    values = [
        node.value.value
        for node in cls.body
        if isinstance(node, ast.Assign)
        for tgt in node.targets
        if isinstance(tgt, ast.Name) and tgt.id == "_attr_has_entity_name"
        and isinstance(node.value, ast.Constant)
    ]
    assert values == [False], (
        "EgaugeProEntity._attr_has_entity_name must be False so the displayed "
        f"name is the bare register; found {values!r}"
    )


def test_legacy_device_is_removed_on_setup() -> None:
    """An install upgraded from <= 0.2.6 must lose its stale device row."""
    tree = _parse(_INIT_PY)
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "_remove_legacy_device" in funcs, (
        "installs upgraded from 0.2.6 keep a device row whose name would still "
        "prefix every entity; setup must remove it"
    )

    setup = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "async_setup_entry"
    )
    called = {
        n.func.id
        for n in ast.walk(setup)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "_remove_legacy_device" in called, (
        "async_setup_entry must call _remove_legacy_device so existing installs "
        "are repaired on reload, not only fresh ones"
    )


def test_legacy_device_helper_detaches_entities_before_removal() -> None:
    """Entities are detached first; removing a device with entities would fail."""
    tree = _parse(_INIT_PY)
    helper = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_remove_legacy_device"
    )
    body = ast.get_source_segment(_INIT_PY.read_text(encoding="utf-8"), helper) or ""
    assert "async_update_entity" in body and "device_id=None" in body, (
        "the helper must clear each entity's device_id before removing the device"
    )
    assert "async_remove_device" in body, "the helper must remove the device row"
