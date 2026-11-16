"""Provider-neutral, fail-closed billing readiness evidence evaluator.

This module does not create checkout sessions, verify provider accounts, process
webhooks, grant entitlements, or enable charging. A future server-side adapter
must supply evidence references only after independently verifying each gate.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MAX_EVIDENCE_REFERENCE_CHARS = 256

REQUIRED_LIVE_READINESS_GATES = (
    "provider_selected",
    "dedicated_atlas_account_verified",
    "test_live_credentials_and_webhooks_isolated",
    "approved_product_price_currency_and_cadence",
    "test_checkout_completed",
    "webhook_signature_verification_passed",
    "webhook_event_idempotency_passed",
    "delayed_and_out_of_order_reconciliation_passed",
    "tenant_billing_data_isolation_passed",
    "subscription_entitlement_state_matrix_passed",
    "cancellation_refund_and_dispute_flows_tested",
    "audit_secret_redaction_and_data_minimisation_passed",
    "monitoring_backup_incident_and_rollback_controls_ready",
    "privacy_terms_tax_and_consumer_obligations_reviewed",
    "independent_billing_security_review_passed",
)


def evaluate_live_billing_readiness(
    evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return a redacted readiness report; never authorise or enable live charging.

    Evidence is an internal server-side input. Each gate must be represented
    by a mapping with passed=True and a non-empty, non-secret reference.
    Missing, malformed, false, or unreferenced evidence fails closed.
    """
    supplied = evidence if isinstance(evidence, Mapping) else {}
    results = []
    for gate in REQUIRED_LIVE_READINESS_GATES:
        item = supplied.get(gate)
        passed = (
            isinstance(item, Mapping)
            and item.get("passed") is True
            and isinstance(item.get("reference"), str)
            and 0 < len(item["reference"].strip()) <= MAX_EVIDENCE_REFERENCE_CHARS
        )
        results.append({
            "gate": gate,
            "status": "pass" if passed else "blocked",
        })

    blocked = [item["gate"] for item in results if item["status"] != "pass"]
    return {
        "schema_version": 1,
        "overall_status": "ready_for_human_release_review" if not blocked else "blocked",
        "required_gate_count": len(results),
        "passed_gate_count": len(results) - len(blocked),
        "blocked_gates": blocked,
        "gates": results,
        "live_release_approval": "not_requested",
        "live_charging_enabled": False,
        "limitations": [
            "This is a readiness evidence evaluator, not a payment-provider integration.",
            "Evidence must be produced by trusted server-side checks and reviewed test records; browser or model supplied evidence is not authoritative.",
            "A passing report is not approval to configure live credentials, register a live webhook, create a live checkout, or charge a customer.",
            "Provider account identity, credential mode, webhook signatures, and subscription state must be independently verified by the future provider adapter.",
        ],
    }
