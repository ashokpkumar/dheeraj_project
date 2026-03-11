import React, { useState, useCallback, useEffect } from 'react'

import {
  ReactFlow,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
  Controls,
  Background,
} from '@xyflow/react'

import '@xyflow/react/dist/style.css'

import RuleNode from './components/RuleNode'

import { saveGraph, loadFunctions, loadRules, loadGraph, loadFirstRuleGraph, deleteRule, executeRule } from './api/api'


let nodeId = 1


const nodeTypes = {

  ruleNode: RuleNode,

}


export default function App() {

  const [nodes, setNodes] = useState([])
  const [edges, setEdges] = useState([])
  const [functions, setFunctions] = useState([])
  const [showDialog, setShowDialog] = useState(false)
  const [selectedFunction, setSelectedFunction] = useState('')
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [ruleName, setRuleName] = useState('')
  const [currentRuleId, setCurrentRuleId] = useState(null)
  const [showParamDialog, setShowParamDialog] = useState(false)
  const [pendingConnection, setPendingConnection] = useState(null)
  const [pendingNodeId, setPendingNodeId] = useState(null) // track node being configured
  const [connectionParams, setConnectionParams] = useState({})
  const [targetFunctionInputs, setTargetFunctionInputs] = useState([])
  const [rules, setRules] = useState([])
  const [dashboardData, setDashboardData] = useState([])
  const [dateDetails, setDateDetails] = useState([])
  const [selectedDate, setSelectedDate] = useState(null)

  const fetchDashboardData = async () => {
    try {
      const res = await fetch('http://127.0.0.1:8000/rule_engine/dashboard/?aggregate=true&group_by=day')
      if (!res.ok) throw new Error(`Dashboard API error: ${res.status}`)
      const data = await res.json()
      setDashboardData(data?.results || [])
      setDateDetails([])
      setSelectedDate(null)
    } catch (error) {
      console.error('Error loading dashboard data:', error)
      // Fallback static data while backend unavailable
      setDashboardData([
        { period_start: '2026-03-10', claims_count: 300 },
        { period_start: '2026-03-11', claims_count: 35 },
      ])
      setDateDetails([])
      setSelectedDate(null)
    }
  }

  const fetchDateDetails = async (date) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/rule_engine/dashboard/?start_date=${date}&end_date=${date}`)
      if (!res.ok) throw new Error(`Details API error: ${res.status}`)
      const data = await res.json()
      setDateDetails(data?.results || [])
      setSelectedDate(date)
    } catch (error) {
      console.error('Error loading date details:', error)
      // Fallback static data while backend unavailable
      setDateDetails([
        {
          id: 1,
          rule_engine: { id: 2002, rule_name: 'scrap_cps_750' },
          processed_at: `${date}T11:38:46.966628Z`,
          claims_count: 100,
        },
        {
          id: 2,
          rule_engine: { id: 2002, rule_name: 'scrap_cps_750' },
          processed_at: `${date}T11:44:24.132887Z`,
          claims_count: 100,
        },
        {
          id: 1002,
          rule_engine: { id: 2002, rule_name: 'scrap_cps_750' },
          processed_at: `${date}T11:48:55.780532Z`,
          claims_count: 100,
        },
      ])
      setSelectedDate(date)
    }
  }

  useEffect(() => {
    console.log('useEffect running');
    async function fetchData() {
      console.log('fetchData called');
      try {
        await loadFunctions().then((funcs) => setFunctions(Array.isArray(funcs) ? funcs : []))
        await loadRules().then((ruls) => setRules(Array.isArray(ruls) ? ruls : []))
        await fetchDashboardData()
      } catch (error) {
        console.error("Error loading data:", error)
      }
    }
    fetchData()
  }, [])


  const onNodesChange = useCallback(
    (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
    []
  )


  const onEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    []
  )


  const onConnect = useCallback(
    (params) => {
      // simply add the edge when two existing nodes are connected
      const newEdge = {
        ...params,
        id: `${params.source}-${params.target}-${Date.now()}`,
      }
      setEdges((eds) => addEdge(newEdge, eds))
    },
    []
  )

    const handleConfirmConnection = () => {

    // if we were configuring a newly added node
    if (pendingNodeId) {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === pendingNodeId
            ? { ...n, data: { ...n.data, params: connectionParams } }
            : n
        )
      )
      setPendingNodeId(null)
      setShowParamDialog(false)
      setConnectionParams({})
      return
    }

    if (!pendingConnection) return

    // update target node params (edge itself doesn’t carry params)
    setNodes((nds) =>
      nds.map((n) =>
        n.id === pendingConnection.target
          ? { ...n, data: { ...n.data, params: connectionParams } }
          : n
      )
    )

    const newEdge = {
      ...pendingConnection,
      id: `${pendingConnection.source}-${pendingConnection.target}-${Date.now()}`,
      // no label or data for params
    }

    setEdges((eds) => addEdge(newEdge, eds))

    setShowParamDialog(false)
    setPendingConnection(null)
    setConnectionParams({})
  }


  const addNode = () => {
    setShowDialog(true)
  }


  const handleAddNode = () => {
    if (!selectedFunction) return

    const currentId = nodeId

    const newNode = {
      id: `${currentId}`,
      type: 'ruleNode',
      position: {
        x: Math.random() * 400,
        y: Math.random() * 400,
      },
      data: {
        label: selectedFunction,
        onDelete: () => setNodes((nds) => nds.filter((n) => n.id !== `${currentId}`)),
      },
    }

    nodeId++
    setNodes((nds) => [...nds, newNode])
    setShowDialog(false)
    setSelectedFunction('')

    // immediately prompt for parameters for this new node
    const functionMeta = functions.find((f) => f.function_name === selectedFunction)
    const inputs = functionMeta?.inputs || []
    setTargetFunctionInputs(inputs)
    const initialParams = {}
    inputs.forEach((input) => {
      initialParams[input.name] = ''
    })
    setConnectionParams(initialParams)
    setPendingNodeId(`${currentId}`)
    setPendingConnection(null)
    setShowParamDialog(true)
  }


const handleSaveWorkflow = async () => {
  if (!ruleName.trim()) return

  // Transform nodes and edges to the desired format expected by the API
  const transformedNodes = nodes.map((node) => ({
    id: node.id,
    data: {
      function_name: node.data.label,
      params: node.data.params || {},
    },
  }))

  const transformedEdges = edges.map((edge) => ({
    source: edge.source,
    target: edge.target,
  }))

  try {
    await saveGraph( ruleName, transformedNodes, transformedEdges)

    alert("Workflow saved")

    setShowSaveDialog(false)
    setRuleName("")

    const updatedRules = await loadRules()
    setRules(Array.isArray(updatedRules) ? updatedRules : [])

  } catch (error) {
    console.error("Save failed:", error)
    alert("Failed to save workflow")
  }
}

  const loadRule = async (ruleId) => {
    const graph = await loadGraph(ruleId)

    if (graph && graph.reactflow_json) {
      let { nodes: graphNodes, edges: graphEdges } = graph.reactflow_json

      graphNodes = graphNodes.map((node, index) => ({
        id: node.id,
        type: 'ruleNode',
        position: node.position || { x: index * 200, y: 100 },
        data: {
          label: node.data?.label || node.data?.function_name, // 🔥 important
          params: node.data?.params || {},
          onDelete: () =>
            setNodes((nds) => nds.filter((n) => n.id !== node.id)),
        },
      }))

      setNodes(graphNodes)
      setEdges(graphEdges)

      const maxId =
        graphNodes.length > 0
          ? Math.max(...graphNodes.map((n) => parseInt(n.id)))
          : 0

      nodeId = maxId + 1
    }

    setCurrentRuleId(ruleId)
  }


  const createNewRule = () => {

    setNodes([])

    setEdges([])

    nodeId = 1

    setCurrentRuleId(null)

  }


  const handleDeleteRule = async (ruleId) => {

    await deleteRule(ruleId)

    const updatedRules = await loadRules()

    setRules(Array.isArray(updatedRules) ? updatedRules : [])

  }


  const executeFlow = async () => {

    if (!currentRuleId) {

      alert("No rule loaded to execute")

      return

    }

    try {

      const result = await executeRule(currentRuleId)

      alert("Execution result: " + JSON.stringify(result))

    } catch (error) {

      console.error("Execution failed:", error)

      alert("Failed to execute flow")

    }

  }


  return (
    <div style={{ width: '100vw', height: '100vh', position: 'relative' }}>


      <div style={{

        position: 'absolute',

        left: 0,

        top: 0,

        width: 250,

        height: '100%',
        background: '#f8fbff',
        borderRight: '1px solid #d8dded',
        padding: '16px 12px',
        zIndex: 5,
        overflowY: 'auto',
      }}>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>

          <h3>Existing Rules</h3>

          <button onClick={createNewRule}>+</button>

        </div>

        <ul style={{ listStyle: 'none', padding: 0 }}>

          {rules.map((rule) => (
            <li key={rule.id} style={{ marginBottom: 10, padding: 5, border: '1px solid #ddd', borderRadius: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span onClick={() => loadRule(rule.id)} style={{ cursor: 'pointer', flex: 1 }}>{rule.rule_name}</span>
              <button onClick={() => handleDeleteRule(rule.id)} style={{ marginLeft: 10 }}>-</button>
            </li>
          ))}

        </ul>

      </div>


      <div style={{

        position: 'absolute',

        zIndex: 10,

        top: 10,

        left: 270,

        right: '30vw',

        background: 'transparent',

        padding: '8px 10px',

        borderRadius: 6,
        border: 'none',
        boxShadow: 'none',
      }}>

        <button onClick={addNode} style={{ background: '#00438f', color: 'white', border: 'none', borderRadius: 4, padding: '6px 12px', cursor: 'pointer' }}>
          Add Function
        </button>

        <button onClick={() => setShowSaveDialog(true)} style={{ marginLeft: 10, background: '#0062c4', color: 'white', border: 'none', borderRadius: 4, padding: '6px 12px', cursor: 'pointer' }}>
          Save Workflow
        </button>

        <button onClick={executeFlow} style={{ marginLeft: 10, background: '#0853b2', color: 'white', border: 'none', borderRadius: 4, padding: '6px 12px', cursor: 'pointer' }}>
          Execute Flow
        </button>

      </div>

      <div style={{
        position: 'fixed',
        right: 0,
        top: 0,
        bottom: 0,
        width: '30vw',
        background: '#f6f8fb',
        borderLeft: '1px solid #d8dde5',
        padding: 12,
        zIndex: 5,
        overflowY: 'auto',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: '1.1rem', color: '#002f6c' }}>Processing Dashboard</h3>
          <button onClick={fetchDashboardData} style={{ fontSize: '0.8rem', background: '#00438f', color: 'white', border: 'none', borderRadius: 4, padding: '5px 8px', cursor: 'pointer' }}>Refresh</button>
        </div>

        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 1, minWidth: 0, background: 'white', border: '1px solid #d8dde5', borderRadius: 8, padding: 10, boxShadow: '0 2px 6px rgba(0,0,0,0.05)', height: 'calc(100% - 44px)', overflowY: 'auto' }}>
            <div style={{ marginBottom: 8, fontWeight: '600', color: '#073c71' }}>Aggregated per day</div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', borderBottom: '1px solid #d8dde5', padding: '6px 4px', color: '#0f3d84' }}>Date</th>
                  <th style={{ textAlign: 'right', borderBottom: '1px solid #d8dde5', padding: '6px 4px', color: '#0f3d84' }}>Claims</th>
                </tr>
              </thead>
              <tbody>
                {dashboardData.length === 0 && (
                  <tr><td colSpan={2} style={{ padding: '6px 4px', color: '#5d6779' }}>No data yet</td></tr>
                )}
                {dashboardData.map((item) => (
                  <tr key={item.period_start} onClick={() => fetchDateDetails(item.period_start)} style={{ cursor: 'pointer', background: selectedDate === item.period_start ? '#e4f0ff' : 'transparent' }}>
                    <td style={{ padding: '6px 4px' }}>{item.period_start}</td>
                    <td style={{ padding: '6px 4px', textAlign: 'right' }}>{item.claims_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ flex: 1, minWidth: 0, background: 'white', border: '1px solid #d8dde5', borderRadius: 8, padding: 10, boxShadow: '0 2px 6px rgba(0,0,0,0.05)', height: 'calc(100% - 44px)', overflowY: 'auto' }}>
            <div style={{ marginBottom: 8, fontWeight: '600', color: '#073c71' }}>Date-wise details</div>
            {!selectedDate && <div style={{ color: '#5d6779', marginBottom: 8 }}>Click a row in aggregated table to view details.</div>}
            {selectedDate && <div style={{ marginBottom: 8, color: '#1f4e92' }}>Showing: {selectedDate}</div>}
            {selectedDate && (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: 'left', borderBottom: '1px solid #d8dde5', padding: '6px 4px', color: '#0f3d84' }}>Date</th>
                    <th style={{ textAlign: 'left', borderBottom: '1px solid #d8dde5', padding: '6px 4px', color: '#0f3d84' }}>Rule Name</th>
                    <th style={{ textAlign: 'right', borderBottom: '1px solid #d8dde5', padding: '6px 4px', color: '#0f3d84' }}>Claims</th>
                  </tr>
                </thead>
                <tbody>
                  {dateDetails.length === 0 && (
                    <tr><td colSpan={3} style={{ padding: '6px 4px', color: '#5d6779' }}>No details for the selected date.</td></tr>
                  )}
                  {dateDetails.map((item) => (
                    <tr key={item.id} style={{ borderBottom: '1px solid #eef2f6' }}>
                      <td style={{ padding: '6px 4px' }}>{new Date(item.processed_at).toISOString().split('T')[0]}</td>
                      <td style={{ padding: '6px 4px' }}>{item.rule_engine?.rule_name || '-'}</td>
                      <td style={{ padding: '6px 4px', textAlign: 'right' }}>{item.claims_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {showDialog && (
        <div style={{

          position: 'fixed',

          top: 0,

          left: 0,

          width: '100%',
          height: '100%',
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000,

        }}>

          <div style={{

            background: 'white',

            padding: 20,

            borderRadius: 5,

            minWidth: 300,

          }}>

            <h3>Select Function</h3>

            <select

              value={selectedFunction}

              onChange={(e) => setSelectedFunction(e.target.value)}

              style={{ width: '100%', padding: 5, marginBottom: 10 }}>

              <option value="">Choose a function</option>

              {functions.map((func) => (
                <option key={func.function_name} value={func.function_name}>{func.function_name}</option>
              ))}

            </select>

            <button onClick={handleAddNode} style={{ marginRight: 10 }}>Add</button>

            <button onClick={() => { setShowDialog(false); setSelectedFunction(''); }}>Cancel</button>

          </div>

        </div>

      )}

      {showParamDialog && (
        <div style={modalOverlay}>
          <div style={modalBox}>
            <h3>Enter Parameters</h3>

            {targetFunctionInputs.map((input) => (
              <div key={input.name} style={{ marginBottom: 10 }}>
                <label>{input.name} ({input.type})</label>
                <input
                  type="text"
                  value={connectionParams[input.name] || ""}
                  onChange={(e) =>
                    setConnectionParams(prev => ({
                      ...prev,
                      [input.name]: e.target.value
                    }))
                  }
                  style={{ width: '100%', padding: 5 }}
                />
              </div>
            ))}

            <button onClick={handleConfirmConnection} style={{ marginRight: 10 }}>
              Confirm
            </button>
            <button
              onClick={() => {
                setShowParamDialog(false)
                setPendingConnection(null)
                setPendingNodeId(null)
                setConnectionParams({})
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {showSaveDialog && (
        <div style={{

          position: 'fixed',

          top: 0,

          left: 0,

          width: '100%',
          height: '100%',
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 1000,

        }}>

          <div style={{

            background: 'white',

            padding: 20,

            borderRadius: 5,

            minWidth: 300,

          }}>

            <h3>Enter Rule Name</h3>

            <input

              type="text"

              value={ruleName}

              onChange={(e) => setRuleName(e.target.value)}

              placeholder="Rule Name"

              style={{ width: '100%', padding: 5, marginBottom: 10 }}

            />

            <button onClick={handleSaveWorkflow} style={{ marginRight: 10 }}>Save</button>

            <button onClick={() => { setShowSaveDialog(false); setRuleName(''); }}>Cancel</button>

          </div>

        </div>

      )}


      <ReactFlow

        nodes={nodes}

        edges={edges}

        nodeTypes={nodeTypes}

        onNodesChange={onNodesChange}

        onEdgesChange={onEdgesChange}

        onConnect={onConnect}

        fitView

        style={{ position: 'absolute', left: 250, top: 0, width: 'calc(100vw - 250px - 30vw)', height: '100vh' }}>

        <Controls />

        <Background />

      </ReactFlow>


    </div>

  )

}

const modalOverlay = {
  position: 'fixed',
  top: 0,
  left: 0,
  width: '100%',
  height: '100%',
  background: 'rgba(0,0,0,0.5)',
  display: 'flex',
  justifyContent: 'center',
  alignItems: 'center',
  zIndex: 1000,
}

const modalBox = {
  background: 'white',
  padding: 20,
  borderRadius: 5,
  minWidth: 350,
}