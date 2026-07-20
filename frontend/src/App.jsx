import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import RankedTable from "./components/RankedTable";
import RationaleCard from "./components/RationaleCard";
import FieldSignals from "./components/FieldSignals";
import WeightsModal from "./components/WeightsModal";
import { ToastStack } from "./components/Toast";

let toastId = 0;

export default function App() {
  const [budget, setBudget] = useState(200);
  const [rows, setRows] = useState([]);
  const [selectedWorkId, setSelectedWorkId] = useState(null);
  const [rationale, setRationale] = useState(null);
  const [rationaleLoading, setRationaleLoading] = useState(false);
  const [tasks, setTasks] = useState([]);
  const [toasts, setToasts] = useState([]);
  const [weightsOpen, setWeightsOpen] = useState(false);
  const [weightsData, setWeightsData] = useState(null);
  const [demoMode, setDemoMode] = useState(false);
  const [resetting, setResetting] = useState(false);

  const pushToast = useCallback((message) => {
    const id = ++toastId;
    setToasts((t) => [...t, { id, message }]);
  }, []);
  const dismissToast = useCallback((id) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const refreshRanking = useCallback(() => {
    api.getRanking(budget).then(setRows).catch((e) => pushToast(`ranking error: ${e.message}`));
  }, [budget, pushToast]);

  const refreshTasks = useCallback(() => {
    api.getVerificationTasks("pending").then(setTasks).catch(() => {});
  }, []);

  useEffect(() => { refreshRanking(); }, [refreshRanking]);
  useEffect(() => { refreshTasks(); }, [refreshTasks]);
  useEffect(() => { api.getConfig().then((c) => setDemoMode(c.demo_mode)).catch(() => {}); }, []);

  useEffect(() => {
    if (!selectedWorkId) { setRationale(null); return; }
    setRationaleLoading(true);
    api.getRationale(selectedWorkId)
      .then(setRationale)
      .catch((e) => pushToast(`rationale error: ${e.message}`))
      .finally(() => setRationaleLoading(false));
  }, [selectedWorkId, pushToast]);

  function handleComplaintSubmitted(result) {
    if (result.dispute_created) {
      pushToast(`⚡ This report disputes the official record for ${result.asset_id}`);
    }
    refreshTasks();
  }

  async function handleTaskClose(taskId, outcome) {
    await api.closeVerificationTask(taskId, { outcome, note: null });
    refreshTasks();
    refreshRanking();
    if (selectedWorkId) {
      api.getRationale(selectedWorkId).then(setRationale).catch(() => {});
    }
  }

  function openWeights() {
    api.getWeights().then((d) => { setWeightsData(d); setWeightsOpen(true); });
  }

  async function saveWeights(w) {
    await api.postWeights(w);
    refreshRanking();
  }

  async function handleReset() {
    if (!window.confirm("Reset the demo? This clears all complaints, disputes, and verification tasks, and restores trust/asset records.")) {
      return;
    }
    setResetting(true);
    try {
      await api.resetDemo();
      setSelectedWorkId(null);
      refreshRanking();
      refreshTasks();
      pushToast("Demo reset — world restored to pristine.");
    } finally {
      setResetting(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="bg-white border-b border-slate-300 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">People's Priorities</h1>
          <p className="text-xs text-slate-500">Constituency development prioritization — single constituency, 6 wards</p>
        </div>
        <div className="flex items-center gap-6">
          <label className="flex items-center gap-2 text-sm">
            <span className="text-slate-500">Budget</span>
            <input
              type="range" min="20" max="500" step="10"
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value))}
              className="w-40"
            />
            <span className="font-medium w-20 text-right">₹{budget}L</span>
          </label>
          <button
            onClick={openWeights}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50"
          >
            Weights
          </button>
          {demoMode && (
            <button
              onClick={handleReset}
              disabled={resetting}
              className="rounded border border-rose-300 text-rose-700 px-3 py-1.5 text-sm font-medium hover:bg-rose-50 disabled:opacity-50"
            >
              {resetting ? "Resetting…" : "Reset demo"}
            </button>
          )}
        </div>
      </header>

      <main className="max-w-7xl mx-auto p-6 grid grid-cols-3 gap-6">
        <div className="col-span-2 space-y-6">
          <section>
            <h2 className="text-sm font-semibold text-slate-600 mb-2 uppercase tracking-wide">Ranked works</h2>
            <RankedTable rows={rows} selectedWorkId={selectedWorkId} onSelect={setSelectedWorkId} />
          </section>
          <section>
            <h2 className="text-sm font-semibold text-slate-600 mb-2 uppercase tracking-wide">Field signals</h2>
            <FieldSignals
              tasks={tasks}
              onComplaintSubmitted={handleComplaintSubmitted}
              onTaskClose={handleTaskClose}
              demoMode={demoMode}
            />
          </section>
        </div>
        <div className="col-span-1">
          <h2 className="text-sm font-semibold text-slate-600 mb-2 uppercase tracking-wide">Rationale</h2>
          <div className="sticky top-6">
            <RationaleCard rationale={rationale} loading={rationaleLoading} />
          </div>
        </div>
      </main>

      {weightsOpen && weightsData && (
        <WeightsModal
          weightsData={weightsData}
          onClose={() => setWeightsOpen(false)}
          onSave={saveWeights}
        />
      )}

      <ToastStack toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
