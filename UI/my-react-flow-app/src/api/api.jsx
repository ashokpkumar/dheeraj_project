const API_BASE = "/rule_engine";

export async function loadGraph(ruleEngineId) {
  console.log("Loading graph for rule engine ID:", ruleEngineId);
  const res = await fetch(`${API_BASE}/rules/${ruleEngineId}/`);
  const ret = await res.json();
  console.log("Graph data received:", ret);
  return ret;
}

export async function saveGraph(ruleEngineId, nodes, edges) {
  console.log("Saving graph:", { nodes, edges });
  await fetch(`${API_BASE}/rules/save/`, {
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

export async function loadFunctions() {
  const res = await fetch(`${API_BASE}/functions/`);
  return await res.json();
}

export async function loadRules() {
  const res = await fetch(`${API_BASE}/rules/`);
  return await res.json();
}

export async function loadFirstRuleGraph() {
  const rules = await loadRules();
  if (rules && rules.length > 0) {
    return await loadGraph(rules[0].id);
  }
  return null;
}
