"""Trusted, immutable department catalogue for AtlasOnePro.

This registry describes installed department modules; it does not grant access,
load plugins, create tenants, or execute department capabilities. Tenant enablement
must come from trusted server-side configuration and every operation must still
pass its capability-level authorisation checks.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Iterable, Mapping

from .capability_registry import CapabilityRegistry
from .identity_policy import (
    AuthorizationDenied,
    RequestPrincipal,
    authorize_tenant_resource,
)


_MODULE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
_LIFECYCLE_STATES = frozenset({
    "planned",
    "disabled",
    "sandbox",
    "pilot",
    "active",
})
_DATA_CLASSIFICATIONS = frozenset({
    "public",
    "internal",
    "confidential",
    "financial_confidential",
    "restricted",
    "special_category",
    "adult_sensitive",
})
_AVAILABLE_STATES = frozenset({"pilot", "active"})


@dataclass(frozen=True)
class DepartmentDefinition:
    """One application-owned department manifest."""

    module_id: str
    display_name: str
    owner: str
    version: str = "1"
    lifecycle_state: str = "planned"
    data_classification: str = "internal"
    description: str = ""
    required_scopes: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    capabilities: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("module_id", "display_name", "owner", "version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} is required.")
            object.__setattr__(self, field_name, value.strip())

        if not _MODULE_ID.fullmatch(self.module_id):
            raise ValueError("module_id must be a stable lowercase identifier.")
        if len(self.display_name) > 120 or len(self.owner) > 120:
            raise ValueError("Department display name and owner must not exceed 120 characters.")
        if len(self.version) > 64:
            raise ValueError("Department version must not exceed 64 characters.")
        if self.lifecycle_state not in _LIFECYCLE_STATES:
            raise ValueError("Unsupported department lifecycle state.")
        if self.data_classification not in _DATA_CLASSIFICATIONS:
            raise ValueError("Unsupported department data classification.")
        if not isinstance(self.description, str) or len(self.description) > 1000:
            raise ValueError("Department description must not exceed 1000 characters.")

        for field_name in ("required_scopes", "dependencies", "capabilities"):
            value = getattr(self, field_name)
            if not isinstance(value, (tuple, list)):
                raise ValueError(f"{field_name} must be a list or tuple.")
            object.__setattr__(self, field_name, tuple(value))

        if any(
            not isinstance(scope, str) or not scope.strip() or len(scope) > 128
            for scope in self.required_scopes
        ):
            raise ValueError("Department scopes must be non-empty strings of at most 128 characters.")
        if len(set(self.required_scopes)) != len(self.required_scopes):
            raise ValueError("Department scopes must be unique.")
        if any(
            not isinstance(dependency, str) or not _MODULE_ID.fullmatch(dependency)
            for dependency in self.dependencies
        ):
            raise ValueError("Department dependencies must be stable module identifiers.")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("Department dependencies must be unique.")
        if self.module_id in self.dependencies:
            raise ValueError("A department cannot depend on itself.")

        normalized_capabilities = []
        for item in self.capabilities:
            if (
                not isinstance(item, (tuple, list))
                or len(item) != 2
                or any(not isinstance(part, str) or not part.strip() for part in item)
            ):
                raise ValueError("Department capabilities must be (name, version) pairs.")
            normalized_capabilities.append((item[0].strip(), item[1].strip()))
        if len(set(normalized_capabilities)) != len(normalized_capabilities):
            raise ValueError("Department capability references must be unique.")
        object.__setattr__(self, "capabilities", tuple(sorted(normalized_capabilities)))
        object.__setattr__(self, "required_scopes", tuple(sorted(self.required_scopes)))
        object.__setattr__(self, "dependencies", tuple(sorted(self.dependencies)))


class DepartmentRegistry:
    """Read-only catalogue built exclusively from trusted application definitions."""

    def __init__(
        self,
        definitions: tuple[DepartmentDefinition, ...] | list[DepartmentDefinition],
        capability_registry: CapabilityRegistry,
    ) -> None:
        if not isinstance(definitions, (tuple, list)):
            raise ValueError("Department definitions must be a list or tuple.")
        if not isinstance(capability_registry, CapabilityRegistry):
            raise ValueError("A trusted capability registry is required.")

        indexed: dict[str, DepartmentDefinition] = {}
        for definition in definitions:
            if not isinstance(definition, DepartmentDefinition):
                raise ValueError("Registry accepts only validated department definitions.")
            if definition.module_id in indexed:
                raise ValueError("Duplicate department module ID.")
            for capability_name, capability_version in definition.capabilities:
                if capability_registry.get(capability_name, capability_version) is None:
                    raise ValueError("Department references an unregistered capability.")
            indexed[definition.module_id] = definition

        for definition in indexed.values():
            if any(dependency not in indexed for dependency in definition.dependencies):
                raise ValueError("Department references an unknown dependency.")

        self._validate_dependency_graph(indexed)
        self._definitions: Mapping[str, DepartmentDefinition] = MappingProxyType(indexed)

    @staticmethod
    def _validate_dependency_graph(
        definitions: Mapping[str, DepartmentDefinition],
    ) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(module_id: str) -> None:
            if module_id in visiting:
                raise ValueError("Department dependencies must not contain cycles.")
            if module_id in visited:
                return
            visiting.add(module_id)
            for dependency in definitions[module_id].dependencies:
                visit(dependency)
            visiting.remove(module_id)
            visited.add(module_id)

        for module_id in definitions:
            visit(module_id)

    def get(self, module_id: str) -> DepartmentDefinition | None:
        return self._definitions.get(module_id)

    def list_definitions(self) -> tuple[DepartmentDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))

    def authorize(
        self,
        principal: RequestPrincipal,
        module_id: str,
        enabled_module_ids: Iterable[str],
    ) -> DepartmentDefinition:
        """Resolve an enabled department for a verified principal.

        enabled_module_ids must be loaded from trusted server-side tenant
        configuration. This check grants no capability permission; each
        capability must independently enforce its own required scopes.
        """
        if not isinstance(principal, RequestPrincipal):
            raise AuthorizationDenied("Verified request principal required.")
        if not isinstance(module_id, str) or not module_id.strip():
            raise AuthorizationDenied("Department access denied.")
        if isinstance(enabled_module_ids, (str, bytes)):
            raise AuthorizationDenied("Trusted department configuration required.")
        try:
            enabled = frozenset(enabled_module_ids)
        except (TypeError, ValueError):
            raise AuthorizationDenied("Trusted department configuration required.") from None
        if any(not isinstance(item, str) or not _MODULE_ID.fullmatch(item) for item in enabled):
            raise AuthorizationDenied("Trusted department configuration required.")

        definition = self.get(module_id.strip())
        if (
            definition is None
            or definition.lifecycle_state not in _AVAILABLE_STATES
            or definition.module_id not in enabled
        ):
            raise AuthorizationDenied("Department access denied.")

        for dependency_id in definition.dependencies:
            dependency = self.get(dependency_id)
            if (
                dependency is None
                or dependency.lifecycle_state not in _AVAILABLE_STATES
                or dependency_id not in enabled
            ):
                raise AuthorizationDenied("Department dependency is unavailable.")

        authorize_tenant_resource(
            principal,
            principal.tenant_id,
            definition.required_scopes,
        )
        return definition

    def __len__(self) -> int:
        return len(self._definitions)


def build_default_department_registry(
    capability_registry: CapabilityRegistry,
) -> DepartmentRegistry:
    """Build the initial catalogue; planned arms remain unavailable by default."""
    professor_capabilities = tuple(
        definition.identity for definition in capability_registry.list_definitions()
    )
    definitions = [
        DepartmentDefinition(
            module_id="professor",
            display_name="Professor Core",
            owner="AtlasOnePro Core",
            lifecycle_state="active",
            data_classification="internal",
            description="Central reasoning, planning and controlled orchestration.",
            capabilities=professor_capabilities,
        ),
        DepartmentDefinition(
            module_id="finance",
            display_name="Finance",
            owner="Finance Department",
            lifecycle_state="planned",
            data_classification="financial_confidential",
            description="Business bookkeeping, budgets, invoices, cash flow and management reporting.",
            required_scopes=("finance:access",),
        ),
        DepartmentDefinition(
            module_id="hospitality",
            display_name="Hospitality Hub",
            owner="Hospitality Department",
            lifecycle_state="planned",
            data_classification="confidential",
            description="Catering operations and the controlled Quick Chef integration.",
            required_scopes=("hospitality:access",),
        ),
        DepartmentDefinition(
            module_id="hr",
            display_name="Human Resources",
            owner="HR Department",
            lifecycle_state="planned",
            data_classification="restricted",
            description="Recruitment, onboarding, employee records and training.",
            required_scopes=("hr:access",),
        ),
        DepartmentDefinition(
            module_id="legal",
            display_name="Legal Operations",
            owner="Legal Department",
            lifecycle_state="planned",
            data_classification="restricted",
            description="Contracts, matters, policies, deadlines and compliance evidence.",
            required_scopes=("legal:access",),
        ),
        DepartmentDefinition(
            module_id="velvet",
            display_name="Velvet",
            owner="Velvet Operations",
            lifecycle_state="planned",
            data_classification="adult_sensitive",
            description="Isolated 18+ product, consent, age assurance and moderation operations.",
            required_scopes=("velvet:access",),
        ),
        DepartmentDefinition(
            module_id="media",
            display_name="Media Studio",
            owner="Media Department",
            lifecycle_state="planned",
            data_classification="confidential",
            description="Creative briefs, media assets, review and publishing workflows.",
            required_scopes=("media:access",),
        ),
        DepartmentDefinition(
            module_id="trading",
            display_name="Personal Finance and Trading",
            owner="Personal Finance Integration",
            lifecycle_state="planned",
            data_classification="financial_confidential",
            description="Optional read-only personal portfolio connection, separate from business finance.",
            required_scopes=("trading:read",),
        ),
    ]
    return DepartmentRegistry(definitions, capability_registry)
