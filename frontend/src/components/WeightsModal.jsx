import { useState } from "react";

export default function WeightsModal({ weightsData, onClose, onSave }) {
  const [w, setW] = useState({ ...weightsData.current, changed_by: "mp_office" });
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const total = w.w_demand + w.w_need + w.w_equity + w.w_cost;

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onSave(w);
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-40 p-4">
      <div className="bg-white rounded-md border border-slate-300 shadow-xl w-full max-w-lg p-5 text-sm">
        <h3 className="text-base font-semibold text-slate-900 mb-3">Priority weights</h3>

        {["w_demand", "w_need", "w_equity", "w_cost"].map((k) => (
          <label key={k} className="block mb-3">
            <span className="text-xs text-slate-500">{k.replace("w_", "").replace(/^\w/, (c) => c.toUpperCase())}</span>
            <input
              type="number" step="0.01" min="0" max="1"
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
              value={w[k]}
              onChange={(e) => setW((s) => ({ ...s, [k]: parseFloat(e.target.value) || 0 }))}
            />
          </label>
        ))}

        <div className={`text-xs mb-3 ${total < 0.9 || total > 1.1 ? "text-rose-600" : "text-slate-500"}`}>
          Sum: {total.toFixed(2)} (must be 0.90–1.10)
        </div>

        {error && <div className="text-xs text-rose-600 mb-3">{error}</div>}

        <div className="border-t border-slate-200 pt-3 mb-3">
          <div className="text-xs uppercase tracking-wide text-slate-400 mb-2">Audit log</div>
          <ul className="max-h-32 overflow-y-auto space-y-1 text-xs text-slate-600">
            {[...weightsData.audit_log].reverse().map((r) => (
              <li key={r.id}>
                {new Date(r.changed_at).toLocaleString()} — {r.changed_by}: d={r.w_demand} n={r.w_need} e={r.w_equity} c={r.w_cost}
              </li>
            ))}
          </ul>
        </div>

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded px-3 py-1.5 text-slate-600 hover:bg-slate-100">Cancel</button>
          <button
            onClick={save}
            disabled={saving || total < 0.9 || total > 1.1}
            className="rounded bg-slate-800 text-white px-3 py-1.5 font-medium hover:bg-slate-700 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
