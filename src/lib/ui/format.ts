export function fmtUSD(n: number) {
try { return n.toLocaleString(undefined, { style: "currency", currency: "USD" }); }
catch { return `$${Number(n || 0).toFixed(2)}`; }
}
export function safeNum(v: any): number | null {
const n = Number(v); return Number.isFinite(n) ? n : null;
}
export function numberOr(v: any, fallback: number) {
const n = Number(v); return Number.isFinite(n) ? n : fallback;
}
export function maskSSN(v: string) {
const s = String(v ?? ""); if (!s) return "—"; const digits = s.replace(/\D/g, "");
if (digits.length < 4) return "—"; return `***-**-${digits.slice(-4)}`;
}