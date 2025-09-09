import types, difflib
from typing import Dict, Any, Optional, List

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

def build_initial_invoice(extracted: Dict[str, Any], tariff: Dict[str, float]) -> Dict[str, Any]:
    matched = []
    choices = list(tariff.keys())
    for raw in extracted.get("procedures", []):
        match = best_tariff_match(raw, choices)
        if match is not None:
            billed = price_for(match, tariff)
            if billed is not None:
                matched.append({"name": match, "billed": billed})

    invoice = {
        "patient name": extracted.get("patient name", ""),
        "patient SSN": extracted.get("patient SSN", ""),
        "hospital name": extracted.get("hospital name", ""),
        "date of service": extracted.get("date of service", ""),
        "diagnose": extracted.get("diagnose", ""),
        "procedures": matched,
    }
    return invoice

def pretty_invoice(invoice: Dict[str, Any]) -> str:
    lines = []
    lines.append(f"Patient: {invoice.get('patient name','-')}  SSN: {invoice.get('patient SSN','-')}")
    lines.append(f"Hospital: {invoice.get('hospital name','-')}  Date: {invoice.get('date of service','-')}")
    lines.append(f"Diagnose: {invoice.get('diagnose','-')}")
    lines.append("Procedures:")
    total = 0.0
    for p in invoice.get("procedures", []):
        lines.append(f"  - {p['name']} | billed: {p['billed']}")
        total += float(p["billed"])
    lines.append(f"TOTAL: {total}")
    return "\n".join(lines)

# -------- Action helpers --------

def apply_discount(invoice: Dict[str, Any], percent: float) -> str:
    for p in invoice["procedures"]:
        p["billed"] = round(float(p["billed"]) * (1 - percent/100.0), 2)
    return f"Applied discount of {percent}% to all procedures."

def add_procedure_free_text(invoice: Dict[str, Any], tariff: Dict[str, float], free_text: str) -> str:
    match = best_tariff_match(free_text, list(tariff.keys()))
    if not match:
        return f"No close tariff match found for: {free_text}"
    billed = price_for(match, tariff)
    if billed is None:
        return f"No price found for: {match}"
    invoice["procedures"].append({"name": match, "billed": billed})
    return f"Added: {match} ({billed})"

def remove_procedure_by_index(invoice: Dict[str, Any], index: int) -> str:
    if index < 1 or index > len(invoice["procedures"]):
        return f"Index {index} out of range (1..{len(invoice['procedures'])})."
    removed = invoice["procedures"].pop(index-1)
    return f"Removed: {removed['name']}"

def remove_procedure_by_name(invoice: Dict[str, Any], name: str) -> str:
    before = len(invoice["procedures"])
    invoice["procedures"] = [p for p in invoice["procedures"] if p["name"] != name]
    after = len(invoice["procedures"])
    return "Removed." if after < before else f"Not found: {name}"

def set_price(invoice: Dict[str, Any], name: str, amount: float) -> str:
    for p in invoice["procedures"]:
        if p["name"] == name:
            p["billed"] = round(float(amount), 2)
            return f"Set {name} to {amount}."
    return f"Not found: {name}"
