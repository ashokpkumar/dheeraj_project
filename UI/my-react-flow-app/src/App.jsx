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

import { saveGraph, loadFunctions, loadRules, loadGraph, loadFirstRuleGraph, deleteRule, executeRule, refreshFunctions } from './api/api'
import SchedulerPage from './components/SchedulerPage'
import ProcessingPage from './components/ProcessingPage'



const nodeTypes = {

  ruleNode: RuleNode,

}


export default function App() {

  const [nodes, setNodes] = useState([])
  const [edges, setEdges] = useState([])
  const [functions, setFunctions] = useState([])
  const [showDialog, setShowDialog] = useState(false)
  const [selectedFunction, setSelectedFunction] = useState('')
  const [funcSearch, setFuncSearch] = useState('')
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
  const [dashboardMeta, setDashboardMeta] = useState({})
  const [dateDetails, setDateDetails] = useState([])
  const [dateMeta, setDateMeta] = useState({})
  const [claimsSummary, setClaimsSummary] = useState(null)
  const [selectedDate, setSelectedDate] = useState(null)
  const [exportingRowId, setExportingRowId] = useState(null)
  const [dashboardExpanded, setDashboardExpanded] = useState(true)
  const [rulesExpanded, setRulesExpanded] = useState(true)
  const [isEditMode, setIsEditMode] = useState(false)
  const [currentPage, setCurrentPage] = useState('processing') // 'workflow' | 'scheduler'
  const [originalNodes, setOriginalNodes] = useState([])
  const [originalEdges, setOriginalEdges] = useState([])
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [editingFunctionMeta, setEditingFunctionMeta] = useState(null)

  // Refs keep latest nodes/functions accessible inside a stable callback
  const nodesRef = React.useRef(nodes)
  const functionsRef = React.useRef(functions)
  useEffect(() => { nodesRef.current = nodes }, [nodes])
  useEffect(() => { functionsRef.current = functions }, [functions])

  const handleEditParams = useCallback((nodeId) => {
    const node = nodesRef.current.find((n) => n.id === nodeId)
    if (!node) return

    const functionMeta = functionsRef.current.find((f) => f.function_name === node.data.label)
    const inputs = functionMeta?.inputs || []

    // Pre-fill with existing param values, falling back to declared default
    const prefilled = {}
    inputs.forEach((input) => {
      prefilled[input.name] = node.data.params?.[input.name] ?? input.default ?? ''
    })

    setTargetFunctionInputs(inputs)
    setConnectionParams(prefilled)
    setEditingFunctionMeta(functionMeta || null)
    setPendingNodeId(nodeId)
    setPendingConnection(null)
    setShowParamDialog(true)
  }, []) // stable — reads latest values via refs, never recreated

  const fetchDashboardData = async (options = {}) => {
    try {
      const { aggregate = true, group_by = 'day', page = 1, limit = 10 } = options
      const params = new URLSearchParams({
        aggregate: aggregate.toString(),
        group_by,
        page: page.toString(),
        limit: limit.toString(),
      })
      const res = await fetch(`http://127.0.0.1:8000/rule_engine/dashboard/?${params}`)
      if (!res.ok) throw new Error(`Dashboard API error: ${res.status}`)
      const data = await res.json()
      setDashboardData(data?.results || [])
      setDashboardMeta({
        current_page: data?.current_page || 1,
        total_pages: data?.total_pages || 1,
      })
      setDateDetails([])
      setSelectedDate(null)
    } catch (error) {
      console.error('Error loading dashboard data:', error)
      // Fallback static data while backend unavailable
    }
  }

 const handleEditRule = () => {
  if (!currentRuleId) {
    alert("Load a rule first to edit")
    return
  }

  // ✅ Backup current state before editing
  setOriginalNodes(nodes)
  setOriginalEdges(edges)

  setIsEditMode(true)
}

const handleCancelEdit = () => {
  // 🔁 Restore previous state
  setNodes(originalNodes)
  setEdges(originalEdges)

  setIsEditMode(false)
}

  const handleExportRowCsv = async (item) => {
    const rowDate = new Date(item.processed_at).toISOString().split('T')[0]
    const rule_name = item.rule_engine?.rule_name || ''
    const rowId = item.id

    setExportingRowId(rowId)

    const params = new URLSearchParams({ rule_engine_id: rowId,  rule_name })

    try {
      const res = await fetch(`http://127.0.0.1:8000/rule_engine/claims/export/?${params}`)
      if (!res.ok) throw new Error(`Export API error: ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let csvContent = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        csvContent += decoder.decode(value, { stream: true })
      }

      const blob = new Blob([csvContent], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `export_${rowDate}${rule_name ? `_${rule_name}` : ''}.csv`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Export failed:', error)
      alert('Failed to export CSV')
    } finally {
      setExportingRowId(null)
    }
  }

  const fetchDateDetails = async (date, options = {}) => {
    try {
      const { page = 1, limit = 10 } = options
      const params = new URLSearchParams({
        start_date: date,
        end_date: date,
        page: page.toString(),
        limit: limit.toString(),
      })
      const res = await fetch(`http://127.0.0.1:8000/rule_engine/dashboard/?${params}`)
      if (!res.ok) throw new Error(`Details API error: ${res.status}`)
      const data = await res.json()
      setDateDetails(data?.results || [])
      setDateMeta({
        current_page: data?.current_page || 1,
        total_pages: data?.total_pages || 1,
      })
      setClaimsSummary(data?.claims_summary || null)
      setSelectedDate(date)
    } catch (error) {
      console.error('Error loading date details:', error)
      // Fallback static data while backend unavailable
    }  
  }
  useEffect(() => {
    setNodes((nds) =>
      nds.map((node) => ({
        ...node,
        data: {
          ...node.data,
          isEditMode,
          onEditParams: isEditMode ? handleEditParams : null,
        },
      }))
    )
  }, [isEditMode]) // handleEditParams is stable (useCallback with no deps), safe to omit

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

  // Groups functions by tag for the color-coded dialog list
  const groupedFunctions = (search) => {
    const lower = search.toLowerCase()
    const filtered = lower
      ? functions.filter(f => f.function_name.toLowerCase().includes(lower))
      : functions
    const map = {}
    filtered.forEach(func => {
      const tag   = func.tag   || 'Other'
      const color = func.color || '#9e9e9e'
      if (!map[tag]) map[tag] = { tag, color, items: [] }
      map[tag].items.push(func)
    })
    return Object.values(map).sort((a, b) => {
      if (a.tag === 'Other') return 1
      if (b.tag === 'Other') return -1
      return a.tag.localeCompare(b.tag)
    })
  }


  const handleAddNode = () => {
    if (!selectedFunction) return

    const currentId = `node-${Date.now()}`

    const newNode = {
      id: `${currentId}`,
      type: 'ruleNode',
      position: {
        x: Math.random() * 400,
        y: Math.random() * 400,
      },
    data: {
      label: selectedFunction,
      isEditMode: isEditMode,
      onDelete: (nodeId) => {
        setNodes((nds) => nds.filter((n) => n.id !== nodeId))
        setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId))
      },
    },
    }

    setNodes((nds) => [...nds, newNode])
    setShowDialog(false)
    setSelectedFunction('')
    setFuncSearch('')

    // immediately prompt for parameters for this new node
    const functionMeta = functions.find((f) => f.function_name === selectedFunction)
    const inputs = functionMeta?.inputs || []
    setTargetFunctionInputs(inputs)
    setEditingFunctionMeta(functionMeta || null)
    const initialParams = {}
    inputs.forEach((input) => {
      initialParams[input.name] = input.default ?? ''
    })
    setConnectionParams(initialParams)
    setPendingNodeId(`${currentId}`)
    setPendingConnection(null)
    setShowParamDialog(true)
  }


const handleSaveWorkflow = async () => {
  if (!ruleName.trim() && !isEditMode) return

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
console.log(ruleName)
  try {
    if (isEditMode && currentRuleId) {
      // 🔥 EDIT FLOW
      await saveGraph(
        ruleName, 
        transformedNodes, 
        transformedEdges,
        currentRuleId   // ✅ send rule_id
      )
    } else {
      // 🆕 CREATE FLOW
      await saveGraph(
        ruleName,
        transformedNodes,
        transformedEdges
      )
    }

      alert(isEditMode ? "Workflow updated" : "Workflow saved")
  setNodes([])
    setEdges([])
    setIsEditMode(false)
    setShowSaveDialog(false)
     setCurrentRuleId(null)
     if (!isEditMode) {
    setRuleName("")
    
  }
     if (isEditMode) {
    setIsEditMode(false)  // ✅ exit edit mode — useEffect will sync isEditMode=false into all nodes
  }

    const updatedRules = await loadRules()
    setRules(Array.isArray(updatedRules) ? updatedRules : [])

  } catch (error) {
    console.error("Save failed:", error)
    alert(error.message)
  }
}


const loadRule = async (ruleId) => {
  const graph = await loadGraph(ruleId)

  console.log("GRAPH RESPONSE:", graph)

  if (graph) {

    // ✅ FIX IS HERE
    setRuleName(graph.rule_engine || "")
console.log(ruleName)
    if (graph.reactflow_json) {
      let { nodes: graphNodes, edges: graphEdges } = graph.reactflow_json

      graphNodes = graphNodes.map((node, index) => ({
        id: node.id,
        type: 'ruleNode',
        position: node.position || { x: index * 200, y: 100 },
        data: {
          label: node.data?.function_name,
          params: node.data?.params || {},
          isEditMode: false,
          onDelete: (nodeId) => {
            setNodes((prev) => prev.filter((n) => n.id !== nodeId))
            setEdges((prev) => prev.filter((e) => e.source !== nodeId && e.target !== nodeId))
          },
        },
      }))

      setNodes(graphNodes)
      setEdges(graphEdges)
    }
  }

  setCurrentRuleId(ruleId)
  setIsEditMode(false)
}


  const createNewRule = () => {
    setNodes([])
    setEdges([])
    setCurrentRuleId(null)
    setRuleName('')
    setIsEditMode(false)
  }


  const handleDeleteRule = async (ruleId) => {

    await deleteRule(ruleId)

    const updatedRules = await loadRules()

    setRules(Array.isArray(updatedRules) ? updatedRules : [])
    setNodes([])
    setEdges([])
    setCurrentRuleId(null)
    setRuleName('')
    setIsEditMode(false)

  }


  const executeFlow = async () => {

    if (!currentRuleId) {

      alert("No rule loaded to execute")

      return

    }

    try {

      const result = await executeRule(currentRuleId)

      alert("Execution result: Completed" )

    } catch (error) {

      console.error("Execution failed:", error)

      alert("Failed to execute flow")

    }

  }






















  return (
    <div style={{ width: '100vw', height: '100vh', position: 'relative' }}>

      {/* ── Top Nav Bar ── */}
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0, height: 42,
        background: '#002f6c', display: 'flex', alignItems: 'center',
        paddingLeft: 16, zIndex: 100, gap: 4,
      }}>
        <span style={{ color: 'white', fontWeight: 700, fontSize: '0.95rem', marginRight: 20, letterSpacing: '0.02em' }}>
          ⚙ Rule Engine
        </span>
        {[
           { id: 'processing', label: '⏱ Dashboard' },
          { id: 'workflow',  label: '⬡ Workflow' },
          { id: 'scheduler', label: '⏱ Scheduler' },
          
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setCurrentPage(tab.id)}
            style={{
              background: currentPage === tab.id ? 'white' : 'transparent',
              color: currentPage === tab.id ? '#002f6c' : 'rgba(255,255,255,0.75)',
              border: 'none', borderRadius: '4px 4px 0 0',
              padding: '6px 18px', cursor: 'pointer',
              fontWeight: currentPage === tab.id ? 700 : 400,
              fontSize: '0.875rem',
              transition: 'all 0.15s ease',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

        {currentPage === 'processing' && (
            <ProcessingPage
              dashboardData={dashboardData}
              dashboardMeta={dashboardMeta}
              dateDetails={dateDetails}
              dateMeta={dateMeta}
              claimsSummary={claimsSummary}
              selectedDate={selectedDate}
              fetchDashboardData={fetchDashboardData}
              fetchDateDetails={fetchDateDetails}
              handleExportRowCsv={handleExportRowCsv}
            />
          )}

      {/* ── Scheduler Page ── */}
      {currentPage === 'scheduler' && (
        <div style={{ paddingTop: 42, height: '100vh', overflowY: 'auto', background: '#eaf2f7' }}>
          <SchedulerPage />
        </div>
      )}

      {/* ── Workflow Page ── */}
      {currentPage === 'workflow' && (
      <>

      <div style={{

        position: 'fixed',

        left: 0,

        top: 42,

        width: rulesExpanded ? 250 : 40,

        height: '100%',
        background: '#f8fbff',
        borderRight: '1px solid #d8dded',
        padding: rulesExpanded ? '16px 12px' : 0,
        zIndex: 5,
        transition: 'width 0.3s ease',
        overflowY: 'auto',
      }}>
        <button
          onClick={() => setRulesExpanded(!rulesExpanded)}
          title={rulesExpanded ? 'Collapse' : 'Expand'}
          style={{
            position: 'absolute',
            left: '8px',
            top: '12px',
            background: '#00438f',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            padding: '6px 8px',
            cursor: 'pointer',
            fontSize: '1rem',
            zIndex: 10,
          }}
        >
          {rulesExpanded ? '←' : '→'}
        </button>

      {rulesExpanded && (
          <>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 30 }}>
          <h3>Existing Rules</h3>

          <button onClick={createNewRule}>+</button>

        </div>

        <ul style={{ listStyle: 'none', padding: 0 }}>

         {rules.map((rule) => {
              const isSelected = rule.id === currentRuleId
              return (
              <li
                key={rule.id}
                style={{
                  marginBottom: 10,
                  padding: 5,
                  border: `1px solid ${isSelected ? '#0062c4' : '#ddd'}`,
                  borderRadius: 3,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  background: isSelected ? '#dbeafe' : 'transparent',
                  fontWeight: isSelected ? '600' : 'normal',
                }}
              >
                <span
                  onClick={() => loadRule(rule.id)}
                  style={{ cursor: 'pointer', flex: 1, color: isSelected ? '#0062c4' : 'inherit' }}
                >
                  {rule.rule_name}
                </span>

                 {confirmDeleteId === rule.id ? (
  <>
    <button
      onClick={() => handleDeleteRule(rule.id)}
      style={{
        marginLeft: 10,
        background: '#dc2626',
        color: 'white',
        border: 'none',
        borderRadius: 4,
        padding: '2px 6px',
        cursor: 'pointer'
      }}
    >
      Confirm
    </button>

    <button
      onClick={() => setConfirmDeleteId(null)}
      style={{
        marginLeft: 5,
        background: '#6b7280',
        color: 'white',
        border: 'none',
        borderRadius: 4,
        padding: '2px 6px',
        cursor: 'pointer'
      }}
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            onClick={() => setConfirmDeleteId(rule.id)}
            style={{ marginLeft: 10 }}
          >
            -
          </button>
        )}
           
              </li>
            )})}

        </ul>
  </>
        )}
      </div>


      <div style={{

        position: 'fixed',

        zIndex: 10,

        top: 52,

        left: rulesExpanded ? 270 : 50,

        right: dashboardExpanded ? 'calc(48vw + 10px)' : '50px',

        background: 'transparent',

        padding: '8px 10px',

        borderRadius: 6,
        border: 'none',
        boxShadow: 'none',
        transition: 'left 0.3s ease, right 0.3s ease',
      }}>

       {(() => {
          const canAdd = !currentRuleId || isEditMode
          return (
            <button
              onClick={addNode}
              disabled={!canAdd}
              title={!canAdd ? 'Select a rule and click Edit, or create a new workflow first' : ''}
              style={{
                background: canAdd ? '#00438f' : '#94a3b8',
                color: 'white',
                border: 'none',
                borderRadius: 4,
                padding: '6px 12px',
                cursor: canAdd ? 'pointer' : 'not-allowed',
                opacity: canAdd ? 1 : 0.7,
              }}
            >
              Add Function
            </button>
          )
        })()}

        <button
          onClick={async () => {
            setIsRefreshing(true)
            try {
              await refreshFunctions()
              await loadFunctions().then((funcs) => setFunctions(Array.isArray(funcs) ? funcs : []))
            } catch (e) {
              console.error('Refresh failed', e)
            } finally {
              setIsRefreshing(false)
            }
          }}
          disabled={isRefreshing}
          title="Clear and re-register all functions from the server"
          style={{
            marginLeft: 10,
            background: isRefreshing ? '#94a3b8' : '#1e6b3a',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            padding: '6px 12px',
            cursor: isRefreshing ? 'not-allowed' : 'pointer',
            opacity: isRefreshing ? 0.7 : 1,
          }}
        >
          {isRefreshing ? 'Refreshing...' : 'Refresh Functions'}
        </button>

         {(() => {
          const canSave = (isEditMode && !!currentRuleId) || (!currentRuleId && nodes.length > 0)
          return (
            <button
              onClick={() => {
                if (isEditMode) {
                  handleSaveWorkflow()
                } else {
                  setShowSaveDialog(true)
                }
              }}
              disabled={!canSave}
              title={!canSave ? 'Select a rule and click Edit, or add a node to a new workflow' : ''}
              style={{
                marginLeft: 10,
                background: canSave ? '#0062c4' : '#94a3b8',
                color: 'white',
                border: 'none',
                borderRadius: 4,
                padding: '6px 12px',
                cursor: canSave ? 'pointer' : 'not-allowed',
                opacity: canSave ? 1 : 0.7,
              }}
            >
              Save Workflow
            </button>
          )
        })()}

        <button
            onClick={executeFlow}
            disabled={isEditMode}
            style={{
              marginLeft: 10,
              background: isEditMode ? '#94a3b8' : '#0853b2',
              color: 'white',
              border: 'none',
              borderRadius: 4,
              padding: '6px 12px',
              cursor: isEditMode ? 'not-allowed' : 'pointer'
            }}
          >
            Execute Flow
          </button>
       <button
          onClick={() => {
            if (isEditMode) {
              handleCancelEdit()
            } else {
              handleEditRule()
            }
          }}
          style={{
            marginLeft: 10,
            background: isEditMode ? '#dc2626' : '#00438f',
            color: 'white',
            border: 'none',
            borderRadius: 4,
            padding: '6px 12px',
            cursor: 'pointer',
            fontWeight: 600
          }}
        >
          {isEditMode ? 'Cancel Edit' : 'Edit Flow'}
        </button>

      </div>

      {showDialog && (
        <div style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
          background: 'rgba(0,0,0,0.45)', display: 'flex',
          justifyContent: 'center', alignItems: 'center', zIndex: 1000,
        }}>
          <div style={{
            background: 'white', borderRadius: 8, padding: 20,
            width: 480, maxHeight: '78vh',
            display: 'flex', flexDirection: 'column',
            boxShadow: '0 8px 32px rgba(0,0,0,0.22)',
          }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Select Function</h3>
              <span
                onClick={() => { setShowDialog(false); setSelectedFunction(''); setFuncSearch('') }}
                style={{ cursor: 'pointer', fontSize: 18, color: '#888', lineHeight: 1 }}
              >✕</span>
            </div>

            {/* Search */}
            <input
              autoFocus
              placeholder="Search functions…"
              value={funcSearch}
              onChange={e => setFuncSearch(e.target.value)}
              style={{
                padding: '7px 10px', border: '1px solid #d0d0d0', borderRadius: 5,
                fontSize: 13, marginBottom: 10, outline: 'none',
              }}
            />

            {/* Grouped list */}
            <div style={{
              flex: 1, overflowY: 'auto',
              border: '1px solid #e8e8e8', borderRadius: 5,
            }}>
              {groupedFunctions(funcSearch).length === 0 && (
                <div style={{ padding: '18px 14px', color: '#999', fontSize: 13, textAlign: 'center' }}>
                  No functions found
                </div>
              )}
              {groupedFunctions(funcSearch).map(group => (
                <div key={group.tag}>
                  {/* Group header */}
                  <div style={{
                    background: group.color + '20',
                    borderLeft: `4px solid ${group.color}`,
                    padding: '5px 10px',
                    fontSize: 11, fontWeight: 700, letterSpacing: '0.6px',
                    textTransform: 'uppercase', color: '#444',
                    position: 'sticky', top: 0, zIndex: 1,
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}>
                    <span style={{
                      width: 9, height: 9, borderRadius: '50%',
                      background: group.color, display: 'inline-block', flexShrink: 0,
                    }} />
                    {group.tag}
                    <span style={{ marginLeft: 'auto', fontWeight: 400, color: '#999', fontSize: 10 }}>
                      {group.items.length}
                    </span>
                  </div>
                  {/* Function rows */}
                  {group.items.map(func => {
                    const isSelected = selectedFunction === func.function_name
                    return (
                      <div
                        key={func.function_name}
                        onClick={() => setSelectedFunction(func.function_name)}
                        style={{
                          padding: '8px 14px',
                          cursor: 'pointer',
                          background: isSelected ? group.color + '18' : 'white',
                          borderLeft: `4px solid ${isSelected ? group.color : 'transparent'}`,
                          borderBottom: '1px solid #f2f2f2',
                          fontSize: 13,
                          display: 'flex', alignItems: 'center', gap: 8,
                          transition: 'background 0.1s',
                        }}
                        onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = '#f7f7f7' }}
                        onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = 'white' }}
                      >
                        <span style={{
                          width: 7, height: 7, borderRadius: '50%',
                          background: group.color, flexShrink: 0,
                        }} />
                        {func.function_name}
                      </div>
                    )
                  })}
                </div>
              ))}
            </div>

            {/* Selected label */}
            {selectedFunction && (
              <div style={{ fontSize: 12, color: '#555', marginTop: 8 }}>
                Selected: <strong>{selectedFunction}</strong>
              </div>
            )}

            {/* Footer buttons */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
              <button
                onClick={() => { setShowDialog(false); setSelectedFunction(''); setFuncSearch('') }}
                style={{
                  padding: '7px 16px', borderRadius: 5, border: '1px solid #ccc',
                  background: 'white', cursor: 'pointer', fontSize: 13,
                }}
              >Cancel</button>
              <button
                onClick={handleAddNode}
                disabled={!selectedFunction}
                style={{
                  padding: '7px 16px', borderRadius: 5, border: 'none',
                  background: selectedFunction ? '#1976d2' : '#b0bec5',
                  color: 'white', cursor: selectedFunction ? 'pointer' : 'default',
                  fontSize: 13, fontWeight: 600,
                }}
              >Add</button>
            </div>
          </div>
        </div>
      )}

      {showParamDialog && (
        <div style={modalOverlay}>
          <div style={{
            background: 'white',
            borderRadius: 8,
            boxShadow: '0 8px 32px rgba(0,0,0,0.22)',
            width: 'min(920px, 94vw)',
            maxHeight: '90vh',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}>
            {/* Sticky header */}
            <div style={{
              padding: '14px 20px',
              borderBottom: '1px solid #e8e8e8',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexShrink: 0,
            }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {editingFunctionMeta?.tag && (
                  <div style={{
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                    background: (editingFunctionMeta.color || '#9e9e9e') + '20',
                    borderLeft: `4px solid ${editingFunctionMeta.color || '#9e9e9e'}`,
                    borderRadius: '0 4px 4px 0',
                    padding: '3px 10px 3px 8px',
                    fontSize: 11, fontWeight: 700, letterSpacing: '0.5px',
                    textTransform: 'uppercase', color: '#555',
                    width: 'fit-content',
                  }}>
                    <span style={{
                      width: 8, height: 8, borderRadius: '50%',
                      background: editingFunctionMeta.color || '#9e9e9e',
                      display: 'inline-block', flexShrink: 0,
                    }} />
                    {editingFunctionMeta.tag}
                  </div>
                )}
                <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>
                  {editingFunctionMeta?.function_name || 'Enter Parameters'}
                  <span style={{ fontSize: 12, fontWeight: 400, color: '#888', marginLeft: 10 }}>
                    {targetFunctionInputs.length} field{targetFunctionInputs.length !== 1 ? 's' : ''}
                  </span>
                </h3>
              </div>
              <span
                onClick={() => {
                  setShowParamDialog(false)
                  setPendingConnection(null)
                  setPendingNodeId(null)
                  setConnectionParams({})
                  setEditingFunctionMeta(null)
                }}
                style={{ cursor: 'pointer', fontSize: 18, color: '#888', lineHeight: 1 }}
              >✕</span>
            </div>

            {/* Scrollable 2-column body */}
            <div style={{
              flex: 1,
              overflowY: 'auto',
              padding: '16px 20px',
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '12px 20px',
              alignContent: 'start',
            }}>
              {targetFunctionInputs.map((input) => (
                <div key={input.name} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <label style={{ fontSize: 12, fontWeight: 600, color: '#444' }}>
                    {input.name}
                    <span style={{ fontWeight: 400, color: '#999', marginLeft: 4 }}>({input.type})</span>
                  </label>
                  {input.options && input.options.length > 0 ? (
                    <select
                      value={connectionParams[input.name] || ""}
                      onChange={(e) =>
                        setConnectionParams(prev => ({ ...prev, [input.name]: e.target.value }))
                      }
                      style={{ padding: '6px 8px', border: '1px solid #d0d0d0', borderRadius: 4, fontSize: 13 }}
                    >
                      <option value="">-- select --</option>
                      {input.options.map((opt) => (
                        <option key={opt} value={opt}>{opt}</option>
                      ))}
                    </select>
                  ) : input.type === "date" ? (
                    <input
                      type="date"
                      value={connectionParams[input.name] || ""}
                      onChange={(e) =>
                        setConnectionParams(prev => ({ ...prev, [input.name]: e.target.value }))
                      }
                      style={{ padding: '6px 8px', border: '1px solid #d0d0d0', borderRadius: 4, fontSize: 13 }}
                    />
                  ) : (
                    <input
                      type="text"
                      value={connectionParams[input.name] || ""}
                      onChange={(e) =>
                        setConnectionParams(prev => ({ ...prev, [input.name]: e.target.value }))
                      }
                      style={{ padding: '6px 8px', border: '1px solid #d0d0d0', borderRadius: 4, fontSize: 13 }}
                    />
                  )}
                </div>
              ))}
            </div>

            {/* Sticky footer */}
            <div style={{
              padding: '12px 20px',
              borderTop: '1px solid #e8e8e8',
              display: 'flex',
              justifyContent: 'flex-end',
              gap: 8,
              flexShrink: 0,
            }}>
              <button
                onClick={() => {
                  setShowParamDialog(false)
                  setPendingConnection(null)
                  setPendingNodeId(null)
                  setConnectionParams({})
                  setEditingFunctionMeta(null)
                }}
                style={{
                  padding: '7px 18px', borderRadius: 5,
                  border: '1px solid #ccc', background: 'white',
                  cursor: 'pointer', fontSize: 13,
                }}
              >Cancel</button>
              <button
                onClick={handleConfirmConnection}
                style={{
                  padding: '7px 18px', borderRadius: 5,
                  border: 'none', background: '#1976d2',
                  color: 'white', cursor: 'pointer',
                  fontSize: 13, fontWeight: 600,
                }}
              >Confirm</button>
            </div>
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

style={{ position: 'fixed', left: rulesExpanded ? 250 : 40, top: 42, width: `calc(100vw - ${rulesExpanded ? 250 : 40}px - ${dashboardExpanded ? '42vw' : '40px'})`, height: 'calc(100vh - 42px)' }}>        <Controls />

        <Background />

      </ReactFlow>

      </> /* end workflow fragment */
      )} {/* end workflow */}

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
  borderRadius: 8,
  minWidth: 350,
  boxShadow: '0 8px 32px rgba(0,0,0,0.22)',
}
