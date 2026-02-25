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

    const [rules, setRules] = useState([])

  useEffect(() => {
    console.log('useEffect running');
    async function fetchData() {
      console.log('fetchData called');
      try {
        await loadFunctions().then((funcs) => setFunctions(Array.isArray(funcs) ? funcs : []))
        await loadRules().then((ruls) => setRules(Array.isArray(ruls) ? ruls : []))
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

      const condition = prompt("Enter condition (true / false):")

      const newEdge = {

        ...params,

        id: `${params.source}-${params.target}-${condition}`,

        label: condition,

      }

      setEdges((eds) => addEdge(newEdge, eds))

    },
    []
  )


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

  }


const handleSaveWorkflow = async () => {
  if (!ruleName.trim()) return

  // Transform nodes and edges to the desired format
  const transformedNodes = nodes.map(node => ({
    id: node.id,
    data: {
      function_name: node.data.label,
      params: {}  // Placeholder for params; can be extended to include actual params
    }
  }))

  const transformedEdges = edges.map(edge => ({
    source: edge.source,
    target: edge.target
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

        ...node,

        position: node.position || { x: index * 200, y: 100 },

        type: node.type || 'ruleNode'

      }))

      setNodes(graphNodes)

      setEdges(graphEdges)

      // Update nodeId to the next available id
      const maxId = graphNodes.length > 0 ? Math.max(...graphNodes.map(n => parseInt(n.id))) : 0
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
        background: 'white',
        borderRight: '1px solid #ccc',
        padding: 10,
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

        background: 'white',

        padding: 10,

        borderRadius: 5,

      }}>

        <button onClick={addNode}>
          Add Function
        </button>

        <button onClick={() => setShowSaveDialog(true)} style={{ marginLeft: 10 }}>
  Save Workflow
</button>

        <button onClick={executeFlow} style={{ marginLeft: 10 }}>
          Execute Flow
        </button>

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

        style={{ position: 'absolute', left: 250, top: 0, width: 'calc(100vw - 250px)', height: '100vh' }}>

        <Controls />

        <Background />

      </ReactFlow>


    </div>

  )

}
