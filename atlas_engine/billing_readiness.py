"""Fail-closed billing readiness checklist; never authorizes live charging.

This is a deterministic planning aid only. Its inputs are checklist assertions,
not independently verified evidence, and its output must never be used as an
authorization decision or to enable a payment provider.
"""
from dataclasses import dataclass
from typing import Mapping


REQUIRED_BILLING_GATES = (
    "dedicated_atlas_account",
    "test_live_environment_isolation",
    "approved_products_prices_currency",
    "verified_identity_and_tenant_ownership",
    "signed_webhook_verification",
    "durable_idempotent_event_ledger",
    "subscription_reconciliation",
    "server_derived_entitlement_policy",
    "cancellation_failure_refund_dispute_flows",
    "customer_portal_and_support_process",
    "monitoring_audit_and_incident_response",
    "backup_restore_and_rollback_rehearsal",
    "privacy_terms_tax_and_legal_review",
    "independent_security_review",
    "complete_test_mode_acceptance_journey",
)


@dataclass(frozen=True)
class BillingReadinessReport:
    status: str
    passed_gates: tuple[str, ...]
    blocked_gates: tuple[str, ...]
    live_activation_permitted: bool = False


def evaluate_billing_readiness(
    gate_results: Mapping[str, bool],
) -> BillingReadinessReport:
    """Summarize owner-supplied checklist assertions without enabling billing.

    Missing gates are blocked. Unknown gate names and non-boolean values are
    rejected so misspellings or truthy strings cannot create a false pass.
    Even when every assertion is true, the result only permits a separate
    human release review; it never permits live activation.
    """
    if not isinstance(gate_results, Mapping):
        raise TypeError("gate_results must be a mapping of gate names to booleans")

    unknown = set(gate_results) - set(REQUIRED_BILLING_GATES)
    if unknown:
        raise ValueError(f"Unknown billing readiness gates: {', '.join(sorted(unknown))}")

    invalid = [name for name, value in gate_results.items() if type(value) is not bool]
    if invalid:
        raise TypeError(f"Billing readiness gates must be booleans: {', '.join(sorted(invalid))}")

    passed = tuple(name for name in REQUIRED_BILLING_GATES if gate_results.get(name) is True)
    blocked = tuple(name for name in REQUIRED_BILLING_GATES if gate_results.get(name) is not True)
    status = "eligible_for_human_review" if not blocked else "blocked"

    return BillingReadinessReport(
        status=status,
        passed_gates=passed,
        blocked_gates=blocked,
        live_activation_permitted=False,
    )
