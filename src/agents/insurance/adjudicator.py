from datetime import date, datetime
from typing import List, Tuple
from .models import Claim, AdjudicatedItem, AdjudicationResult
from .db import get_policy_by_ssn, get_usage, increment_usage
from .rag import match_procedure

def _within(d: date, start: str, end: str) -> bool:
    s = datetime.fromisoformat(start).date()
    e = datetime.fromisoformat(end).date()
    return s <= d <= e


def _piecewise_coverage(amount: float) -> float:
    """
    Tiers:
      - first $500 → 100%
      - next $500 → 80%
      - next $1,000 → 50%
      - remainder → 30%
    """
    remain = amount
    covered = 0.0
    tiers = [(500, 1.0), (500, 0.8), (1000, 0.5), (float("inf"), 0.3)]
    for cap, pct in tiers:
        if remain <= 0:
            break
        chunk = min(remain, cap if cap != float("inf") else remain)
        covered += chunk * pct
        remain -= chunk
    return round(covered, 2)


def _fmt_usd(x: float) -> str:
    return f"${x:,.2f}"


def adjudicate(claim: Claim, write_usage: bool = False) -> AdjudicationResult:
    policy = get_policy_by_ssn(claim.patient_ssn)
    if not policy:
        return AdjudicationResult(
            policy_id=None,
            eligible=False,
            reason="Policy not found",
            items=[],
            total_payable=0.0,
            pretty_message="No policy found for the given SSN.",
        )

    policy_id = policy.get("policy_id") or policy.get("policyId")

    elig = policy.get("eligibility", {})
    active_from = elig.get("active_from") or elig.get("activeFrom")
    active_to = elig.get("active_to") or elig.get("activeTo")

    if not active_from or not active_to or not _within(claim.date_of_service, active_from, active_to):
        return AdjudicationResult(
            policy_id=policy_id,
            eligible=False,
            reason="Out of eligibility window" if (active_from and active_to) else "Missing eligibility period",
            items=[],
            total_payable=0.0,
            pretty_message="Service date is outside policy eligibility window." if (active_from and active_to) else "Eligibility period is missing on the policy.",
        )

    year = claim.date_of_service.year
    limits = policy.get("limits", {})

    items: List[AdjudicatedItem] = []
    total_payable = 0.0

    # Track totals for clarity in the message
    total_patient_resp_allowed = 0.0
    total_potential_balance_bill = 0.0

    # Build pretty message lines
    pretty_lines: List[str] = []

    for p in claim.procedures:
        canon, category, ref_price, dbg = match_procedure(p.name)

        billed_float = float(p.billed)
        allowed = min(billed_float, float(ref_price))

        # Limits: support per_year (old) or perYear (camelCase)
        lim_conf = limits.get(category, {}) if isinstance(limits, dict) else {}
        limit = lim_conf.get("per_year")
        if limit is None:
            limit = lim_conf.get("perYear")

        used = get_usage(claim.patient_ssn, category, year) if limit is not None else 0
        remaining = None if limit is None else max(0, int(limit) - int(used))
        limit_reached = (limit is not None and remaining <= 0)

        if limit_reached:
            # Your requirement: if limit is reached, insurer pays $0,
            # patient owes the entire allowed amount.
            payable = 0.0
            note = (
                f"LIMIT REACHED for '{category}'. Insurer pays $0; patient owes the allowed amount."
                f" (used={used}/{limit})"
            )
        else:
            payable = _piecewise_coverage(allowed)
            if limit is not None:
                note = f"Matched to '{canon}' (ref {ref_price}). Usage {used}/{limit} this year."
            else:
                note = f"Matched to '{canon}' (ref {ref_price})."

        # Patient responsibility on allowed portion:
        patient_on_allowed = max(0.0, allowed - payable)
        # Potential balance bill (only if out-of-network):
        potential_balance_bill = max(0.0, billed_float - allowed)

        # Accumulate totals
        total_payable += payable
        total_patient_resp_allowed += patient_on_allowed
        total_potential_balance_bill += potential_balance_bill

        # Save item JSON (unchanged shape)
        items.append(
            AdjudicatedItem(
                claim_name=p.name,
                matched_name=canon,
                category=category,
                billed=billed_float,
                ref_price=float(ref_price),
                allowed_amount=float(allowed),
                payable_amount=float(payable),
                notes=note + f"\n{dbg}",
            )
        )

        # Pretty message lines
        pretty_lines.append(f"• {p.name} → matched '{canon}' [{category}]")
        pretty_lines.append(
            f"  Billed { _fmt_usd(billed_float) } | Reference { _fmt_usd(ref_price) } | Allowed { _fmt_usd(allowed) } | Payable { _fmt_usd(payable) }"
        )
        if limit is None:
            pretty_lines.append("  Limit: no annual limit")
        else:
            status = "LIMIT REACHED" if limit_reached else "OK"
            pretty_lines.append(f"  Limit: used {used}/{int(limit)} – status: {status}")
        if limit_reached:
            pretty_lines.append(f"  → Because the limit is reached: insurer pays $0; patient owes { _fmt_usd(allowed) } (allowed amount).")
        else:
            pretty_lines.append(
                f"  Patient responsibility (allowed portion): { _fmt_usd(patient_on_allowed) }"
            )
        pretty_lines.append(
            f"  Potential balance bill (if out-of-network): { _fmt_usd(potential_balance_bill) }"
        )

    header = [
        f"Dear {claim.hospital_name},",
        f"We reviewed the claim for {claim.full_name} (SSN ending {claim.patient_ssn[-4:]}) dated {claim.date_of_service.isoformat()}.",
        "Adjudication summary:",
    ]
    footer = [
        f"TOTAL PAYABLE (insurer): { _fmt_usd(round(total_payable, 2)) }",
        f"PATIENT RESPONSIBILITY (allowed portion): { _fmt_usd(round(total_patient_resp_allowed, 2)) }",
        f"POTENTIAL BALANCE BILL (if out-of-network): { _fmt_usd(round(total_potential_balance_bill, 2)) }",
        "Notes: Coverage tiers applied: ≤$500 @100%, next $500 @80%, next $1,000 @50%, remainder @30%.",
        "If out-of-network, provider may bill the balance (difference between billed and allowed).",
        "If the annual limit is reached for a category, insurer pays $0 for that item and the patient owes the allowed amount.",
    ]
    pretty = "\n".join(header + pretty_lines + footer)

    if write_usage:
        # Only increment usage for items that were within limit
        for it in items:
            # Find per-category limit to decide if we should count usage
            lim_conf = limits.get(it.category, {}) if isinstance(limits, dict) else {}
            limit = lim_conf.get("per_year")
            if limit is None:
                limit = lim_conf.get("perYear")
            used = get_usage(claim.patient_ssn, it.category, year) if limit is not None else 0
            remaining = None if limit is None else max(0, int(limit) - int(used))
            if limit is not None and remaining > 0:
                increment_usage(claim.patient_ssn, it.category, year, 1)

    return AdjudicationResult(
        policy_id=policy_id,
        eligible=True,
        reason=None,
        items=items,
        total_payable=round(total_payable, 2),
        pretty_message=pretty,
    )
