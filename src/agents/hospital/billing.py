import types, difflib
from typing import Dict, Any, Optional, List
from datetime import datetime

# -------- Tariff loading --------

def _first_numeric_dict(mod: types.ModuleType) -> Optional[Dict[str, float]]:
    for _, v in vars(mod).items():
        if isinstance(v, dict) and v:
            try:
                if all(isinstance(x, (int, float)) for x in v.values()):
                    return {str(name): float(val) for name, val in v.items()}
            except Exception:
                continue
    return None

def load_tariff() -> Dict[str, float]:
    """Import tariff data from this package's tariff.py only."""
    from . import tariff as mod  # src/agents/hospital/tariff.py
    d = _first_numeric_dict(mod)
    if not d:
        raise RuntimeError("No suitable price dict found in tariff.py (expects a dict with numeric values).")
    return d


# -------- Matching & pricing helpers --------

def best_tariff_match(proc_free_text: str, choices: List[str], cutoff: float = 0.6) -> Optional[str]:
    proc = (proc_free_text or "").strip()
    if not proc:
        return None
    best, best_ratio = None, 0.0
    for c in choices:
        ratio = difflib.SequenceMatcher(None, proc.lower(), c.lower()).ratio()
        if ratio > best_ratio:
            best, best_ratio = c, ratio
    return best if best and best_ratio >= cutoff else None

def price_for(proc_name: str, tariff: Dict[str, float]) -> Optional[float]:
    return float(tariff.get(proc_name)) if proc_name in tariff else None


# -------- Normalization & totals --------

TAX_RATE = 0.15  # 15%

def _ensure_proc_fields(invoice: Dict[str, Any], tariff: Optional[Dict[str, float]] = None) -> None:
    """
    Ensure each line has: name, tariff (full price), discount (currency), billed (net).
    If tariff dict is provided, it takes precedence for the full price.
    """
    for p in invoice.get("procedures", []):
        name = p.get("name", "")
        full_price = None
        if tariff and name in tariff:
            full_price = float(tariff[name])
        else:
            # fallbacks: explicit tariff, then billed as last resort
            full_price = float(p.get("tariff", p.get("billed", 0.0) or 0.0))
        p["tariff"] = round(float(full_price), 2)
        p["discount"] = round(float(p.get("discount", 0.0) or 0.0), 2)
        net = p["tariff"] - p["discount"]
        p["billed"] = round(net if net > 0 else 0.0, 2)

def recompute_totals(invoice: Dict[str, Any]) -> None:
    """Compute subtotal (tariff), discounts_total, tax, and total."""
    _ensure_proc_fields(invoice)
    subtotal_tariff = round(sum(p.get("tariff", 0.0) for p in invoice.get("procedures", [])), 2)
    discounts_total = round(sum(p.get("discount", 0.0) for p in invoice.get("procedures", [])), 2)
    subtotal_after_discount = round(sum(p.get("billed", 0.0) for p in invoice.get("procedures", [])), 2)
    tax = round(subtotal_after_discount * TAX_RATE, 2)
    total = round(subtotal_after_discount + tax, 2)
    invoice["subtotal"] = subtotal_tariff
    invoice["discounts_total"] = discounts_total
    invoice["tax_rate"] = TAX_RATE
    invoice["tax"] = tax
    invoice["total"] = total


# -------- Invoice construction & printing --------

def build_initial_invoice(extracted: Dict[str, Any], tariff: Dict[str, float]) -> Dict[str, Any]:
    matched = []
    choices = list(tariff.keys())
    for raw in extracted.get("procedures", []):
        match = best_tariff_match(raw, choices)
        if match is not None:
            price = price_for(match, tariff)
            if price is not None:
                matched.append({"name": match, "tariff": float(price), "discount": 0.0, "billed": float(price)})

    date_of_service = extracted.get("date of service") or datetime.today().strftime("%Y-%m-%d")
    invoice = {
        "patient name": extracted.get("patient name", ""),
        "patient SSN": extracted.get("patient SSN", ""),
        "hospital name": extracted.get("hospital name") or "City Hospital",
        "date of service": date_of_service,
        "diagnose": extracted.get("diagnose", ""),
        "procedures": matched,
    }
    # normalize & totals
    _ensure_proc_fields(invoice, tariff)
    recompute_totals(invoice)
    return invoice

def pretty_invoice(invoice: Dict[str, Any]) -> str:
    # make sure numbers are up-to-date for the textual view
    _ensure_proc_fields(invoice)
    recompute_totals(invoice)

    lines = []
    lines.append(f"Patient: {invoice.get('patient name','-')}  SSN: {invoice.get('patient SSN','-')}")
    lines.append(f"Hospital: {invoice.get('hospital name','-')}  Date: {invoice.get('date of service','-')}")
    lines.append(f"Diagnose: {invoice.get('diagnose','-')}")
    lines.append("Procedures:")
    for idx, p in enumerate(invoice.get("procedures", []), start=1):
        t = f"{p.get('tariff',0):.2f}"
        d = f"{p.get('discount',0):.2f}"
        b = f"{p.get('billed',0):.2f}"
        lines.append(f"  {idx}. {p['name']} | tariff: {t} | discount: {d} | billed: {b}")
    lines.append(f"Subtotal: {invoice.get('subtotal',0):.2f}")
    lines.append(f"Discounts: {invoice.get('discounts_total',0):.2f}")
    lines.append(f"Tax ({int(TAX_RATE*100)}%): {invoice.get('tax',0):.2f}")
    lines.append(f"TOTAL: {invoice.get('total',0):.2f}")
    return "\n".join(lines)


# -------- Action helpers --------

def apply_discount(invoice: Dict[str, Any], percent: float) -> str:
    """
    Apply a percentage discount to ALL procedures.
    Keeps tariff fixed, increases discount (currency), recomputes billed and totals.
    Returns a status message including the total currency deducted.
    """
    _ensure_proc_fields(invoice)
    before = sum(p.get("discount", 0.0) for p in invoice.get("procedures", []))
    for p in invoice.get("procedures", []):
        p["discount"] = round(p.get("discount", 0.0) + p["tariff"] * (percent / 100.0), 2)
    recompute_totals(invoice)
    after = sum(p.get("discount", 0.0) for p in invoice.get("procedures", []))
    saved = round(after - before, 2)
    return f"Applied discount of {percent}% to all procedures (saved {saved:.2f})."

def apply_discount_to_index(invoice: Dict[str, Any], percent: float, index_1based: int) -> str:
    _ensure_proc_fields(invoice)
    i = index_1based - 1
    if i < 0 or i >= len(invoice.get("procedures", [])):
        return f"Index {index_1based} out of range (1..{len(invoice['procedures'])})."
    p = invoice["procedures"][i]
    add = round(p["tariff"] * (percent / 100.0), 2)
    p["discount"] = round(p.get("discount", 0.0) + add, 2)
    recompute_totals(invoice)
    return f"Applied discount of {percent}% to procedure #{index_1based} ({p.get('name','')}) (saved {add:.2f})."

def apply_discount_to_name(invoice: Dict[str, Any], percent: float, name: str) -> str:
    _ensure_proc_fields(invoice)
    for p in invoice.get("procedures", []):
        if p.get("name", "").lower() == (name or "").lower():
            add = round(p["tariff"] * (percent / 100.0), 2)
            p["discount"] = round(p.get("discount", 0.0) + add, 2)
            recompute_totals(invoice)
            return f"Applied discount of {percent}% to '{name}' (saved {add:.2f})."
    return f"Not found: {name}"

def add_procedure_exact(invoice: Dict[str, Any], tariff: Dict[str, float], exact_name: str) -> str:
    if exact_name not in tariff:
        return f"No exact tariff named: {exact_name}"
    price = float(tariff[exact_name])
    invoice["procedures"].append({"name": exact_name, "tariff": price, "discount": 0.0, "billed": price})
    recompute_totals(invoice)
    return f"Added: {exact_name} ({price})"

def add_procedure_free_text(invoice: Dict[str, Any], tariff: Dict[str, float], free_text: str) -> str:
    match = best_tariff_match(free_text, list(tariff.keys()))
    if not match:
        return f"No close tariff match found for: {free_text}"
    price = price_for(match, tariff)
    if price is None:
        return f"No price found for: {match}"
    price = float(price)
    invoice["procedures"].append({"name": match, "tariff": price, "discount": 0.0, "billed": price})
    recompute_totals(invoice)
    return f"Added: {match} ({price})"

def remove_procedure_by_index(invoice: Dict[str, Any], index: int) -> str:
    if index < 1 or index > len(invoice["procedures"]):
        return f"Index {index} out of range (1..{len(invoice['procedures'])})."
    removed = invoice["procedures"].pop(index-1)
    recompute_totals(invoice)
    return f"Removed: {removed['name']}"

def remove_procedure_by_name(invoice: Dict[str, Any], name: str) -> str:
    before = len(invoice["procedures"])
    invoice["procedures"] = [p for p in invoice["procedures"] if p.get("name") != name]
    after = len(invoice["procedures"])
    recompute_totals(invoice)
    return "Removed." if after < before else f"Not found: {name}"

def set_price(invoice: Dict[str, Any], name: str, amount: float) -> str:
    """
    Set the FULL price (tariff) for the named procedure; keep existing discount amount.
    """
    found = False
    for p in invoice["procedures"]:
        if p.get("name") == name:
            p["tariff"] = round(float(amount), 2)
            # keep existing discount; recompute billed
            p["discount"] = round(float(p.get("discount", 0.0) or 0.0), 2)
            p["billed"] = round(p["tariff"] - p["discount"], 2)
            found = True
            break
    if not found:
        return f"Not found: {name}"
    recompute_totals(invoice)
    return f"Set {name} to {amount}."
