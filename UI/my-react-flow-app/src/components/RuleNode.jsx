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

      <Handle type="source" position={Position.Bottom} />

    </div>
  )
}
