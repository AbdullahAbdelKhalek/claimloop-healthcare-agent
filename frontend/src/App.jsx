import React, { useEffect, useRef, useState } from "react";
import { getEncounters, getHealth, getRun, startRun } from "./api.js";

const money = (cents) => `$${(cents / 100).toFixed(2)}`;

function Badge({ kind, children }) {
  return <span className={`badge badge-${kind}`}>{children}</span>;
}

function CarcChip({ denial }) {
  return (
    <span className="carc" title={denial.description}>
      CO-{denial.carc}
      {denial.rarc ? ` / ${denial.rarc}` : ""}
    </span>
  );
}

function Confidence({ value }) {
  return (
    <span className="conf">
      <span className="conf-bar" style={{ width: `${Math.round(value * 100)}%` }} />
      <span className="conf-num">{value.toFixed(2)}</span>
    </span>
  );
}

function NoteCard({ stage }) {
  const n = stage.note;
  const rows = [
    ["Chief complaint", n.chief_complaint],
    ["HPI", n.history_of_present_illness],
    ["Past medical history", n.past_medical_history],
    ["Medications", n.medications],
    ["Allergies", n.allergies],
    ["Physical exam", n.physical_exam],
    ["Results", n.results_review],
    ["Follow up", n.follow_up],
  ];
  return (
    <section className="card">
      <header>
        <h3>1. Scribe: visit note</h3>
        <Meta stage={stage} />
      </header>
      <dl>
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
        <div>
          <dt>Assessment and plan</dt>
          <dd>
            <ol>
              {n.assessment_and_plan.map((ap, i) => (
                <li key={i}>
                  <strong>{ap.problem}.</strong> {ap.assessment} <em>{ap.plan}</em>
                </li>
              ))}
            </ol>
          </dd>
        </div>
      </dl>
    </section>
  );
}

function CodingCard({ stage }) {
  const c = stage.coding;
  return (
    <section className="card">
      <header>
        <h3>2. Coder: ICD-10-CM and CPT</h3>
        <Meta stage={stage} />
      </header>
      <table>
        <thead>
          <tr><th>#</th><th>ICD-10-CM</th><th>description</th><th>confidence</th></tr>
        </thead>
        <tbody>
          {c.diagnoses.map((d, i) => (
            <tr key={d.icd10_code + i}>
              <td>{i + 1}</td>
              <td><code>{d.icd10_code}</code></td>
              <td>{d.description}<div className="rationale">{d.rationale}</div></td>
              <td><Confidence value={d.confidence} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <table>
        <thead>
          <tr><th>CPT</th><th>description</th><th>dx links</th><th>confidence</th></tr>
        </thead>
        <tbody>
          {c.procedures.map((p, i) => (
            <tr key={p.cpt_code + i}>
              <td><code>{p.cpt_code}</code></td>
              <td>{p.description}<div className="rationale">{p.rationale}</div></td>
              <td>{p.dx_pointers.join(", ")}</td>
              <td><Confidence value={p.confidence} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {c.coding_notes && <p className="notes">{c.coding_notes}</p>}
    </section>
  );
}

function AttemptCard({ attempt }) {
  const adj = attempt.adjudication;
  const res = attempt.resolution;
  const accepted = adj.status === "accepted";
  return (
    <section className={`card attempt ${accepted ? "ok" : "bad"}`}>
      <header>
        <h3>
          Attempt {attempt.attempt}: claim <code>{attempt.claim.claim_id}</code>
        </h3>
        <Badge kind={accepted ? "ok" : "bad"}>{adj.status}</Badge>
      </header>

      <div className="claim-line">
        {attempt.claim.diagnoses.length} dx, {attempt.claim.service_lines.length} lines,
        billed {money(attempt.claim.total_charge_cents)}
        {accepted && <> , paid <strong>{money(adj.paid_total_cents)}</strong></>}
        {attempt.claim.resubmission_of && <> , resubmission of <code>{attempt.claim.resubmission_of}</code></>}
      </div>

      <div className="chips">
        {attempt.claim.service_lines.map((l) => (
          <span key={l.sequence} className="line-chip">
            {l.cpt_code}
            {l.prior_auth_number && <em> {l.prior_auth_number}</em>}
          </span>
        ))}
      </div>

      {!accepted && (
        <ul className="remittance">
          {adj.remittance_notes.map((r, i) => <li key={i}>{r}</li>)}
        </ul>
      )}
      <div className="chips">
        {[...adj.claim_level_denials, ...adj.line_outcomes.flatMap((lo) => lo.denials)]
          .map((d, i) => <CarcChip key={i} denial={d} />)}
      </div>

      <details>
        <summary>claim JSON</summary>
        <pre>{JSON.stringify(attempt.claim, null, 2)}</pre>
      </details>

      {res && (
        <div className="resolution">
          <h4>
            Denial resolver: <Badge kind="info">{res.decision.action.replaceAll("_", " ")}</Badge>
          </h4>
          <p>{res.decision.rationale}</p>
          {res.decision.field_fixes.length > 0 && (
            <p className="notes">
              field fixes: {res.decision.field_fixes.map((f) => `${f.field}=${f.value}`).join(", ")}
            </p>
          )}
          {res.decision.appeal_letter && (
            <blockquote>{res.decision.appeal_letter}</blockquote>
          )}
        </div>
      )}
      {attempt.appeal && (
        <div className="resolution">
          <h4>
            Appeal review: <Badge kind={attempt.appeal.decision === "overturned" ? "ok" : "bad"}>
              {attempt.appeal.decision}
            </Badge>
          </h4>
          <p>{attempt.appeal.explanation}</p>
        </div>
      )}
    </section>
  );
}

function Meta({ stage }) {
  return (
    <span className="meta">
      {stage.seconds}s, {stage.usage.input_tokens} in / {stage.usage.output_tokens} out
    </span>
  );
}

function FinalBanner({ run }) {
  const f = run.final;
  if (!f) return null;
  const kind = f.status === "accepted" ? "ok" : "bad";
  return (
    <section className={`final final-${kind}`}>
      <strong>{f.status.toUpperCase()}</strong>
      <span>
        {f.first_pass_accepted
          ? "clean claim on the first pass"
          : f.resolved_after_denial
            ? `denied, then recovered by the loop in ${f.attempts_used} attempts`
            : `still ${f.status} after ${f.attempts_used} attempt(s)`}
        {f.status === "accepted" && <> , paid {money(f.paid_total_cents)}</>}
      </span>
      <span className="meta">
        {run.usage_totals.input_tokens} tokens in, {run.usage_totals.output_tokens} out,
        {" "}{run.total_seconds}s total
      </span>
    </section>
  );
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [encounters, setEncounters] = useState([]);
  const [selected, setSelected] = useState("");
  const [customText, setCustomText] = useState("");
  const [useCustom, setUseCustom] = useState(false);
  const [cheap, setCheap] = useState(false);
  const [run, setRun] = useState(null);
  const [error, setError] = useState("");
  const pollRef = useRef(null);

  useEffect(() => {
    getHealth().then(setHealth).catch((e) => setError(String(e)));
    getEncounters()
      .then((rows) => {
        setEncounters(rows);
        if (rows.length) setSelected(rows[0].encounter_id);
      })
      .catch(() => setEncounters([]));
    return () => clearInterval(pollRef.current);
  }, []);

  const launch = async () => {
    setError("");
    setRun(null);
    try {
      const payload = useCustom
        ? { custom_transcript: customText, cheap }
        : { encounter_id: selected, cheap };
      const { run_id } = await startRun(payload);
      pollRef.current = setInterval(async () => {
        try {
          const r = await getRun(run_id);
          setRun(r);
          if (r.status === "done" || r.status === "error") clearInterval(pollRef.current);
        } catch (e) {
          clearInterval(pollRef.current);
          setError(String(e));
        }
      }, 1200);
    } catch (e) {
      setError(String(e));
    }
  };

  const running = run && run.status === "running";

  return (
    <div className="page">
      <header className="top">
        <h1>ClaimLoop</h1>
        <p>
          transcript to claim to denial to resubmission, one encounter at a time.
          A teaching demo, not a billing product.
        </p>
        {health && (
          <div className="chips">
            <Badge kind={health.api_key_present ? "ok" : "bad"}>
              {health.api_key_present ? "API key loaded" : "no API key"}
            </Badge>
            <Badge kind={health.data_present ? "ok" : "bad"}>
              {health.data_present ? "data ready" : "run fetch_data.py"}
            </Badge>
            <Badge kind="info">{cheap ? health.models.cheap : health.models.main}</Badge>
          </div>
        )}
      </header>

      <section className="card controls">
        <div className="row">
          <label>
            <input type="radio" checked={!useCustom} onChange={() => setUseCustom(false)} />
            ACI-Bench encounter
          </label>
          <label>
            <input type="radio" checked={useCustom} onChange={() => setUseCustom(true)} />
            paste a transcript
          </label>
          <label className="right">
            <input type="checkbox" checked={cheap} onChange={(e) => setCheap(e.target.checked)} />
            cheap model tier
          </label>
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
          <textarea
            rows={7}
            placeholder="[doctor] hi there, what brings you in today? [patient] ..."
            value={customText}
            onChange={(e) => setCustomText(e.target.value)}
          />
        )}

        <button onClick={launch} disabled={running || (!useCustom && !selected)}>
          {running ? `running: ${run.current_stage}...` : "run the claim lifecycle"}
        </button>
        {error && <p className="error">{error}</p>}
      </section>

      {run && run.status === "error" && (
        <section className="card"><p className="error">{run.error}</p></section>
      )}

      {run && run.stages.scribe && <NoteCard stage={run.stages.scribe} />}
      {run && run.stages.coding && <CodingCard stage={run.stages.coding} />}
      {run && run.attempts.map((a) => <AttemptCard key={a.attempt} attempt={a} />)}
      {run && <FinalBanner run={run} />}

      <footer>
        Portfolio demo by Abdullah Abdel-Khalek. Simulated payer, public simulated
        dataset, no real patient data. Not medical or billing advice.
      </footer>
    </div>
  );
}
