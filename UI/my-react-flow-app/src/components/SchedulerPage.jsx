import React, { useState, useEffect } from 'react'

const API_BASE = 'http://127.0.0.1:8000/rule_engine'

const UNIT_OPTIONS = ['seconds', 'minutes', 'hours']

const badge = (isActive) => ({
  display: 'inline-block',
  padding: '2px 10px',
  borderRadius: 12,
  fontSize: '0.75rem',
  fontWeight: 600,
  background: isActive ? '#dcfce7' : '#fee2e2',
  color: isActive ? '#16a34a' : '#dc2626',
})

const btn = (color = '#00438f', extra = {}) => ({
  background: color,
  color: 'white',
  border: 'none',
  borderRadius: 4,
  padding: '6px 14px',
  cursor: 'pointer',
  fontSize: '0.85rem',
  fontWeight: 500,
  ...extra,
})

export default function SchedulerPage() {
  const [jobs, setJobs]               = useState([])
  const [loading, setLoading]         = useState(true)
  const [showForm, setShowForm]       = useState(false)
  const [submitting, setSubmitting]   = useState(false)
  const [error, setError]             = useState('')
  const [successMsg, setSuccessMsg]   = useState('')

  // Form state
  const [formRuleName, setFormRuleName] = useState('')
  const [formInterval, setFormInterval] = useState('')
  const [formUnit, setFormUnit]         = useState('seconds')
  const [formActive, setFormActive]     = useState(true)
  const [useCombinations, setUseCombinations] = useState(false)
  const [comboIntervals, setComboIntervals] = useState('')
  const [comboUnits, setComboUnits] = useState([])
  const [rulesList, setRulesList] = useState([])

  const [scheduleType, setScheduleType] = useState('interval')
  const [scheduleTime, setScheduleTime] = useState('')
  const [scheduleDays, setScheduleDays] = useState([])
  const [scheduleDate, setScheduleDate] = useState('')
  const [jobName, setJobName] = useState('')
  const allPaused = jobs.length > 0 && jobs.every(j => !j.is_active)
const [formKey, setFormKey] = useState(0)
const fetchRules = async () => {
  try {
    const res = await fetch(`${API_BASE}/rules/`)
    const data = await res.json()

    setRulesList(Array.isArray(data) ? data : (data.results || []))
  } catch {
    setError('Failed to load rules list')
  }
}
  const fetchJobs = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/scheduler/jobs/`)
      const data = await res.json()
      // API returns { count, results } or plain array
      setJobs(Array.isArray(data) ? data : (data.results || []))
    } catch (e) {
      setError('Failed to load scheduled jobs')
    } finally {
      setLoading(false)
    }
  }

useEffect(() => {
  fetchJobs()
  fetchRules() // ✅ NEW
}, [])

  const flash = (msg) => {
    setSuccessMsg(msg)
    setTimeout(() => setSuccessMsg(''), 3000)
  }

  const formatSchedule = (job) => {
  const config = job.schedule_config

  if (!config) return ''

  switch (config.type) {
    case 'interval':
      return `Every ${job.interval} ${job.unit}`

    case 'daily':
      return `Daily at ${config.time}`

    case 'weekly':
      return `Every week on ${config.days?.join(', ')} at ${config.time}`

    case 'once':
      if (!config.datetime) return ''
      return `Run once at ${toLocalDisplay(config.datetime)}`

    default:
      return ''
  }
}

const resetForm = () => {
  setFormRuleName('')
  setFormInterval('')
  setFormUnit('seconds')
  setFormActive(true)
  setError('')
  setUseCombinations(false)
  setComboIntervals('')
  setComboUnits([])
  setScheduleType('interval')
  setScheduleTime('')
  setScheduleDays([])
  setScheduleDate('')
  setJobName('')

  setFormKey(prev => prev + 1) // 🔥 force re-render
}
const toLocalDisplay = (utcString) => {
  if (!utcString) return ''

  const date = new Date(utcString)

  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}
  const handleAddJob = async () => {
    setError('')
    if (!formRuleName.trim()) return setError('Rule name is required')
    const toUTCISOString = (localDateTime) => {
              if (!localDateTime) return null
              const date = new Date(localDateTime)
              return date.toISOString() // converts to UTC
            }
    const payload = {
      rule_id: formRuleName.trim(),
      is_active: formActive,
      job_name: jobName.trim() || `Job for ${formRuleName.trim()}`,
      schedule_config: {
        type: scheduleType,
        ...(scheduleType === 'daily' && { time: scheduleTime }),
        ...(scheduleType === 'weekly' && { time: scheduleTime, days: scheduleDays }),
        ...(scheduleType === 'once'   && { datetime: toUTCISOString(scheduleDate) }),
      },
    }

    if (scheduleType === 'interval') {
      if (!formInterval || isNaN(formInterval) || Number(formInterval) <= 0)
        return setError('Interval must be a positive number')
      payload.interval = Number(formInterval)
      payload.unit = formUnit

      if (useCombinations) {
        const intervals = comboIntervals
          .split(',')
          .map(x => parseInt(x.trim()))
          .filter(x => !isNaN(x) && x > 0)

        if (intervals.length === 0) return setError('Provide valid combination intervals')
        if (comboUnits.length === 0) return setError('Select at least one unit')

        payload.combinations = { intervals, units: comboUnits }
      }
    }
    setSubmitting(true)
    try {
      const res = await fetch(`${API_BASE}/scheduler/jobs/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Failed to save job')
      const savedJob = data
      flash(data.message || 'Job saved')
      console.log(savedJob)
      setShowForm(false)
      resetForm()
      fetchJobs()

    } catch (e) {
      setError(e.message)
    } finally {
      setSubmitting(false)
      setFormRuleName('')
      setFormInterval('')
      setFormUnit('seconds')
      setFormActive(true)
      setError('')
      setUseCombinations(false)
      setComboIntervals('')
      setComboUnits([])
    }
  }

  const handleToggle = async (job) => {
    try {
      await fetch(`${API_BASE}/scheduler/jobs/${job.id}/toggle/`, { method: 'PATCH' })
      flash(`Job "${job.rule_name}" ${job.is_active ? 'paused' : 'resumed'}`)
      fetchJobs()
    } catch {
      setError('Toggle failed')
    }
  }

  const handleDelete = async (job) => {
    if (!window.confirm(`Are you sure you want to delete the scheduled job "${job.rule_name}"? This cannot be undone.`)) return
    try {
      await fetch(`${API_BASE}/scheduler/jobs/${job.id}/`, { method: 'DELETE' })
      flash(`Job "${job.rule_name}" deleted`)
      fetchJobs()
    } catch {
      setError('Delete failed')
    }
  }

const handleRunNow = async (job) => {
  console.log(job)
  try {
    flash(`Running "${job.rule_name}" now…`)

    const response = await fetch(`${API_BASE}/rules/${job.rule_id}/execute/`, {
      method: 'POST',
    })

    if (!response.ok) {
      // Handle 4xx / 5xx responses
      const errorText = await response.text() // or response.json() if API returns JSON
      throw new Error(errorText || 'Server error')
      
    }

    flash(`Job "${job.rule_name}" executed successfully`)
  } catch (err) {

    flash(`⚠️ ${err.message}`)
  }
}

  const handleExecuteAll = async () => {
    if (!window.confirm(`Execute all ${jobs.filter(j => j.is_active).length} active jobs now?`)) return
    const active = jobs.filter(j => j.is_active)
    try {
      flash(`Running ${active.length} active jobs…`)
      await Promise.all(
        active.map(job => fetch(`${API_BASE}/rules/${job.rule_name}/execute/`, { method: 'POST' }))
      )
      flash(`All ${active.length} active jobs executed successfully`)
    } catch {
      setError('One or more jobs failed to execute')
    }
  }

 const handleToggleAll = async () => {
  const targetJobs = allPaused
    ? jobs.filter(j => !j.is_active)   // resume all
    : jobs.filter(j => j.is_active)    // pause all

  if (targetJobs.length === 0) {
    return flash(allPaused ? 'No paused jobs to resume' : 'No active jobs to pause')
  }

  if (!window.confirm(`${allPaused ? 'Resume' : 'Pause'} all ${targetJobs.length} jobs?`)) return

  try {
    await Promise.all(
      targetJobs.map(job =>
        fetch(`${API_BASE}/scheduler/jobs/${job.id}/toggle/`, { method: 'PATCH' })
      )
    )

    flash(`${targetJobs.length} jobs ${allPaused ? 'resumed' : 'paused'}`)
    fetchJobs()
  } catch {
    setError(`Failed to ${allPaused ? 'resume' : 'pause'} all jobs`)
  }
}

  return (
   <div style={{
  width: '100%',
  minHeight: '100vh',
  padding: '32px',
  boxSizing: 'border-box',
  fontFamily: "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif",
}}>

      {/* ── Header ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h2 style={{ margin: 0, color: '#002f6c', fontSize: '1.4rem' }}>Scheduled Jobs</h2>
          <p style={{ margin: '4px 0 0', color: '#5d6779', fontSize: '0.85rem' }}>
            Manage and monitor automated rule executions
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <button onClick={fetchJobs} style={btn('#475569')}>↻ Refresh</button>
         <button
          onClick={handleToggleAll}
          style={btn(allPaused ? '#16a34a' : '#f59e0b')}
          title={allPaused ? 'Resume all paused jobs' : 'Pause all active jobs'}
        >
          {allPaused ? '▶ Resume All' : '⏸ Pause All'}
        </button>
          <button
            onClick={handleExecuteAll}
            style={btn('#0853b2')}
            title="Execute all active jobs immediately"
          >
            ▶ Execute All
          </button>
          <button
            onClick={() => { setShowForm(true); setError('') }}
            style={btn('#00438f')}
          >
            + New Job
          </button>
        </div>
      </div>

      {/* ── Flash messages ── */}
      {successMsg && (
        <div style={{ background: '#dcfce7', color: '#15803d', border: '1px solid #86efac', borderRadius: 6, padding: '10px 16px', marginBottom: 16, fontSize: '0.9rem' }}>
          ✓ {successMsg}
        </div>
      )}
      {error && !showForm && (
        <div key={formKey} style={{ background: '#fee2e2', color: '#dc2626', border: '1px solid #fca5a5', borderRadius: 6, padding: '10px 16px', marginBottom: 16, fontSize: '0.9rem' }}>
          ✕ {error}
        </div>
      )}

      {/* ── Add Job Form ── */}
      {showForm && (
        <div style={{
          background: '#f0f6ff',
          border: '1px solid #bfd4f5',
          borderRadius: 8,
          padding: 20,
          marginBottom: 24,
        }}>
          <h3 style={{ margin: '0 0 16px', color: '#002f6c', fontSize: '1rem' }}>Add / Update Scheduled Job</h3>

          {error && (
            <div style={{ background: '#fee2e2', color: '#dc2626', borderRadius: 4, padding: '8px 12px', marginBottom: 12, fontSize: '0.85rem' }}>
              {error}
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <div>
              <label style={labelStyle}>Job Name</label>
              <input type="text" value={jobName} onChange={e => setJobName(e.target.value)} />
              
              
            </div>

            <div>
              <label style={labelStyle}>Rule Name</label>
              
              
              <select
                value={formRuleName}
                onChange={(e) => setFormRuleName(e.target.value)}
                style={inputStyle}
              >
                <option value="">Select a rule</option>

                {rulesList.map((rule) => (
                  <option key={rule.rule_name} value={rule.id}>
                   {rule.rule_name}
                  </option>
                ))}
              </select>
            </div>
            <div>
 <select value={scheduleType} onChange={e => setScheduleType(e.target.value)} style={inputStyle}>
          <option value="interval">Interval</option>
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="once">Run Once</option>
        </select>

            </div>
           {scheduleType === 'daily' && (
              <input
                type="time"
                value={scheduleTime}
                onChange={e => setScheduleTime(e.target.value)}
                style={inputStyle}
              />
            )}

            {scheduleType === 'weekly' && (
  <>
   <input
  type="time"
  value={scheduleTime}
  onChange={e => setScheduleTime(e.target.value)}
  style={inputStyle}
/>

    

    <div>
      {['monday','tuesday','wednesday','thursday','friday','saturday','sunday'].map(day => (
        <label key={day}>
          <input
            type="checkbox"
            checked={scheduleDays.includes(day)}
            onChange={(e) => {
              if (e.target.checked) {
                setScheduleDays([...scheduleDays, day])
              } else {
                setScheduleDays(scheduleDays.filter(d => d !== day))
              }
            }}
          />
          {day}
        </label>
      ))}
    </div>
  </>
)}

{scheduleType === 'once' && (
  <>
    <input type="datetime-local" value={scheduleDate} onChange={e => setScheduleDate(e.target.value)} />
   
  </>
)}

            {scheduleType === 'interval' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div>
                <label style={labelStyle}>Interval</label>
                <input
                  type="number"
                  min="1"
                  value={formInterval}
                  onChange={(e) => setFormInterval(e.target.value)}
                  placeholder="e.g. 60"
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={labelStyle}>Unit</label>
                <select value={formUnit} onChange={(e) => setFormUnit(e.target.value)} style={inputStyle}>
                  {UNIT_OPTIONS.map((u) => (
                    <option key={u} value={u}>{u}</option>
                  ))}
                </select>
              </div>
              <div style={{ marginTop: 10 }}>
              <label style={labelStyle}>
                <input
                  type="checkbox"
                  checked={useCombinations}
                  onChange={(e) => setUseCombinations(e.target.checked)}
                  style={{ marginRight: 6 }}
                />
                Use advanced combinations
              </label>
            </div>

            {useCombinations && (
              <div style={{ marginTop: 10 }}>
                
                {/* Intervals */}
                <div>
                  <label style={labelStyle}>Intervals (comma separated)</label>
                  <input
                    type="text"
                    value={comboIntervals}
                    onChange={(e) => setComboIntervals(e.target.value)}
                    placeholder="e.g. 5,10,30"
                    style={inputStyle}
                  />
                </div>

                {/* Units */}
                <div style={{ marginTop: 10 }}>
                  <label style={labelStyle}>Units</label>
                  <div style={{ display: 'flex', gap: 10 }}>
                    {UNIT_OPTIONS.map(u => (
                      <label key={u}>
                        <input
                          type="checkbox"
                          checked={comboUnits.includes(u)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setComboUnits([...comboUnits, u])
                            } else {
                              setComboUnits(comboUnits.filter(x => x !== u))
                            }
                          }}
                        />
                        {u}
                      </label>
                    ))}
                  </div>
                </div>

              </div>
            )}
            </div>
            )}

            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
              <input
                type="checkbox"
                id="activeCheck"
                checked={formActive}
                onChange={(e) => setFormActive(e.target.checked)}
                style={{ width: 16, height: 16, cursor: 'pointer' }}
              />
              <label htmlFor="activeCheck" style={{ color: '#334155', fontSize: '0.875rem', cursor: 'pointer' }}>
                Active immediately
              </label>
            </div>
          </div>

          <div style={{ marginTop: 18, display: 'flex', gap: 10 }}>
            <button onClick={handleAddJob} disabled={submitting} style={btn('#00438f', { opacity: submitting ? 0.7 : 1 })}>
              {submitting ? 'Saving…' : 'Save Job'}
            </button>
            <button onClick={() => { setShowForm(false); resetForm() }} style={btn('#64748b')}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* ── Jobs Table ── */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 48, color: '#5d6779' }}>Loading jobs…</div>
      ) : jobs.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: 48, color: '#5d6779',
          border: '1px dashed #d8dde5', borderRadius: 8, background: '#f8fbff',
        }}>
          No scheduled jobs yet. Click <strong>+ New Job</strong> to add one.
        </div>
      ) : (
        <div style={{ border: '1px solid #d8dde5', borderRadius: 8, overflow: 'hidden', background: 'white' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
            <thead>
              <tr style={{ background: '#f0f6ff', borderBottom: '1px solid #d8dde5' }}>
                {['Job Name', 'Rule Name', 'Schedule', 'Status', 'Last Updated', 'Actions'].map((h) => (
                  <th key={h} style={{ textAlign: 'left', padding: '10px 16px', color: '#0f3d84', fontWeight: 600, fontSize: '0.82rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {jobs.map((job, i) => (
                <tr
                  key={job.id}
                  style={{ borderBottom: i < jobs.length - 1 ? '1px solid #eef2f6' : 'none', background: i % 2 === 0 ? 'white' : '#fafbff' }}
                >
                  <td style={{ padding: '12px 16px', color: '#5d6779', fontSize: '0.82rem' }}>
                    {job.job_name}
                  </td>
                  <td style={{ padding: '12px 16px', fontWeight: 500, color: '#1a273d' }}>
                    {job.rule_name}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{
                      background: '#e0f2fe', color: '#0369a1',
                      padding: '3px 10px', borderRadius: 12,
                      fontSize: '0.82rem', fontWeight: 500,
                    }}>
                      ⏱ {formatSchedule(job)}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={badge(job.is_active)}>
                      {job.is_active ? 'Active' : 'Paused'}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px', color: '#5d6779', fontSize: '0.82rem' }}>
                    {toLocalDisplay(job.updated_at)}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <button
                        onClick={() => handleRunNow(job)}
                        style={btn('#16a34a', { padding: '4px 10px', fontSize: '0.78rem' })}
                        title="Run this job immediately"
                      >
                        ▶ Run Now
                      </button>
                      <button
                        onClick={() => handleToggle(job)}
                        style={btn(job.is_active ? '#f59e0b' : '#0853b2', { padding: '4px 10px', fontSize: '0.78rem' })}
                        title={job.is_active ? 'Pause this job' : 'Resume this job'}
                      >
                        {job.is_active ? '⏸ Pause' : '▶ Resume'}
                      </button>
                      <button
                        onClick={() => handleDelete(job)}
                        style={btn('#ef4444', { padding: '4px 10px', fontSize: '0.78rem' })}
                        title="Delete this job"
                      >
                        🗑 Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Footer count */}
          <div style={{ padding: '8px 16px', borderTop: '1px solid #eef2f6', background: '#f8fbff', fontSize: '0.8rem', color: '#5d6779' }}>
            {jobs.length} job{jobs.length !== 1 ? 's' : ''} total
          </div>
        </div>
      )}
    </div>
  )
}

const labelStyle = {
  display: 'block',
  marginBottom: 5,
  fontSize: '0.82rem',
  fontWeight: 600,
  color: '#334155',
}

const inputStyle = {
  width: '100%',
  padding: '7px 10px',
  border: '1px solid #cbd5e1',
  borderRadius: 4,
  fontSize: '0.875rem',
  boxSizing: 'border-box',
  background: 'white',
}
