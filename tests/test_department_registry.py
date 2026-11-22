import pytest

from atlas_engine.capability_registry import CapabilityDefinition, CapabilityRegistry
from atlas_engine.department_registry import (
    DepartmentDefinition,
    DepartmentRegistry,
    build_default_department_registry,
)
from atlas_engine.identity_policy import AuthorizationDenied, RequestPrincipal


def _capabilities():
    return CapabilityRegistry([
        CapabilityDefinition(
            name="research.lookup",
            version="1",
            risk_class="read_only",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            output_schema={"type": "object", "properties": {}, "additionalProperties": False},
            required_scopes=("research:read",),
        )
    ])


def _department(**overrides):
    values = {
        "module_id": "finance",
        "display_name": "Finance",
        "owner": "Finance Department",
        "lifecycle_state": "active",
        "data_classification": "financial_confidential",
        "required_scopes": ("finance:access",),
    }
    values.update(overrides)
    return DepartmentDefinition(**values)


def _principal(scopes=frozenset({"finance:access"}), tenant_id="org-a"):
    return RequestPrincipal(
        issuer="https://identity.example",
        subject="user-1",
        tenant_id=tenant_id,
        membership_active=True,
        scopes=scopes,
    )


def test_default_registry_contains_the_planned_independent_departments():
    registry = build_default_department_registry(_capabilities())
    assert [item.module_id for item in registry.list_definitions()] == [
        "finance", "hospitality", "hr", "legal", "media", "professor", "trading", "velvet"
    ]
    assert registry.get("finance").lifecycle_state == "planned"
    assert registry.get("velvet").data_classification == "adult_sensitive"
    assert registry.get("trading").data_classification == "financial_confidential"


def test_planned_department_is_not_authorized_even_when_tenant_enables_it():
    registry = build_default_department_registry(_capabilities())
    with pytest.raises(AuthorizationDenied):
        registry.authorize(_principal(), "finance", {"finance"})


def test_active_department_requires_tenant_enablement_and_scope():
    registry = DepartmentRegistry([_department()], _capabilities())
    with pytest.raises(AuthorizationDenied):
        registry.authorize(_principal(), "finance", set())
    with pytest.raises(AuthorizationDenied):
        registry.authorize(_principal(frozenset()), "finance", {"finance"})
    assert registry.authorize(_principal(), "finance", {"finance"}) == registry.get("finance")


def test_department_manifest_does_not_grant_its_own_required_scope():
    registry = DepartmentRegistry([_department()], _capabilities())
    with pytest.raises(AuthorizationDenied):
        registry.authorize(_principal(frozenset()), "finance", {"finance"})


def test_inactive_membership_is_denied():
    registry = DepartmentRegistry([_department()], _capabilities())
    principal = RequestPrincipal(
        issuer="https://identity.example",
        subject="user-1",
        tenant_id="org-a",
        membership_active=False,
        scopes=frozenset({"finance:access"}),
    )
    with pytest.raises(AuthorizationDenied):
        registry.authorize(principal, "finance", {"finance"})


def test_untrusted_or_malformed_tenant_module_configuration_is_denied():
    registry = DepartmentRegistry([_department()], _capabilities())
    with pytest.raises(AuthorizationDenied):
        registry.authorize(_principal(), "finance", "finance")
    with pytest.raises(AuthorizationDenied):
        registry.authorize(_principal(), "finance", {"../finance"})


def test_unknown_duplicate_and_self_dependencies_are_rejected():
    with pytest.raises(ValueError, match="unknown dependency"):
        DepartmentRegistry([_department(dependencies=("missing",))], _capabilities())
    with pytest.raises(ValueError, match="Duplicate department"):
        DepartmentRegistry([_department(), _department()], _capabilities())
    with pytest.raises(ValueError, match="cannot depend on itself"):
        _department(dependencies=("finance",))


def test_dependency_cycles_are_rejected():
    finance = _department(dependencies=("hospitality",))
    hospitality = DepartmentDefinition(
        module_id="hospitality",
        display_name="Hospitality",
        owner="Hospitality Department",
        dependencies=("finance",),
    )
    with pytest.raises(ValueError, match="cycles"):
        DepartmentRegistry([finance, hospitality], _capabilities())


def test_unregistered_capabilities_are_rejected():
    with pytest.raises(ValueError, match="unregistered capability"):
        DepartmentRegistry(
            [_department(capabilities=(("not.installed", "1"),))],
            _capabilities(),
        )


def test_registry_is_immutable_and_rejects_unvalidated_objects():
    registry = DepartmentRegistry([_department()], _capabilities())
    with pytest.raises(AttributeError):
        registry.register(_department())
    with pytest.raises(ValueError, match="validated department"):
        DepartmentRegistry([{"module_id": "untrusted"}], _capabilities())


def test_manifest_validation_rejects_unknown_states_and_duplicate_scopes():
    with pytest.raises(ValueError, match="lifecycle"):
        _department(lifecycle_state="launch_now")
    with pytest.raises(ValueError, match="unique"):
        _department(required_scopes=("finance:access", "finance:access"))


def test_department_capabilities_are_bound_to_the_existing_capability_catalogue():
    registry = DepartmentRegistry(
        [_department(capabilities=(("research.lookup", "1"),))],
        _capabilities(),
    )
    assert registry.get("finance").capabilities == (("research.lookup", "1"),)
