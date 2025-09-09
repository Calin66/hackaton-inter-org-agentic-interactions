export function renderDiagnosis(d: any) {
if (!d) return "—";
if (Array.isArray(d)) return d.length ? d.join(", ") : "—";
if (typeof d === "string") return d;
const codes = d?.codes ?? d?.code ?? d?.icd ?? null;
if (Array.isArray(codes) && codes.length) return codes.join(", ");
if (typeof codes === "string") return codes;
return "—";
}