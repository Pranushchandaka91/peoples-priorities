import { useState } from "react";
import { api } from "../api";

function ageDays(createdAt) {
  const ms = Date.now() - new Date(createdAt).getTime();
  return Math.max(0, Math.floor(ms / (1000 * 60 * 60 * 24)));
}

function RealityPeek({ assetId, demoMode }) {
  const [reality, setReality] = useState(null);
  const [loading, setLoading] = useState(false);

  if (!demoMode) return null;

  async function peek() {
    setLoading(true);
    try {
      const r = await api.peekReality(assetId);
      setReality(r.actual_status);
    } finally {
      setLoading(false);
    }
  }

  if (reality) {
    return (
      <span className="text-xs text-slate-500 italic">
        actual: {reality}
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={peek}
      disabled={loading}
      title="Peek ground truth (operator/demo only)"
      className="text-slate-400 hover:text-slate-700"
    >
      👁
    </button>
  );
}

export default function VerificationQueue({ tasks, onClose, demoMode }) {
  const [closingId, setClosingId] = useState(null);

  async function handleClose(taskId, outcome) {
    setClosingId(taskId);
    try {
      await onClose(taskId, outcome);
    } finally {
      setClosingId(null);
    }
  }

  if (tasks.length === 0) {
    return <div className="text-sm text-slate-500">No pending verification tasks.</div>;
  }

  return (
    <ul className="space-y-2 text-sm">
      {tasks.map((t) => (
        <li key={t.task_id} className="rounded border border-slate-300 bg-white p-3 flex items-center justify-between gap-3">
          <div>
            <div className="font-medium text-slate-900 flex items-center gap-2">
              {t.descriptor}
              <RealityPeek assetId={t.asset_id} demoMode={demoMode} />
            </div>
            <div className="text-xs text-slate-500">
              {t.ward_id} · {t.sector} · {t.dispute_count} dispute{t.dispute_count === 1 ? "" : "s"} · {ageDays(t.created_at)}d old
            </div>
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              disabled={closingId === t.task_id}
              onClick={() => handleClose(t.task_id, "confirmed_broken")}
              className="rounded bg-rose-600 text-white text-xs px-2 py-1.5 font-medium hover:bg-rose-700 disabled:opacity-50"
            >
              Confirmed broken
            </button>
            <button
              disabled={closingId === t.task_id}
              onClick={() => handleClose(t.task_id, "fixed")}
              className="rounded bg-emerald-600 text-white text-xs px-2 py-1.5 font-medium hover:bg-emerald-700 disabled:opacity-50"
            >
              Actually fixed
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
