import { CheckCircle, AlertTriangle, FileText, Building2, CalendarDays, User2 } from 'lucide-react';
import { fmtUSD, safeNum, numberOr, maskSSN } from '@/lib/ui/format';
import { renderDiagnosis } from '@/lib/ui/diagnosis';

/* ----------------------- existing normalizer (unchanged) ----------------------- */
function isNewBackendInvoice(obj: any) {
  return (
    obj &&
    typeof obj === 'object' &&
    ('patient name' in obj || 'patient SSN' in obj || 'diagnose' in obj) &&
    Array.isArray(obj?.procedures)
  );
}

function normalizeNewInvoice(inv: any) {
  const full_name = (inv?.['patient name'] ?? '').trim() || undefined;
  const ssn = (inv?.['patient SSN'] ?? '').trim() || undefined;
  const hospital = (inv?.['hospital name'] ?? '').trim() || undefined;
  const date_of_service = (inv?.['date of service'] ?? '').trim() || undefined;

  const diagnosis = inv?.diagnose ? [String(inv.diagnose).trim()].filter(Boolean) : [];

  const procedures = (inv?.procedures ?? []).map((p: any) => {
    const billed = Number(p?.billed ?? 0) || 0;
    return {
      name: p?.name ?? p?.procedure ?? '—',
      units: 1,
      price: billed,
      discount: 0,
      total: billed,
    };
  });

  const subtotal = procedures.reduce((s: number, p: any) => s + (Number(p.total) || 0), 0);
  const totals = { subtotal, discount: 0, tax: 0, total: subtotal };

  const missing: string[] = [];
  if (!full_name) missing.push('patient.full_name');
  if (!ssn) missing.push('patient.ssn');
  if (!hospital) missing.push('hospital');
  if (!date_of_service) missing.push('date_of_service');
  if (!diagnosis.length) missing.push('diagnosis');
  if (!procedures.length) missing.push('procedures');

  return {
    draft: {
      patient: { full_name, ssn },
      hospital,
      date_of_service,
      diagnosis,
      procedures,
      totals,
      ready_for_insurance: missing.length === 0,
    },
    missing,
  };
}

/* -------------------------------- component -------------------------------- */

export function InvoiceSummaryCard({ data }: { data: any }) {
  // Determine source and normalize if it’s the new backend shape
  const src = data?.draft ?? data?.invoice ?? data;
  const normalized = isNewBackendInvoice(src) ? normalizeNewInvoice(src) : data;

  const draft = normalized?.draft ?? normalized ?? {};
  const ready = normalized?.ready_for_insurance ?? draft?.ready_for_insurance ?? false;

  const patient = draft?.patient ?? {};
  const fullName = patient?.full_name ?? '—';
  const ssn = patient?.ssn ?? '—';
  const hospital = draft?.hospital ?? '—';
  const date = draft?.date_of_service ?? '—';

  const diagnosis = draft?.diagnosis ?? [];
  const procedures: any[] = draft?.procedures ?? [];

  const totals = draft?.totals ?? {};
  const subtotal = safeNum(totals?.subtotal ?? totals?.sub_total) ?? 0;
  const discount = safeNum(totals?.discount ?? totals?.discounts) ?? 0;
  const tax = safeNum(totals?.tax) ?? 0;
  const total = safeNum(totals?.total) ?? subtotal - discount + tax;

  const missing = normalized?.missing ?? [];

  return (
    <div className="rounded-2xl border border-neutral-800 bg-[#0f0f0f] p-4 shadow-[0_0_0_1px_rgba(255,255,255,0.03)_inset,0_12px_24px_-12px_rgba(0,0,0,0.6)]">
      {/* Header */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium text-neutral-200">
          <FileText className="h-4 w-4 text-neutral-400" />
          <span>Invoice summary</span>
        </div>
        <div className="flex items-center gap-2">
          {ready ? (
            <Badge tone="success" icon={<CheckCircle className="h-3.5 w-3.5" />}>
              Ready for insurance
            </Badge>
          ) : (
            <Badge tone="warn" icon={<AlertTriangle className="h-3.5 w-3.5" />}>
              Draft
            </Badge>
          )}
        </div>
      </div>

      {/* Patient + context strip */}
      <div className="mb-4 grid gap-2 sm:grid-cols-3">
        <ContextRow
          icon={<User2 className="h-3.5 w-3.5 text-neutral-400" />}
          label="Patient"
          value={
            <span className="truncate">
              {fullName} <span className="text-neutral-500">&middot; SSN {maskSSN(ssn)}</span>
            </span>
          }
        />
        <ContextRow
          icon={<Building2 className="h-3.5 w-3.5 text-neutral-400" />}
          label="Hospital"
          value={hospital || '—'}
        />
        <ContextRow
          icon={<CalendarDays className="h-3.5 w-3.5 text-neutral-400" />}
          label="Date of service"
          value={date || '—'}
        />
      </div>

      {/* Diagnosis */}
      <SectionTitle>Diagnosis</SectionTitle>
      <div className="rounded-xl border border-neutral-900 bg-[#0e0e0e] p-2">
        {diagnosis?.length ? (
          <div className="flex flex-wrap gap-1.5">
            {diagnosis.map((d: any, i: number) => (
              <Pill key={i}>{renderDiagnosis([d])}</Pill>
            ))}
          </div>
        ) : (
          <div className="text-sm text-neutral-500">No diagnosis provided</div>
        )}
      </div>

      {/* Procedures */}
      <SectionTitle>Procedures</SectionTitle>
      <div className="overflow-hidden rounded-xl border border-neutral-900 bg-[#0e0e0e]">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm [font-variant-numeric:tabular-nums]">
            <thead className="sticky top-0 z-10 bg-[#0e0e0e]">
              <tr className="border-b border-neutral-800 text-neutral-400">
                <Th left>Procedure</Th>
                <Th>Units</Th>
                <Th>Tariff</Th>
                <Th>Discount</Th>
                <Th right>Line total</Th>
              </tr>
            </thead>
            <tbody>
              {Array.isArray(procedures) && procedures.length ? (
                procedures.map((p, i) => {
                  const name = p?.name ?? p?.procedure ?? '—';
                  const units = numberOr(p?.units, 1);
                  const price = numberOr(p?.price ?? p?.tariff, 0);
                  const disc = numberOr(p?.discount, 0);
                  const line = safeNum(p?.total) ?? safeNum(units * price - disc) ?? 0;
                  return (
                    <tr
                      key={i}
                      className="border-b border-neutral-900 even:bg-[#0d0d0d] hover:bg-[#131313]/70"
                    >
                      <Td left className="max-w-[420px] truncate">
                        {name}
                      </Td>
                      <Td className="text-right">{units}</Td>
                      <Td className="text-right">
                        <Money value={price} />
                      </Td>
                      <Td className="text-right">
                        {disc ? (
                          <span className="text-red-300">
                            -<Money value={disc} />
                          </span>
                        ) : (
                          '—'
                        )}
                      </Td>
                      <Td right className="text-right font-medium">
                        <Money value={line!} />
                      </Td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={5} className="py-3 text-center text-neutral-500">
                    No procedures
                  </td>
                </tr>
              )}
            </tbody>

            {/* Table footer totals */}
            <tfoot>
              <tr className="border-t border-neutral-800">
                <Td left colSpan={3} className="text-neutral-400">
                  Subtotal
                </Td>
                <Td className="text-right text-neutral-300">
                  <Money value={subtotal} />
                </Td>
                <Td right className="text-right text-neutral-300">
                  <Money value={subtotal} />
                </Td>
              </tr>
              <tr>
                <Td left colSpan={3} className="text-neutral-400">
                  Discounts
                </Td>
                <Td className="text-right text-red-300">
                  {discount ? (
                    <>
                      -<Money value={discount} />
                    </>
                  ) : (
                    '—'
                  )}
                </Td>
                <Td right className="text-right text-red-300">
                  {discount ? (
                    <>
                      -<Money value={discount} />
                    </>
                  ) : (
                    '—'
                  )}
                </Td>
              </tr>
              <tr>
                <Td left colSpan={3} className="text-neutral-400">
                  Tax
                </Td>
                <Td className="text-right text-neutral-300">{tax ? <Money value={tax} /> : '—'}</Td>
                <Td right className="text-right text-neutral-300">
                  {tax ? <Money value={tax} /> : '—'}
                </Td>
              </tr>
              <tr>
                <Td left colSpan={3} className="text-neutral-200">
                  Total
                </Td>
                <Td className="text-right text-neutral-200 font-semibold">
                  <Money value={total} />
                </Td>
                <Td right className="text-right text-neutral-200 font-semibold">
                  <Money value={total} />
                </Td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      {/* Missing */}
      {Array.isArray(missing) && missing.length ? (
        <>
          <SectionTitle>Missing</SectionTitle>
          <ul className="ml-5 list-disc text-sm text-neutral-300">
            {missing.map((m: any, i: number) => (
              <li key={i}>{String(m)}</li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

/* --------------------------------- UI bits --------------------------------- */

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-5 mb-2 text-xs font-medium uppercase tracking-wide text-neutral-400">
      {children}
    </div>
  );
}

function Badge({
  tone,
  icon,
  children,
}: {
  tone: 'success' | 'warn' | 'info';
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  const ring =
    tone === 'success'
      ? 'border-emerald-700/60 bg-emerald-900/30 text-emerald-300'
      : tone === 'warn'
      ? 'border-yellow-700/60 bg-yellow-900/20 text-yellow-300'
      : 'border-sky-700/60 bg-sky-900/20 text-sky-300';
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs ${ring}`}
    >
      {icon}
      {children}
    </span>
  );
}

function ContextRow({
  icon,
  label,
  value,
}: {
  icon?: React.ReactNode;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-neutral-900 bg-[#0e0e0e] px-2 py-2">
      {icon}
      <div className="min-w-0">
        <div className="text-[11px] uppercase tracking-wide text-neutral-500">{label}</div>
        <div className="truncate text-sm text-neutral-200">{value}</div>
      </div>
    </div>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-neutral-800 bg-[#111] px-2 py-0.5 text-xs text-neutral-200">
      {children}
    </span>
  );
}

function Th({
  children,
  left,
  right,
}: {
  children: React.ReactNode;
  left?: boolean;
  right?: boolean;
}) {
  return (
    <th
      className={[
        'py-2 px-2 font-medium text-neutral-400',
        left ? 'text-left' : right ? 'text-right' : 'text-right',
      ].join(' ')}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  left,
  right,
  colSpan,
  className = '',
}: {
  children: React.ReactNode;
  left?: boolean;
  right?: boolean;
  colSpan?: number;
  className?: string;
}) {
  return (
    <td
      colSpan={colSpan}
      className={[
        'py-2 px-2 align-middle text-neutral-200',
        left ? 'text-left' : right ? 'text-right' : 'text-right',
        className,
      ].join(' ')}
    >
      {children}
    </td>
  );
}

function Money({ value }: { value: number }) {
  return <span className="tabular-nums">{fmtUSD(value ?? 0)}</span>;
}
