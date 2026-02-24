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

import { saveGraph, loadFunctions, loadRules, loadGraph, loadFirstRuleGraph } from './api/api'


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

  const [rules, setRules] = useState([])

  const ruleEngineId = 1


  useEffect(() => {

    async function fetchData() {

      try {

        await loadFunctions().then((funcs) => setFunctions(funcs))

        await loadRules().then((ruls) => setRules(ruls))

        const graph = await loadFirstRuleGraph()

        console.log("Graph data:", graph)

        if (graph && graph.reactflow_json) {
          let { nodes: graphNodes, edges: graphEdges } = graph.reactflow_json
          // Add position to nodes if missing
          graphNodes = graphNodes.map((node, index) => ({
            ...node,
            position: node.position || { x: index * 200, y: 100 },
            type: node.type || 'ruleNode'
          }))
          console.log("Setting nodes:", graphNodes)
          console.log("Setting edges:", graphEdges)
          setNodes(graphNodes)
          setEdges(graphEdges)
        }

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

    const newNode = {

      id: `${nodeId}`,

      type: 'ruleNode',

      position: {

        x: Math.random() * 400,

        y: Math.random() * 400,

      },

      data: {

        label: selectedFunction,

      },

    }

    nodeId++

    setNodes((nds) => [...nds, newNode])

    setShowDialog(false)

    setSelectedFunction('')

  }


  const saveWorkflow = async () => {

    await saveGraph(ruleEngineId, nodes, edges)

    alert("Workflow saved")

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

        <h3>Existing Rules</h3>

        <ul style={{ listStyle: 'none', padding: 0 }}>

          {rules.map((rule) => (
            <li key={rule.id} style={{ marginBottom: 10, padding: 5, border: '1px solid #ddd', borderRadius: 3 }}>
              {rule.rule_name}
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

        <button onClick={saveWorkflow} style={{ marginLeft: 10 }}>
          Save Workflow
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
                <option key={func.id} value={func.name}>{func.name}</option>
              ))}

            </select>

            <button onClick={handleAddNode} style={{ marginRight: 10 }}>Add</button>

            <button onClick={() => { setShowDialog(false); setSelectedFunction(''); }}>Cancel</button>

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
