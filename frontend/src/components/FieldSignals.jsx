import { useState } from "react";
import ComplaintForm from "./ComplaintForm";
import VerificationQueue from "./VerificationQueue";

export default function FieldSignals({ tasks, onComplaintSubmitted, onTaskClose, demoMode }) {
  const [tab, setTab] = useState("intake");

  return (
    <div className="rounded-md border border-slate-300 bg-white p-4">
      <div className="flex gap-4 border-b border-slate-200 mb-4">
        <button
          className={`pb-2 text-sm font-medium border-b-2 -mb-px ${
            tab === "intake" ? "border-slate-800 text-slate-900" : "border-transparent text-slate-500"
          }`}
          onClick={() => setTab("intake")}
        >
          Complaint intake
        </button>
        <button
          className={`pb-2 text-sm font-medium border-b-2 -mb-px ${
            tab === "queue" ? "border-slate-800 text-slate-900" : "border-transparent text-slate-500"
          }`}
          onClick={() => setTab("queue")}
        >
          Verification queue {tasks.length > 0 && <span className="ml-1 text-amber-600">({tasks.length})</span>}
        </button>
      </div>

      {tab === "intake" ? (
        <ComplaintForm onSubmitted={onComplaintSubmitted} />
      ) : (
        <VerificationQueue tasks={tasks} onClose={onTaskClose} demoMode={demoMode} />
      )}
    </div>
  );
}
