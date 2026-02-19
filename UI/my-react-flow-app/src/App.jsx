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

import { loadGraph, saveGraph } from './api/graphApi'


let nodeId = 1


const nodeTypes = {

  ruleNode: RuleNode,

}


export default function App() {

  const [nodes, setNodes] = useState([])

  const [edges, setEdges] = useState([])

  const ruleEngineId = 1


  useEffect(() => {

    async function fetchGraph() {

      try {

        const graph = await loadGraph(ruleEngineId)

        setNodes(graph.nodes)

        setEdges(graph.edges)

      } catch {

        console.log("No graph found, starting empty")

      }

    }

    fetchGraph()

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

    const functionName = prompt("Enter function name:")

    if (!functionName) return

    const newNode = {

      id: `${nodeId}`,

      type: 'ruleNode',

      position: {

        x: Math.random() * 400,

        y: Math.random() * 400,

      },

      data: {

        label: functionName,

      },

    }

    nodeId++

    setNodes((nds) => [...nds, newNode])

  }


  const saveWorkflow = async () => {

    await saveGraph(ruleEngineId, nodes, edges)

    alert("Workflow saved")

  }


  return (

    <div style={{ width: '100vw', height: '100vh' }}>


      <div style={{

        position: 'absolute',

        zIndex: 10,

        top: 10,

        left: 10,

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


      <ReactFlow

        nodes={nodes}

        edges={edges}

        nodeTypes={nodeTypes}

        onNodesChange={onNodesChange}

        onEdgesChange={onEdgesChange}

        onConnect={onConnect}

        fitView

      >

        <Controls />

        <Background />

      </ReactFlow>


    </div>

  )

}
