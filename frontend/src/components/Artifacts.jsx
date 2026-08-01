import React from "react";

const money = (cents) => `$${(cents / 100).toFixed(2)}`;
const DX_LETTERS = "ABCDEFGHIJKL";

export function NoteCard({ stage }) {
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
    <section className="panel card appear">
      <header>
        <h3>Visit note</h3>
        <span className="meta">{stage.model} · {stage.seconds}s</span>
      </header>
      <dl>
        {rows.map(([k, v]) => (
          <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
        ))}
        <div>
          <dt>Assessment and plan</dt>
          <dd>
            <ol>
              {n.assessment_and_plan.map((ap, i) => (
                <li key={i}><strong>{ap.problem}.</strong> {ap.assessment} <em>{ap.plan}</em></li>
              ))}
            </ol>
          </dd>
        </div>
      </dl>
    </section>
  );
}

function Confidence({ value }) {
  return (
    <span className="conf">
      <span className="conf-track"><span className="conf-bar" style={{ width: `${Math.round(value * 100)}%` }} /></span>
      <span className="conf-num">{value.toFixed(2)}</span>
    </span>
  );
}

export function CodingCard({ stage }) {
  const c = stage.coding;
  return (
    <section className="panel card appear">
      <header>
        <h3>Billing codes</h3>
        <span className="meta">{stage.model} · {stage.seconds}s</span>
      </header>
      <table>
        <thead><tr><th>#</th><th>ICD-10-CM</th><th>description</th><th>confidence</th></tr></thead>
        <tbody>
          {c.diagnoses.map((d, i) => (
            <tr key={d.icd10_code + i}>
              <td>{DX_LETTERS[i] || i + 1}</td>
              <td><code>{d.icd10_code}</code></td>
              <td>{d.description}<div className="rationale">{d.rationale}</div></td>
              <td><Confidence value={d.confidence} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <table>
        <thead><tr><th>CPT</th><th>description</th><th>dx links</th><th>confidence</th></tr></thead>
        <tbody>
          {c.procedures.map((p, i) => (
            <tr key={p.cpt_code + i}>
              <td><code>{p.cpt_code}</code></td>
              <td>{p.description}<div className="rationale">{p.rationale}</div></td>
              <td>{p.dx_pointers.map((n) => DX_LETTERS[n - 1] || n).join(", ")}</td>
              <td><Confidence value={p.confidence} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {c.coding_notes && <p className="notes">{c.coding_notes}</p>}
    </section>
  );
}

export function ClaimDocument({ claim }) {
  const p = claim.patient;
  return (
    <div className="claim-doc">
      <div className="claim-doc-head">
        <span>Professional claim <strong>{claim.claim_id}</strong></span>
        <span>
          service date {claim.service_date} · submission {claim.attempt}
          {claim.resubmission_of && <> · corrects <strong>{claim.resubmission_of}</strong></>}
        </span>
      </div>
      <div className="claim-parties">
        <div className="claim-party">
          <p className="section-label">Patient</p>
          <div>{p.first_name} {p.last_name}</div>
          <div className="sub">
            {p.gender}, born {p.date_of_birth} · member {p.member_id}
          </div>
        </div>
        <div className="claim-party">
          <p className="section-label">Billing provider</p>
          <div>{claim.provider.name}</div>
          <div className="sub">NPI {claim.provider.npi}</div>
        </div>
        <div className="claim-party">
          <p className="section-label">Payer</p>
          <div>{claim.payer_id}</div>
          <div className="sub">simulated adjudication</div>
        </div>
      </div>
      <div className="claim-dx">
        <p className="section-label">Diagnoses</p>
        {claim.diagnoses.map((d, i) => (
          <span key={d.sequence} className="dx-item">
            <span className="dx-letter">{DX_LETTERS[i] || d.sequence}</span>
            <code>{d.icd10_code}</code>
            <span>{d.description}</span>
          </span>
        ))}
      </div>
      <div className="claim-lines">
        <table>
          <thead>
            <tr><th>#</th><th>CPT</th><th>service</th><th>units</th><th>dx</th><th>auth</th><th>charge</th></tr>
          </thead>
          <tbody>
            {claim.service_lines.map((l) => (
              <tr key={l.sequence}>
                <td>{l.sequence}</td>
                <td><code>{l.cpt_code}</code></td>
                <td>{l.description}</td>
                <td>{l.units}</td>
                <td>{l.dx_pointers.map((n) => DX_LETTERS[n - 1] || n).join(", ")}</td>
                <td>{l.prior_auth_number ? <span className="auth-num">{l.prior_auth_number}</span> : "-"}</td>
                <td>{money(l.charge_cents)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="claim-total">
        <span>total billed</span>
        <strong>{money(claim.total_charge_cents)}</strong>
      </div>
    </div>
  );
}

function CarcChip({ denial }) {
  return (
    <span className="carc" title={denial.description}>
      CO-{denial.carc}{denial.rarc ? ` / ${denial.rarc}` : ""}
    </span>
  );
}

export function AttemptCard({ attempt }) {
  const adj = attempt.adjudication;
  const res = attempt.resolution;
  const claim = attempt.claim;
  if (!claim) return null;
  const accepted = adj && adj.status === "accepted";
  return (
    <section className={`panel card appear attempt ${accepted ? "ok" : adj ? "bad" : ""}`}>
      <header>
        <h3>Submission {attempt.attempt}</h3>
        {adj && <span className={`stamp ${accepted ? "s-ok" : "s-bad"}`}>{adj.status}</span>}
      </header>

      <ClaimDocument claim={claim} />

      {accepted && (
        <p className="claim-line" style={{ marginTop: 8 }}>
          Paid <strong>{money(adj.paid_total_cents)}</strong> by the payer.
        </p>
      )}

      {adj && !accepted && (
        <>
          <ul className="remittance">
            {adj.remittance_notes.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
          <div className="chips">
            {[...adj.claim_level_denials, ...adj.line_outcomes.flatMap((lo) => lo.denials)]
              .map((d, i) => <CarcChip key={i} denial={d} />)}
          </div>
        </>
      )}

      <details>
        <summary>claim JSON</summary>
        <pre>{JSON.stringify(claim, null, 2)}</pre>
      </details>

      {res && (
        <div className="resolution">
          <h4>Resolver decision: <span className="badge b-info">{res.action.replaceAll("_", " ")}</span></h4>
          <p>{res.rationale}</p>
          {res.field_fixes && res.field_fixes.length > 0 && (
            <p className="notes">
              field fixes: {res.field_fixes.map((f) => `${f.field}=${f.value}`).join(", ")}
            </p>
          )}
          {res.appeal_letter && <blockquote>{res.appeal_letter}</blockquote>}
        </div>
      )}
      {attempt.appeal && (
        <div className="resolution">
          <h4>
            Appeal review:{" "}
            <span className={`badge ${attempt.appeal.decision === "overturned" ? "b-ok" : "b-bad"}`}>
              {attempt.appeal.decision}
            </span>
          </h4>
          <p>{attempt.appeal.explanation}</p>
        </div>
      )}
    </section>
  );
}

export function FinalBanner({ final, usage, seconds }) {
  const ok = final.status === "accepted";
  return (
    <section className={`panel final appear ${ok ? "f-ok" : "f-bad"}`}>
      <span className={`stamp ${ok ? "s-ok" : "s-bad"}`}>{final.status}</span>
      <div className="final-body">
        <p>
          {final.first_pass_accepted
            ? "Clean claim on the first pass."
            : final.resolved_after_denial
              ? `Denied, then recovered by the loop in ${final.attempts_used} submissions.`
              : `Still ${final.status} after ${final.attempts_used} submission(s).`}
          {ok && <> Paid <strong>{money(final.paid_total_cents)}</strong>.</>}
        </p>
        <div className="stats">
          {usage && <span>{usage.input_tokens.toLocaleString()} tok in</span>}
          {usage && <span>{usage.output_tokens.toLocaleString()} tok out</span>}
          {typeof final.estimated_cost_usd === "number" && (
            <span>est ${final.estimated_cost_usd.toFixed(4)}</span>
          )}
          {seconds && <span>{seconds}s</span>}
        </div>
      </div>
    </section>
  );
}
