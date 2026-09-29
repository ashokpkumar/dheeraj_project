import React, { useState, useEffect, useRef, useCallback } from 'react'

const API_BASE = 'http://127.0.0.1:8000/rule_engine'
const MAX_DISPLAY_WIDTH = 820

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

const panelBox = {
  background: 'white',
  border: '1px solid #d8dded',
  borderRadius: 6,
  padding: 14,
  marginBottom: 14,
}

// Deterministic-ish color per cell key, just so overlapping boxes are easy to tell apart
function colorForCell(cell) {
  let hash = 0
  for (let i = 0; i < cell.length; i++) hash = (hash * 31 + cell.charCodeAt(i)) >>> 0
  const hue = hash % 360
  return `hsl(${hue}, 70%, 45%)`
}

export default function OcrAnnotationPage() {
  // Uploaded document
  const [docId, setDocId] = useState(null)
  const [pageCount, setPageCount] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)
  const [pageImage, setPageImage] = useState(null) // { url, width, height, dpi }
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const fileInputRef = useRef(null)

  // Annotations being edited (not yet necessarily saved)
  const [annotations, setAnnotations] = useState([]) // [{cell, page, x0,y0,x1,y1}]
  const [newCellName, setNewCellName] = useState('')
  const [armedForDraw, setArmedForDraw] = useState(false)
  const [dragStart, setDragStart] = useState(null) // display-space {x,y}
  const [dragCurrent, setDragCurrent] = useState(null)

  // Templates
  const [templates, setTemplates] = useState([])
  const [templateNameToSave, setTemplateNameToSave] = useState('')
  const [templateToLoad, setTemplateToLoad] = useState('')
  const [saving, setSaving] = useState(false)
  const [statusMsg, setStatusMsg] = useState('')

  // Extraction
  const [extracting, setExtracting] = useState(false)
  const [extractionResults, setExtractionResults] = useState(null) // {cell: text}
  const [extractionTemplate, setExtractionTemplate] = useState('')

  const canvasRef = useRef(null)
  const imgElRef = useRef(null)

  const scale = pageImage ? Math.min(1, MAX_DISPLAY_WIDTH / pageImage.width) : 1

  // ── Load template list on mount ──
  const refreshTemplateList = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/ocr/templates/`)
      const data = await res.json()
      setTemplates(Array.isArray(data.templates) ? data.templates : [])
    } catch (e) {
      console.error('Failed to load template list', e)
    }
  }, [])

  useEffect(() => { refreshTemplateList() }, [refreshTemplateList])

  // ── Upload a PDF ──
  const handleFileSelected = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadError('')
    setExtractionResults(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`${API_BASE}/ocr/upload/`, { method: 'POST', body: form })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Upload failed')
      setDocId(data.doc_id)
      setPageCount(data.page_count)
      setCurrentPage(1)
      setAnnotations([])
      setStatusMsg(`Loaded ${file.name} (${data.page_count} page${data.page_count === 1 ? '' : 's'}) — this file stays on your machine, nothing is uploaded anywhere else.`)
    } catch (err) {
      setUploadError(err.message || String(err))
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleDiscardUpload = async () => {
    if (!docId) return
    try {
      await fetch(`${API_BASE}/ocr/uploads/${docId}/`, { method: 'DELETE' })
    } catch (e) {
      console.error('Failed to discard upload', e)
    }
    setDocId(null)
    setPageImage(null)
    setPageCount(0)
    setAnnotations([])
    setExtractionResults(null)
    setStatusMsg('Upload discarded.')
  }

  // ── Fetch the rendered image for the current page whenever doc/page changes ──
  useEffect(() => {
    if (!docId) return
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`${API_BASE}/ocr/page-image/?doc_id=${docId}&page=${currentPage}`)
        const data = await res.json()
        if (!res.ok) throw new Error(data.error || 'Failed to render page')
        if (!cancelled) setPageImage({ url: data.image, width: data.width, height: data.height, dpi: data.dpi })
      } catch (err) {
        if (!cancelled) setUploadError(err.message || String(err))
      }
    })()
    return () => { cancelled = true }
  }, [docId, currentPage])

  // ── Redraw the canvas: page image + annotation boxes + live drag preview ──
  const redraw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas || !pageImage) return
    const ctx = canvas.getContext('2d')
    const dispW = Math.round(pageImage.width * scale)
    const dispH = Math.round(pageImage.height * scale)
    canvas.width = dispW
    canvas.height = dispH

    const draw = () => {
      ctx.clearRect(0, 0, dispW, dispH)
      ctx.drawImage(imgElRef.current, 0, 0, dispW, dispH)

      annotations
        .filter(a => a.page === currentPage)
        .forEach(a => {
          const color = colorForCell(a.cell)
          const x = Math.min(a.x0, a.x1) * scale
          const y = Math.min(a.y0, a.y1) * scale
          const w = Math.abs(a.x1 - a.x0) * scale
          const h = Math.abs(a.y1 - a.y0) * scale
          ctx.strokeStyle = color
          ctx.lineWidth = 2
          ctx.strokeRect(x, y, w, h)
          ctx.fillStyle = color
          ctx.font = '11px sans-serif'
          const labelY = y > 12 ? y - 3 : y + h + 12
          ctx.fillText(a.cell, x + 2, labelY)
        })

      if (dragStart && dragCurrent) {
        const x = Math.min(dragStart.x, dragCurrent.x)
        const y = Math.min(dragStart.y, dragCurrent.y)
        const w = Math.abs(dragCurrent.x - dragStart.x)
        const h = Math.abs(dragCurrent.y - dragStart.y)
        ctx.strokeStyle = '#dc2626'
        ctx.setLineDash([4, 3])
        ctx.lineWidth = 2
        ctx.strokeRect(x, y, w, h)
        ctx.setLineDash([])
      }
    }

    if (imgElRef.current && imgElRef.current.src === pageImage.url && imgElRef.current.complete) {
      draw()
    } else {
      const img = new Image()
      img.onload = () => { imgElRef.current = img; draw() }
      img.src = pageImage.url
    }
  }, [pageImage, scale, annotations, currentPage, dragStart, dragCurrent])

  useEffect(() => { redraw() }, [redraw])

  // ── Mouse handlers for drawing a new box ──
  const canvasPoint = (e) => {
    const rect = canvasRef.current.getBoundingClientRect()
    return { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }

  const handleMouseDown = (e) => {
    if (!armedForDraw) return
    setDragStart(canvasPoint(e))
    setDragCurrent(canvasPoint(e))
  }

  const handleMouseMove = (e) => {
    if (!armedForDraw || !dragStart) return
    setDragCurrent(canvasPoint(e))
  }

  const handleMouseUp = () => {
    if (!armedForDraw || !dragStart || !dragCurrent) return
    const x0 = Math.min(dragStart.x, dragCurrent.x) / scale
    const y0 = Math.min(dragStart.y, dragCurrent.y) / scale
    const x1 = Math.max(dragStart.x, dragCurrent.x) / scale
    const y1 = Math.max(dragStart.y, dragCurrent.y) / scale

    if (x1 - x0 < 3 || y1 - y0 < 3) {
      // Too small to be a real box (a stray click) — ignore, stay armed so the user can retry
      setDragStart(null)
      setDragCurrent(null)
      return
    }

    setAnnotations(prev => [...prev, { cell: newCellName, page: currentPage, x0, y0, x1, y1 }])
    setDragStart(null)
    setDragCurrent(null)
    setArmedForDraw(false)
    setNewCellName('')
    setStatusMsg(`Added annotation "${newCellName}" on page ${currentPage}.`)
  }

  const startNewAnnotation = () => {
    const trimmed = newCellName.trim()
    if (!trimmed) {
      setStatusMsg('Enter a cell key (e.g. "R89") before drawing.')
      return
    }
    setNewCellName(trimmed)
    setArmedForDraw(true)
    setStatusMsg(`Draw a box for "${trimmed}" on the page below.`)
  }

  const cancelDraw = () => {
    setArmedForDraw(false)
    setDragStart(null)
    setDragCurrent(null)
  }

  const removeAnnotation = (index) => {
    setAnnotations(prev => prev.filter((_, i) => i !== index))
  }

  // ── Save / load templates ──
  const handleSaveTemplate = async () => {
    const name = templateNameToSave.trim()
    if (!name) {
      setStatusMsg('Enter a template name to save.')
      return
    }
    if (annotations.length === 0) {
      setStatusMsg('Add at least one annotation before saving.')
      return
    }
    setSaving(true)
    try {
      const res = await fetch(`${API_BASE}/ocr/templates/save/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template_name: name,
          dpi: pageImage?.dpi || 200,
          annotations,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Save failed')
      setStatusMsg(`Saved template "${name}" (${annotations.length} annotation${annotations.length === 1 ? '' : 's'}).`)
      setExtractionTemplate(name)
      await refreshTemplateList()
    } catch (err) {
      setStatusMsg(`Save failed: ${err.message || err}`)
    } finally {
      setSaving(false)
    }
  }

  const handleLoadTemplate = async () => {
    if (!templateToLoad) return
    try {
      const res = await fetch(`${API_BASE}/ocr/templates/${encodeURIComponent(templateToLoad)}/`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Load failed')
      setAnnotations(data.annotations || [])
      setTemplateNameToSave(templateToLoad)
      setExtractionTemplate(templateToLoad)
      setStatusMsg(`Loaded template "${templateToLoad}" (${(data.annotations || []).length} annotation(s), rendered at ${data.dpi} DPI — page image DPI must match for boxes to line up).`)
    } catch (err) {
      setStatusMsg(`Load failed: ${err.message || err}`)
    }
  }

  const handleDeleteTemplate = async (name) => {
    if (!window.confirm(`Delete template "${name}"? This cannot be undone.`)) return
    try {
      await fetch(`${API_BASE}/ocr/templates/${encodeURIComponent(name)}/delete/`, { method: 'DELETE' })
      await refreshTemplateList()
      setStatusMsg(`Deleted template "${name}".`)
    } catch (err) {
      setStatusMsg(`Delete failed: ${err.message || err}`)
    }
  }

  // ── Run extraction against the uploaded doc using a saved template ──
  const handleRunExtraction = async () => {
    if (!docId) {
      setStatusMsg('Upload a PDF first.')
      return
    }
    if (!extractionTemplate) {
      setStatusMsg('Save or load a template first, then run extraction.')
      return
    }
    setExtracting(true)
    setExtractionResults(null)
    try {
      const res = await fetch(`${API_BASE}/ocr/extract/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_id: docId, template_name: extractionTemplate }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Extraction failed')
      setExtractionResults(data.values || {})
      setStatusMsg(`Extraction complete using "${extractionTemplate}".`)
    } catch (err) {
      setStatusMsg(`Extraction failed: ${err.message || err}`)
    } finally {
      setExtracting(false)
    }
  }

  return (
    <div style={{ padding: '16px 20px', maxWidth: 1400, margin: '0 auto' }}>
      <h2 style={{ marginTop: 0 }}>🔍 OCR Annotation</h2>
      <p style={{ color: '#555', fontSize: 13, maxWidth: 780 }}>
        Draw boxes on a PDF page and give each one a cell key (e.g. "R89"). Save the set of boxes as a
        named template — a JSON file kept in the code folder (no document content, just box positions
        and labels) — and reuse it to OCR the same fields out of every PDF that shares this layout.
        The PDF you upload here stays on your local machine only; it is written to a temp folder and
        never committed or sent anywhere else.
      </p>

      {statusMsg && (
        <div style={{ ...panelBox, background: '#eff6ff', borderColor: '#bfdbfe', color: '#1e3a8a', fontSize: 13 }}>
          {statusMsg}
        </div>
      )}

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        {/* ── Left: upload + canvas ── */}
        <div style={{ flex: '1 1 auto', minWidth: 0 }}>
          <div style={panelBox}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <input ref={fileInputRef} type="file" accept="application/pdf" onChange={handleFileSelected} disabled={uploading} />
              {uploading && <span style={{ fontSize: 13, color: '#555' }}>Uploading…</span>}
              {docId && (
                <>
                  <span style={{ fontSize: 12, color: '#16a34a', fontWeight: 600 }}>Document loaded ({pageCount} page{pageCount === 1 ? '' : 's'})</span>
                  <button style={btn('#dc2626')} onClick={handleDiscardUpload}>Discard Upload</button>
                </>
              )}
            </div>
            {uploadError && <div style={{ color: '#dc2626', fontSize: 13, marginTop: 8 }}>{uploadError}</div>}
          </div>

          {docId && pageCount > 1 && (
            <div style={{ ...panelBox, display: 'flex', alignItems: 'center', gap: 10 }}>
              <button style={btn()} disabled={currentPage <= 1} onClick={() => setCurrentPage(p => p - 1)}>← Prev</button>
              <span style={{ fontSize: 13 }}>Page {currentPage} of {pageCount}</span>
              <button style={btn()} disabled={currentPage >= pageCount} onClick={() => setCurrentPage(p => p + 1)}>Next →</button>
            </div>
          )}

          {pageImage && (
            <div style={{ ...panelBox, overflow: 'auto' }}>
              <canvas
                ref={canvasRef}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                style={{ border: '1px solid #ccc', cursor: armedForDraw ? 'crosshair' : 'default', maxWidth: '100%' }}
              />
              <div style={{ fontSize: 11, color: '#888', marginTop: 6 }}>
                Rendered at {pageImage.dpi} DPI, displayed at {Math.round(scale * 100)}% scale.
              </div>
            </div>
          )}

          {!docId && (
            <div style={{ ...panelBox, color: '#888', fontSize: 13, textAlign: 'center', padding: 40 }}>
              Upload a PDF above to get started.
            </div>
          )}
        </div>

        {/* ── Right: annotation controls ── */}
        <div style={{ flex: '0 0 360px' }}>
          <div style={panelBox}>
            <h4 style={{ marginTop: 0 }}>New Annotation</h4>
            {!armedForDraw ? (
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  type="text"
                  placeholder="Cell key, e.g. R89"
                  value={newCellName}
                  onChange={e => setNewCellName(e.target.value)}
                  style={{ flex: 1, padding: '6px 8px', border: '1px solid #d0d0d0', borderRadius: 4, fontSize: 13 }}
                />
                <button style={btn()} disabled={!docId} onClick={startNewAnnotation}>Draw Box</button>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 13 }}>Drawing box for <strong>{newCellName}</strong>…</span>
                <button style={btn('#6b7280')} onClick={cancelDraw}>Cancel</button>
              </div>
            )}
          </div>

          <div style={panelBox}>
            <h4 style={{ marginTop: 0 }}>Annotations ({annotations.length})</h4>
            {annotations.length === 0 && <div style={{ fontSize: 12, color: '#999' }}>None yet.</div>}
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, maxHeight: 220, overflowY: 'auto' }}>
              {annotations.map((a, i) => (
                <li key={i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '4px 6px', borderBottom: '1px solid #f0f0f0', fontSize: 12,
                }}>
                  <span>
                    <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: colorForCell(a.cell), marginRight: 6 }} />
                    <strong>{a.cell}</strong> <span style={{ color: '#888' }}>(page {a.page})</span>
                  </span>
                  <button onClick={() => removeAnnotation(i)} style={{ ...btn('#dc2626', { padding: '2px 8px' }) }}>✕</button>
                </li>
              ))}
            </ul>
          </div>

          <div style={panelBox}>
            <h4 style={{ marginTop: 0 }}>Save Template</h4>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                placeholder="Template name"
                value={templateNameToSave}
                onChange={e => setTemplateNameToSave(e.target.value)}
                style={{ flex: 1, padding: '6px 8px', border: '1px solid #d0d0d0', borderRadius: 4, fontSize: 13 }}
              />
              <button style={btn('#1e6b3a')} disabled={saving} onClick={handleSaveTemplate}>
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>

          <div style={panelBox}>
            <h4 style={{ marginTop: 0 }}>Load Template</h4>
            <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
              <select
                value={templateToLoad}
                onChange={e => setTemplateToLoad(e.target.value)}
                style={{ flex: 1, padding: '6px 8px', border: '1px solid #d0d0d0', borderRadius: 4, fontSize: 13 }}
              >
                <option value="">-- select a template --</option>
                {templates.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
              <button style={btn()} disabled={!templateToLoad} onClick={handleLoadTemplate}>Load</button>
            </div>
            {templates.length > 0 && (
              <ul style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: 12 }}>
                {templates.map(t => (
                  <li key={t} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
                    <span>{t}</span>
                    <button onClick={() => handleDeleteTemplate(t)} style={{ ...btn('#dc2626', { padding: '1px 6px', fontSize: 11 }) }}>Delete</button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div style={panelBox}>
            <h4 style={{ marginTop: 0 }}>Run Extraction</h4>
            <div style={{ fontSize: 12, color: '#555', marginBottom: 8 }}>
              Using template: <strong>{extractionTemplate || '(none selected — save or load one above)'}</strong>
            </div>
            <button
              style={btn('#0853b2', { width: '100%' })}
              disabled={!docId || !extractionTemplate || extracting}
              onClick={handleRunExtraction}
            >
              {extracting ? 'Running OCR… (first run loads the model, can take a while)' : 'Run Extraction'}
            </button>

            {extractionResults && (
              <table style={{ width: '100%', marginTop: 10, fontSize: 12, borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: 'left', borderBottom: '1px solid #ddd', padding: '4px 2px' }}>Cell</th>
                    <th style={{ textAlign: 'left', borderBottom: '1px solid #ddd', padding: '4px 2px' }}>Value</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(extractionResults).map(([cell, value]) => (
                    <tr key={cell}>
                      <td style={{ padding: '3px 2px', borderBottom: '1px solid #f5f5f5', fontWeight: 600 }}>{cell}</td>
                      <td style={{ padding: '3px 2px', borderBottom: '1px solid #f5f5f5' }}>{value || <span style={{ color: '#bbb' }}>(empty)</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
