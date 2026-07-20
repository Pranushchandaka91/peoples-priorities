import { useEffect, useState } from "react";
import { api } from "../api";
import { SECTORS, WARDS, REPORTED_STATUSES } from "../constants";

const initial = {
  ward_id: WARDS[0],
  sector: SECTORS[0],
  raw_text: "",
  asset_id: "",
  reported_status: "",
  duration_weeks: "",
};

export default function ComplaintForm({ onSubmitted }) {
  const [form, setForm] = useState(initial);
  const [assets, setAssets] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [quickText, setQuickText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [parseNote, setParseNote] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api.getAssets(form.ward_id, form.sector)
      .then((rows) => { if (!cancelled) setAssets(rows); })
      .catch(() => { if (!cancelled) setAssets([]); });
    return () => { cancelled = true; };
  }, [form.ward_id, form.sector]);

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  // §9a — pre-fills the structured form from free text; never auto-submits.
  // Degrades to "fill manually" on any parse failure or low-confidence miss.
  async function handleParse() {
    if (!quickText.trim()) return;
    setParsing(true);
    setParseNote(null);
    try {
      const result = await api.parseComplaint(quickText);
      const top = result.asset_candidates?.[0];
      setForm((f) => ({
        ...f,
        raw_text: quickText,
        ward_id: result.ward_id || f.ward_id,
        sector: result.sector || f.sector,
        asset_id: top ? top.asset_id : f.asset_id,
        reported_status: result.reported_status || f.reported_status,
        duration_weeks: result.duration_weeks != null ? String(result.duration_weeks) : f.duration_weeks,
      }));
      if (result.confidence === "low" && !result.ward_id && !result.sector) {
        setParseNote("Couldn't confidently extract fields — please fill in the form below manually.");
      } else {
        setParseNote(`Pre-filled (confidence: ${result.confidence}). Review before submitting.`);
      }
    } catch {
      setParseNote("Parsing unavailable — please fill in the form below manually.");
    } finally {
      setParsing(false);
    }
  }

  async function submit(e) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const body = {
        ward_id: form.ward_id,
        sector: form.sector,
        raw_text: form.raw_text,
        asset_id: form.asset_id || null,
        reported_status: form.reported_status || null,
        duration_weeks: form.duration_weeks ? parseInt(form.duration_weeks, 10) : null,
      };
      const result = await api.postComplaint(body);
      onSubmitted(result);
      setForm((f) => ({ ...initial, ward_id: f.ward_id, sector: f.sector }));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 text-sm">
      <div className="rounded border border-slate-200 bg-slate-50 p-3">
        <span className="text-xs text-slate-500">
          Quick parse — paste any complaint, we'll pre-fill the fields below (never auto-submitted)
        </span>
        <div className="mt-1 flex gap-2">
          <input
            id="quick-parse-text"
            className="flex-1 rounded border border-slate-300 px-2 py-1.5"
            placeholder="e.g. the handpump near the school in W14 has been dry for a month"
            value={quickText}
            onChange={(e) => setQuickText(e.target.value)}
          />
          <button
            id="quick-parse-btn"
            type="button"
            disabled={parsing || !quickText.trim()}
            onClick={handleParse}
            className="rounded bg-slate-700 text-white px-3 py-1.5 text-xs font-medium hover:bg-slate-600 disabled:opacity-50"
          >
            {parsing ? "Parsing…" : "Parse"}
          </button>
        </div>
        {parseNote && <div className="mt-1 text-xs text-slate-500">{parseNote}</div>}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className="text-xs text-slate-500">Ward</span>
          <select
            id="complaint-ward"
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
            value={form.ward_id}
            onChange={(e) => set("ward_id", e.target.value)}
          >
            {WARDS.map((w) => <option key={w} value={w}>{w}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="text-xs text-slate-500">Sector</span>
          <select
            id="complaint-sector"
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
            value={form.sector}
            onChange={(e) => set("sector", e.target.value)}
          >
            {SECTORS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      </div>

      <label className="block">
        <span className="text-xs text-slate-500">Complaint text</span>
        <textarea
          id="complaint-text"
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
          rows={3}
          required
          value={form.raw_text}
          onChange={(e) => set("raw_text", e.target.value)}
        />
      </label>

      <label className="block">
        <span className="text-xs text-slate-500">Asset (optional, filtered by ward + sector)</span>
        <select
          id="complaint-asset"
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
          value={form.asset_id}
          onChange={(e) => set("asset_id", e.target.value)}
        >
          <option value="">— none / legacy free-text —</option>
          {assets.map((a) => (
            <option key={a.asset_id} value={a.asset_id}>{a.asset_id} — {a.descriptor}</option>
          ))}
        </select>
      </label>

      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className="text-xs text-slate-500">Status</span>
          <select
            id="complaint-status"
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
            value={form.reported_status}
            onChange={(e) => set("reported_status", e.target.value)}
          >
            {REPORTED_STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="text-xs text-slate-500">Duration (weeks)</span>
          <input
            id="complaint-duration"
            type="number"
            min="0"
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
            value={form.duration_weeks}
            onChange={(e) => set("duration_weeks", e.target.value)}
          />
        </label>
      </div>

      <button
        id="complaint-submit"
        type="submit"
        disabled={submitting}
        className="rounded bg-slate-800 text-white px-4 py-2 font-medium hover:bg-slate-700 disabled:opacity-50"
      >
        {submitting ? "Submitting…" : "Submit complaint"}
      </button>
    </form>
  );
}
