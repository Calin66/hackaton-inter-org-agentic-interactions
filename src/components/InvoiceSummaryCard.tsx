import { CheckCircle, AlertTriangle, FileText } from 'lucide-react';
import { fmtUSD, safeNum, numberOr, maskSSN } from '@/lib/ui/format';
import { renderDiagnosis } from '@/lib/ui/diagnosis';

export function InvoiceSummaryCard({ data }: { data: any }) {
  const draft = data?.draft ?? data?.invoice ?? data;
  const ready = data?.ready_for_insurance ?? draft?.ready_for_insurance ?? false;

  const patient = draft?.patient ?? draft ?? {};
  const fullName = patient?.full_name ?? patient?.name ?? data?.full_name ?? data?.name ?? '—';
  const ssn = patient?.ssn ?? data?.ssn ?? '—';
  const diagnosis =
    draft?.diagnosis ?? draft?.diagnoses ?? data?.diagnosis ?? data?.diagnoses ?? [];
  const procedures: any[] = draft?.procedures ?? data?.procedures ?? draft?.items ?? [];

  const totals = draft?.totals ?? data?.totals ?? draft ?? {};
  const subtotal = safeNum(totals?.subtotal ?? totals?.sub_total ?? draft?.subtotal);
  const discount = safeNum(totals?.discount ?? totals?.discounts);
  const tax = safeNum(totals?.tax);
  const total = safeNum(totals?.total ?? draft?.total);

  const missing =
    data?.missing ?? draft?.missing ?? data?.missing_fields ?? draft?.missing_fields ?? [];

  return (
    <div className="rounded-2xl border border-neutral-800 bg-[#0f0f0f] p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium text-neutral-200">
          <FileText className="h-4 w-4 text-neutral-400" />
          Invoice summary
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

      <div className="grid gap-2 sm:grid-cols-3">
        <InfoRow label="Full name" value={fullName} />
        <InfoRow label="SSN" value={maskSSN(ssn)} />
      </div>

      <SectionTitle>Diagnosis</SectionTitle>
      <div className="rounded-xl border border-neutral-900 bg-[#0e0e0e] p-2 text-sm text-neutral-300">
        {renderDiagnosis(diagnosis)}
      </div>

      <SectionTitle>Procedures</SectionTitle>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-neutral-800 text-neutral-400">
              <th className="py-1 pr-2 text-left font-medium">Procedure</th>
              <th className="py-1 px-2 text-right font-medium">Units</th>
              <th className="py-1 px-2 text-right font-medium">Tariff</th>
              <th className="py-1 px-2 text-right font-medium">Discount</th>
              <th className="py-1 pl-2 text-right font-medium">Line total</th>
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
                  <tr key={i} className="border-b border-neutral-900">
                    <td className="py-1 pr-2">{name}</td>
                    <td className="py-1 px-2 text-right">{units}</td>
                    <td className="py-1 px-2 text-right">{fmtUSD(price)}</td>
                    <td className="py-1 px-2 text-right">{disc ? fmtUSD(disc) : '—'}</td>
                    <td className="py-1 pl-2 text-right">{fmtUSD(line!)}</td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={5} className="py-2 text-neutral-500">
                  No procedures
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <SectionTitle>Totals</SectionTitle>
      <div className="grid gap-2 sm:grid-cols-4">
        <InfoRow label="Subtotal" value={subtotal != null ? fmtUSD(subtotal) : '—'} />
        <InfoRow label="Discounts" value={discount ? fmtUSD(discount) : '—'} />
        <InfoRow label="Tax" value={tax ? fmtUSD(tax) : '—'} />
        <InfoRow
          label="Total"
          value={<span className="font-semibold">{total != null ? fmtUSD(total) : '—'}</span>}
        />
      </div>

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

function InfoRow({ label, value }: { label: string; value: any }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-neutral-900 bg-[#0e0e0e] px-2 py-1">
      <span className="text-neutral-400 text-sm">{label}</span>
      <span className="text-neutral-200 text-sm">{value ?? '—'}</span>
    </div>
  );
}
function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div className="mt-4 mb-2 text-sm font-medium text-neutral-200">{children}</div>;
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
