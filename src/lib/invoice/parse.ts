import type { ParsedInvoice, ParsedProcedure } from "@/types";

export function parseInvoiceFromText(message: string): ParsedInvoice {
  const text = message ?? "";
  const mPatient = /Patient:\s*([^(]+?)\s*\(SSN:\s*([\d\- ]+)\)/i.exec(text);
  const full_name = mPatient?.[1]?.trim();
  const ssnRaw = mPatient?.[2]?.replace(/[^\d]/g, "");
  const ssn = ssnRaw && ssnRaw.length >= 4 ? ssnRaw : undefined;

  const hospital = /Hospital:\s*([^\n\r]+)/i.exec(text)?.[1]?.trim();
  const date_of_service = /Date of service:\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|\d{1,2}[\/.\-]\d{1,2}[\/.\-]\d{2,4})/i.exec(text)?.[1]?.trim() ?? null;

  const diagnosisRaw = /Diagnosis:\s*([^\n\r]+)/i.exec(text)?.[1]?.trim();
  const diagnosis = diagnosisRaw ? diagnosisRaw.split(/[\,\s]+/).map((s) => s.trim()).filter(Boolean) : undefined;

  const proceduresBlock = /Procedures:\s*([\s\S]*?)(?:\n\s*Total\b|\n\s*Would you|\n*$)/i.exec(text)?.[1] ?? "";
  const procLineRegex = /^[\s*\-\u2022•]+?\s*(.+?)\s*[:\-–]\s*\$?\s*([0-9][\d,]*(?:\.\d{1,2})?)\s*$/im;
  const procedures: ParsedProcedure[] = [];
  proceduresBlock.split(/\r?\n/).map((l) => l.trim()).filter(Boolean).forEach((line) => {
    const m = procLineRegex.exec(line);
    if (m) {
      const name = m[1].trim();
      const price = parseMoney(m[2]);
      if (name && Number.isFinite(price)) procedures.push({ name, price, total: price, units: 1 });
    }
  });

  const totalMatch = /Total\s+billed:\s*\$?\s*([0-9][\d,]*(?:\.\d{1,2})?)/i.exec(text);
  const total = totalMatch ? parseMoney(totalMatch[1]) : null;

  const missing: string[] = [];
  if (!full_name) missing.push("patient.full_name");
  if (!ssn) missing.push("patient.ssn");
  if (!hospital) missing.push("hospital");
  if (!date_of_service) missing.push("date_of_service");
  if (!diagnosis?.length) missing.push("diagnosis");
  if (!procedures.length) missing.push("procedures");
  if (total == null) missing.push("totals.total");

  return {
    draft: {
      patient: { full_name, ssn, dob: null },
      hospital,
      date_of_service,
      diagnosis,
      procedures,
      totals: { total },
      ready_for_insurance: missing.length === 0,
    },
    missing,
  };
}

export function mergeToolResults(serverTool: any, parsed: ParsedInvoice) {
  const s = serverTool ?? {};
  const d = s.draft ?? s.invoice ?? {};
  const p = parsed.draft;
  return {
    ...s,
    draft: {
      ...d,
      patient: { ...(d.patient ?? {}), ...(p.patient ?? {}) },
      hospital: d.hospital ?? p.hospital,
      date_of_service: d.date_of_service ?? p.date_of_service,
      diagnosis: Array.isArray(d.diagnosis) && d.diagnosis.length ? d.diagnosis : p.diagnosis,
      procedures: Array.isArray(d.procedures) && d.procedures.length ? d.procedures : p.procedures,
      totals: { ...(d.totals ?? {}), ...(p.totals ?? {}) },
      ready_for_insurance: typeof d.ready_for_insurance === "boolean" ? d.ready_for_insurance : p.ready_for_insurance,
    },
    missing: Array.from(new Set([...(s.missing ?? []), ...(parsed.missing ?? [])])),
  };
}

function parseMoney(s: string): number {
  return Number(String(s).replace(/[\,\s]/g, ""));
}