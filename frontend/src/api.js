async function json(resp) {
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${resp.status}: ${body}`);
  }
  return resp.json();
}

export const getHealth = () => fetch("/api/health").then(json);
export const getEncounters = () => fetch("/api/encounters").then(json);
export const getRun = (id) => fetch(`/api/runs/${id}`).then(json);

export const startRun = (payload) =>
  fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(json);
