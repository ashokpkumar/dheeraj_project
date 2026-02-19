const API_BASE = "http://localhost:8000/api";


export async function loadGraph(ruleEngineId) {

  const res = await fetch(`${API_BASE}/rule_graph/${ruleEngineId}/`);

  return await res.json();
}


export async function saveGraph(ruleEngineId, nodes, edges) {
console.log("Saving graph:", { nodes, edges }),
  await fetch(`${API_BASE}/save_graph/${ruleEngineId}/`, {

    method: "POST",

    headers: {
      "Content-Type": "application/json",
    },
    
    body: JSON.stringify({
      nodes,
      edges,
    }),

  });

}
