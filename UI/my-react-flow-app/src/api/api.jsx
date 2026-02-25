const API_BASE = "/rule_engine";

export async function loadGraph(ruleEngineId) {
  console.log("Loading graph for rule engine ID:", ruleEngineId);
  const res = await fetch(`${API_BASE}/rules/${ruleEngineId}/`);
  const ret = await res.json();
  console.log("Graph data received:", ret);
  return ret;
}

export async function saveGraph(ruleName, nodes, edges) {
  const response = await fetch("http://127.0.0.1:8000/rule_engine/rules/save/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      rule_name: ruleName,
      nodes: nodes,
      edges: edges,
    }),
  })

  if (!response.ok) {
    throw new Error("Failed to save rule")
  }

  return await response.json()
}

export async function loadFunctions() {
  console.log('Calling loadFunctions API');
  const res = await fetch(`${API_BASE}/functions/`);
  console.log('loadFunctions response status:', res.status);
  const data = await res.json();
  console.log('loadFunctions data:', data);
  return data;
}

export async function loadRules() {
  console.log('Calling loadRules API');
  const res = await fetch(`${API_BASE}/rules/`);
  console.log('loadRules response status:', res.status);
  const data = await res.json();
  console.log('loadRules data:', data);
  return data;
}

export async function loadFirstRuleGraph() {
  const rules = await loadRules();
  if (rules && rules.length > 0) {
    return await loadGraph(rules[0].id);
  }
  return null;
}

export async function deleteRule(ruleId) {
  // placeholder API
  console.log('Deleting rule', ruleId);
  await fetch(`${API_BASE}/rules/${ruleId}/`, { method: 'DELETE' });
}

export async function executeRule(ruleId) {
  console.log('Executing rule', ruleId);
  const res = await fetch(`${API_BASE}/rules/${ruleId}/execute/`, { method: 'POST' });
  return await res.json();
}
