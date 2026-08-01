import React, { useEffect, useReducer, useRef, useState } from "react";
import { getEncounters, getHealth, startRun } from "./api.js";
import StageRail from "./components/StageRail.jsx";
import Console from "./components/Console.jsx";
import { NoteCard, CodingCard, AttemptCard, FinalBanner } from "./components/Artifacts.jsx";

const INITIAL = {
  meta: null,
  stages: { scribe: "idle", coder: "idle", claim: "idle", payer: "idle", resolver: "idle" },
  blocks: [],       // console blocks, one per agent stage_started
  note: null,
  coding: null,
  attempts: {},     // attempt number -> {claim, adjudication, resolution, appeal}
  final: null,
  usageTotals: null,
  totalSeconds: null,
  estimatedCost: null,
  error: "",
  live: false,
};

function reduce(state, ev) {
  const s = structuredClone(state);
  const touchAttempt = (n) => (s.attempts[n] = s.attempts[n] || { attempt: n });
  switch (ev.type) {
    case "reset":
      return { ...structuredClone(INITIAL), live: true };
    case "run_started":
      s.meta = ev;
      return s;
    case "stage_started":
      s.stages[ev.stage] = "active";
      if (ev.stage === "resolver") { s.stages.claim = "idle"; s.stages.payer = "idle"; }
      s.blocks.push({ stage: ev.stage, label: ev.label, model: ev.model,
                      attempt: ev.attempt, text: "", reasoning: "", tools: [], done: false });
      return s;
    case "token": {
      const b = s.blocks.findLast((x) => x.stage === ev.stage);
      if (b) b.text += ev.delta;
      return s;
    }
    case "reasoning": {
      const b = s.blocks.findLast((x) => x.stage === ev.stage);
      if (b) b.reasoning += ev.delta;
      return s;
    }
    case "tool_call": {
      const b = s.blocks.findLast((x) => x.stage === ev.stage);
      if (b) b.tools.push({ name: ev.name, args: ev.args, result: null });
      return s;
    }
    case "tool_result": {
      const b = s.blocks.findLast((x) => x.stage === ev.stage);
      const t = b && b.tools.findLast((x) => x.result === null);
      if (t) t.result = ev.output;
      return s;
    }
    case "stage_done": {
      s.stages[ev.stage] = "done";
      const b = s.blocks.findLast((x) => x.stage === ev.stage);
      if (b) b.done = true;
      if (ev.stage === "scribe") s.note = ev.artifact;
      if (ev.stage === "coder") s.coding = ev.artifact;
      return s;
    }
    case "claim_built":
      s.stages.claim = "done";
      s.stages.payer = "active";
      touchAttempt(ev.attempt).claim = ev.claim;
      return s;
    case "adjudication": {
      const a = touchAttempt(ev.attempt);
      a.adjudication = ev.result;
      s.stages.payer = ev.result.status === "accepted" ? "done" : "failed";
      return s;
    }
    case "resolution": {
      const b = s.blocks.findLast((x) => x.stage === "resolver");
      if (b) b.done = true;
      s.stages.resolver = "done";
      touchAttempt(ev.attempt).resolution = ev.decision;
      return s;
    }
    case "appeal":
      touchAttempt(ev.attempt).appeal = ev.outcome;
      return s;
    case "run_finished":
      s.final = ev.final;
      s.usageTotals = ev.usage_totals;
      s.totalSeconds = ev.total_seconds;
      s.estimatedCost = ev.final ? ev.final.estimated_cost_usd : null;
      s.live = false;
      for (const k of Object.keys(s.stages)) if (s.stages[k] === "active") s.stages[k] = "done";
      return s;
    case "error":
      s.error = ev.message;
      s.live = false;
      return s;
    default:
      return s;
  }
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [encounters, setEncounters] = useState([]);
  const [selected, setSelected] = useState("");
  const [useCustom, setUseCustom] = useState(false);
  const [customText, setCustomText] = useState("");
  const [profile, setProfile] = useState("budget");
  const [state, dispatch] = useReducer(reduce, structuredClone(INITIAL));
  const esRef = useRef(null);

  useEffect(() => {
    getHealth().then((h) => { setHealth(h); setProfile(h.default_profile); }).catch(() => {});
    getEncounters()
      .then((rows) => { setEncounters(rows); if (rows.length) setSelected(rows[0].encounter_id); })
      .catch(() => setEncounters([]));
    return () => esRef.current && esRef.current.close();
  }, []);

  const launch = async (mock = false) => {
    dispatch({ type: "reset" });
    try {
      const payload = mock
        ? { mock: true }
        : useCustom
          ? { custom_transcript: customText, profile }
          : { encounter_id: selected, profile };
      const { run_id } = await startRun(payload);
      if (esRef.current) esRef.current.close();
      const es = new EventSource(`/api/runs/${run_id}/events`);
      esRef.current = es;
      es.onmessage = (msg) => {
        const ev = JSON.parse(msg.data);
        dispatch(ev);
        if (ev.type === "run_finished" || ev.type === "error") es.close();
      };
      es.onerror = () => es.close();
    } catch (e) {
      dispatch({ type: "error", message: String(e) });
    }
  };

  const attempts = Object.values(state.attempts).sort((a, b) => a.attempt - b.attempt);
  const started = state.meta !== null || state.live;

  return (
    <div className="page">
      <header className="top">
        <div className="brand">
          <h1>Claim<span>Loop</span></h1>
          <p>watch agents take a clinic visit from transcript to paid claim, denials included</p>
        </div>
        {health && (
          <div className="chips">
            <span className={`badge ${health.api_key_present ? "b-ok" : "b-bad"}`}>
              {health.api_key_present ? "API key loaded" : "no API key"}
            </span>
            <span className={`badge ${health.data_present ? "b-ok" : "b-bad"}`}>
              {health.data_present ? "data ready" : "run fetch_data.py"}
            </span>
          </div>
        )}
      </header>

      <section className="panel controls">
        <div className="row">
          <label className="opt">
            <input type="radio" checked={!useCustom} onChange={() => setUseCustom(false)} />
            ACI-Bench encounter
          </label>
          <label className="opt">
            <input type="radio" checked={useCustom} onChange={() => setUseCustom(true)} />
            paste a transcript
          </label>
          <div className="spacer" />
          <select className="profile" value={profile} onChange={(e) => setProfile(e.target.value)}
                  title="which model runs each agent stage">
            <option value="budget">budget: Luna everywhere</option>
            <option value="balanced">balanced: Luna scribe, Terra coder + resolver</option>
            <option value="premium">premium: Terra agents, Sol resolver</option>
          </select>
        </div>

        {!useCustom ? (
          <select value={selected} onChange={(e) => setSelected(e.target.value)}>
            {encounters.map((e) => (
              <option key={e.encounter_id} value={e.encounter_id}>
                {e.encounter_id} ({e.split}) {e.patient && `- ${e.patient}`}
                {e.age && `, ${e.age} ${e.gender}`} - {e.chief_complaint}
              </option>
            ))}
          </select>
        ) : (
          <textarea rows={6} value={customText} onChange={(e) => setCustomText(e.target.value)}
                    placeholder="[doctor] hi there, what brings you in today? [patient] ..." />
        )}

        <div className="row">
          <button className="run" onClick={() => launch(false)}
                  disabled={state.live || (!useCustom && !selected)}>
            {state.live ? "agents working..." : "run the claim lifecycle"}
          </button>
          <button className="ghost" onClick={() => launch(true)} disabled={state.live}
                  title="scripted playback that exercises the real payer, no tokens spent">
            mock playback
          </button>
        </div>
        {state.error && <p className="error">{state.error}</p>}
      </section>

      {state.meta && state.meta.mock && (
        <div className="mockbar">
          Mock playback for UI preview. Agent text is a fixture, no tokens were
          spent. The claim builder and payer verdicts are the real rules engine.
        </div>
      )}

      {started && (
        <div className="grid">
          <div className="left">
            <StageRail stages={state.stages} attempts={attempts.length} models={state.meta?.models} />
            <Console blocks={state.blocks} live={state.live} />
          </div>
          <div className="right">
            {state.note && <NoteCard stage={state.note} />}
            {state.coding && <CodingCard stage={state.coding} />}
            {attempts.map((a) => <AttemptCard key={a.attempt} attempt={a} />)}
            {state.final && (
              <FinalBanner final={state.final} usage={state.usageTotals}
                           seconds={state.totalSeconds} />
            )}
          </div>
        </div>
      )}

      <footer>
        Portfolio demo by Abdullah Abdel-Khalek. Simulated payer, public simulated
        dataset, no real patient data. Not medical or billing advice.
      </footer>
    </div>
  );
}
