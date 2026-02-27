import React from 'react'
import { Handle, Position } from '@xyflow/react'

export default function RuleNode({ data }) {

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

      {/* show parameters if any */}
      {data.params && Object.keys(data.params).length > 0 && (
        <pre
          style={{
            textAlign: 'left',
            marginTop: 5,
            fontSize: '10px',
            background: '#fff',
            padding: '2px',
            border: '1px solid #ddd',
            borderRadius: '3px',
          }}
        >
          {JSON.stringify(data.params, null, 2)}
        </pre>
      )}

      <button onClick={data.onDelete} style={{ marginTop: 5, fontSize: '12px' }}>-</button>

      <Handle type="source" position={Position.Bottom} />

    </div>
  )
}
