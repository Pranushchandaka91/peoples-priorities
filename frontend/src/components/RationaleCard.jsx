function WeightBar({ label, contribution, weight, negative }) {
  const pct = Math.max(0, Math.min(100, Math.abs(contribution) * 100));
  return (
    <div className="mb-2">
      <div className="flex justify-between text-xs text-slate-500 mb-0.5">
        <span>{label} (w={weight})</span>
        <span>{negative ? "−" : ""}{Math.abs(contribution).toFixed(3)}</span>
      </div>
      <div className="w-full h-2 rounded-full bg-slate-200 overflow-hidden">
        <div
          className={`h-full ${negative ? "bg-rose-400" : "bg-slate-700"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export default function RationaleCard({ rationale, loading }) {
  if (loading) {
    return <div className="rounded-md border border-slate-300 bg-white p-4 text-sm text-slate-500">Loading…</div>;
  }
  if (!rationale) {
    return (
      <div className="rounded-md border border-slate-300 bg-white p-4 text-sm text-slate-500">
        Select a work from the ranked table to see its rationale.
      </div>
    );
  }

  const { rank, name, cost_lakh, submissions, correction_factor, sector_evidence,
          beneficiaries, cost_per_beneficiary, priority_breakdown, disputes } = rationale;
  const b = priority_breakdown;

  return (
    <div className="rounded-md border border-slate-300 bg-white p-4 text-sm">
      <div className="text-xs text-slate-500 mb-1">#{rank}</div>
      <h3 className="text-base font-semibold text-slate-900 mb-2">{name}</h3>
      <div className="text-slate-700 mb-3">
        ₹{cost_lakh.toFixed(0)}L · {beneficiaries.toLocaleString()} beneficiaries ·
        {" "}₹{cost_per_beneficiary.toLocaleString()} per beneficiary
      </div>

      <div className="mb-3 text-slate-600">
        {submissions} citizen submission{submissions === 1 ? "" : "s"}, bias-corrected ×{correction_factor.toFixed(2)}
        {" "}({correction_factor > 1 ? "ward under-reports" : "ward over-reports"})
      </div>

      {Object.keys(sector_evidence).length > 0 && (
        <div className="mb-3 border-t border-slate-200 pt-2">
          <div className="text-xs uppercase tracking-wide text-slate-400 mb-1">Sector evidence</div>
          {Object.entries(sector_evidence).map(([k, v]) => (
            <div key={k} className="text-slate-600">
              {k.replace(/_/g, " ")}: {typeof v === "number" ? v.toFixed(1) : v}
            </div>
          ))}
        </div>
      )}

      <div className="mb-3 border-t border-slate-200 pt-2">
        <div className="text-xs uppercase tracking-wide text-slate-400 mb-2">Priority breakdown</div>
        <WeightBar label="Demand" contribution={b.weights.w_demand * b.demand} weight={b.weights.w_demand} />
        <WeightBar label="Need" contribution={b.weights.w_need * b.need} weight={b.weights.w_need} />
        <WeightBar label="Equity" contribution={b.weights.w_equity * b.equity} weight={b.weights.w_equity} />
        <WeightBar label="Cost penalty" contribution={b.weights.w_cost * b.cost_pen} weight={b.weights.w_cost} negative />
      </div>

      {disputes.length > 0 && (
        <div className="border-t border-slate-200 pt-2">
          <div className="text-xs uppercase tracking-wide text-amber-600 mb-1">Disputes</div>
          <ul className="space-y-1">
            {disputes.map((d, i) => (
              <li key={i} className="text-slate-600">
                <span className="font-medium text-slate-800">{d.descriptor}</span>
                {" — "}{d.reported_status || "unspecified"}
                {d.weeks ? `, ${d.weeks} wk` : ""} · since {d.date}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
