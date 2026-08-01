import React, { useEffect, useRef } from "react";

function ToolRow({ tool }) {
  return (
    <div className="tool">
      <span className="tool-call">
        tool&gt; {tool.name}({tool.args})
      </span>
      {tool.result === null
        ? <span className="tool-wait">running...</span>
        : tool.result && <span className="tool-result">{"->"} {tool.result}</span>}
    </div>
  );
}

export default function Console({ blocks, live }) {
  const endRef = useRef(null);
  useEffect(() => {
    endRef.current && endRef.current.scrollIntoView({ block: "nearest" });
  });

  return (
    <section className="panel console">
      <p className="section-label" style={{ fontFamily: "var(--sans)" }}>Agent activity</p>
      {!blocks.length && (
        <div className="console-empty">
          model output, tool calls, and retries will appear here as the agents work
        </div>
      )}
      {blocks.map((b, i) => {
        const isLast = i === blocks.length - 1;
        return (
          <div key={i} className={`block ${b.done ? "done" : "active"}`}>
            <div className="block-head">
              <span className={`pulse ${b.done ? "off" : ""}`} />
              <span>{b.label || b.stage}</span>
              {b.model && <span className="model-chip">{b.model}</span>}
            </div>
            {b.reasoning && <div className="reasoning">{b.reasoning}</div>}
            {b.tools.map((t, j) => <ToolRow key={j} tool={t} />)}
            {b.text && (
              <pre className="stream">
                {b.text}
                {isLast && live && !b.done && <span className="caret" />}
              </pre>
            )}
            {!b.text && !b.tools.length && !b.done && (
              <div className="thinking">model is thinking<span className="dots" /></div>
            )}
          </div>
        );
      })}
      <div ref={endRef} />
    </section>
  );
}
