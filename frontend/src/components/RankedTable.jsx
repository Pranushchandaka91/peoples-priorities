function NeedCell({ row }) {
  const isRange = row.need_low !== row.need_high;
  if (!isRange) {
    return <span>{row.need_low.toFixed(2)}</span>;
  }
  return (
    <span className="whitespace-nowrap">
      {row.need_low.toFixed(2)}–{row.need_high.toFixed(2)} <span title="Uncertainty from disputed source trust">⚠</span>
    </span>
  );
}

function FlagIcon({ flags }) {
  if (!flags || flags.length === 0) return null;
  return (
    <span className="ml-1 cursor-help text-amber-600" title={flags.join("\n")}>
      ⚠
    </span>
  );
}

function PriorityBar({ value }) {
  const pct = Math.max(0, Math.min(100, value * 100));
  return (
    <div className="w-24 h-2 rounded-full bg-slate-200 overflow-hidden" title={value.toFixed(3)}>
      <div className="h-full bg-slate-700" style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function RankedTable({ rows, selectedWorkId, onSelect }) {
  return (
    <div className="overflow-x-auto rounded-md border border-slate-300 bg-white">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-slate-100 text-left text-slate-600 border-b border-slate-300">
            <th className="px-3 py-2 font-medium">#</th>
            <th className="px-3 py-2 font-medium">Work</th>
            <th className="px-3 py-2 font-medium">Ward</th>
            <th className="px-3 py-2 font-medium">Sector</th>
            <th className="px-3 py-2 font-medium text-right">Cost (₹L)</th>
            <th className="px-3 py-2 font-medium">Need</th>
            <th className="px-3 py-2 font-medium">Priority</th>
            <th className="px-3 py-2 font-medium">Funded</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.work_id}
              onClick={() => onSelect(row.work_id)}
              className={`border-b border-slate-200 cursor-pointer hover:bg-slate-50 ${
                selectedWorkId === row.work_id ? "bg-slate-100" : ""
              }`}
            >
              <td className="px-3 py-2 text-slate-500">{row.rank}</td>
              <td className="px-3 py-2 font-medium text-slate-900">
                {row.name}
                <FlagIcon flags={row.data_flags} />
              </td>
              <td className="px-3 py-2 text-slate-600">{row.ward_id}</td>
              <td className="px-3 py-2 text-slate-600">{row.sector}</td>
              <td className="px-3 py-2 text-right text-slate-700">{row.cost_lakh.toFixed(0)}</td>
              <td className="px-3 py-2 text-slate-700">
                <NeedCell row={row} />
              </td>
              <td className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <PriorityBar value={row.priority} />
                  <span className="text-slate-500 text-xs">{row.priority.toFixed(3)}</span>
                </div>
              </td>
              <td className="px-3 py-2">
                {row.funded ? (
                  <span className="inline-block rounded bg-emerald-100 text-emerald-800 text-xs px-2 py-0.5 font-medium">
                    funded
                  </span>
                ) : (
                  <span className="inline-block rounded bg-slate-100 text-slate-500 text-xs px-2 py-0.5">
                    —
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
