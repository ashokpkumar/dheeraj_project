import React from 'react'
import { Handle, Position } from '@xyflow/react'

export default function RuleNode({ id, data }) {

  return (
    <div style={{
      padding: 10,
      border: '1px solid black',
      borderRadius: 5,
      background: '#f9f9f9',
      minWidth: 120,
      textAlign: 'center'
    }}>

      <Handle type="target" position={Position.Top} />

      <div>
        {data.label}
      </div>

      {/* Params block — double-click to edit when in edit mode */}
      {data.params && Object.keys(data.params).length > 0 && (
        <div style={{ position: 'relative' }}>
          <pre
            onDoubleClick={() => data.isEditMode && data.onEditParams && data.onEditParams(id)}
            title={data.isEditMode ? 'Double-click to edit parameters' : undefined}
            style={{
              textAlign: 'left',
              marginTop: 5,
              fontSize: '10px',
              background: '#fff',
              padding: '4px',
              border: `1px solid ${data.isEditMode ? '#f59e0b' : '#ddd'}`,
              borderRadius: '3px',
              cursor: data.isEditMode ? 'pointer' : 'default',
              userSelect: 'none',
            }}
          >
            {JSON.stringify(data.params, null, 2)}
          </pre>
          {/* Edit hint icon shown only in edit mode */}
          {data.isEditMode && (
            <span style={{
              position: 'absolute',
              top: 6,
              right: 4,
              fontSize: '8px',
              color: '#f59e0b',
              fontWeight: 'bold',
              pointerEvents: 'none',
            }}>
              ✎
            </span>
          )}
        </div>
      )}

      {/* Delete button — only visible in edit mode */}
      {data.isEditMode && data.onDelete && (
        <button
          onClick={() => data.onDelete(id)}
          style={{
            marginTop: 5,
            fontSize: '12px',
            background: '#ef4444',
            color: 'white',
            border: 'none',
            borderRadius: 3,
            padding: '2px 8px',
            cursor: 'pointer',
          }}
        >
          −
        </button>
      )}

      <Handle type="source" position={Position.Bottom} />

    </div>
  )
}
