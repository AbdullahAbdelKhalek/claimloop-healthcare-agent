import React from "react";

const STAGES = [
  { key: "scribe", name: "Scribe", desc: "transcript to visit note", agent: true },
  { key: "coder", name: "Coder", desc: "ICD-10-CM + CPT, verified", agent: true },
  { key: "claim", name: "Claim builder", desc: "professional claim assembly", agent: false },
  { key: "payer", name: "Payer", desc: "rules adjudication", agent: false },
  { key: "resolver", name: "Denial resolver", desc: "fix, auth, appeal", agent: true },
];

export default function StageRail({ stages, attempts, models }) {
  return (
    <nav className="rail panel">
      <p className="section-label">Pipeline</p>
      {STAGES.map((st) => {
        const status = stages[st.key];
        return (
          <div key={st.key} className={`rail-node ${status}`}>
            <span className="dot">
              {status === "done" && "✓"}
              {status === "failed" && "✕"}
            </span>
            <span className="rail-text">
              <strong>
                {st.name}
                {st.agent ? <em className="tag-agent">agent</em> : <em className="tag-code">code</em>}
                {attempts > 1 && (st.key === "payer" || st.key === "claim") && (
                  <em className="tag-attempt">submission {attempts}</em>
                )}
              </strong>
              <small>
                {st.desc}
                {st.agent && models && models[st.key] ? ` · ${models[st.key]}` : ""}
              </small>
            </span>
          </div>
        );
      })}
    </nav>
  );
}
