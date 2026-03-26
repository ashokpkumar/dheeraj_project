import React from 'react'

export default function ProcessingPage({
  dashboardData,
  dateDetails,
  selectedDate,
  fetchDashboardData,
  fetchDateDetails,
  handleExportRowCsv,
}) {
  return (
    <div style={{
      paddingTop: 42,
      height: '100vh',
      overflowY: 'auto',
      background: '#eef3f8',
      display: 'flex',
      justifyContent: 'center'
    }}>
      <div style={{ width: '90%', maxWidth: 1200, marginTop: 20 }}>

        {/* Header */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16
        }}>
          <h2 style={{ color: '#002f6c' }}>Processing Dashboard</h2>

          <button
            onClick={fetchDashboardData}
            style={{
              background: '#00438f',
              color: 'white',
              border: 'none',
              borderRadius: 4,
              padding: '6px 12px',
              cursor: 'pointer'
            }}
          >
            Refresh
          </button>
        </div>

   <div style={{
  display: 'flex',
  gap: 16,
  alignItems: 'stretch'
}}>

  {/* LEFT → Aggregated */}
  <div style={{
    flex: 1,
    background: 'white',
    padding: 16,
    borderRadius: 8,
    minWidth: 0
  }}>
    <h4>Daywise Details</h4>

    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr>
          <th>Date</th>
          <th>Claims</th>
        </tr>
      </thead>
      <tbody>
        {dashboardData.length === 0 && (
          <tr><td colSpan={2}>No data</td></tr>
        )}

        {dashboardData.map((item) => (
          <tr
            key={item.period_start}
            onClick={() => fetchDateDetails(item.period_start)}
            style={{
              cursor: 'pointer',
              background: selectedDate === item.period_start ? '#e4f0ff' : 'transparent'
            }}
          >
            <td>{item.period_start}</td>
            <td>{item.claims_count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>

  {/* RIGHT → Details */}
  <div style={{
    flex: 2,
    background: 'white',
    padding: 16,
    borderRadius: 8,
    minWidth: 0
  }}>
    <h4>Rule Wise details for {selectedDate}</h4>

    {!selectedDate && <div>Select a date to view details</div>}

    {selectedDate && (
      <>
        <div style={{ marginBottom: 8 }}>Showing: {selectedDate}</div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th>Date</th>
                <th>Rule Name</th>
                <th>Claims</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {dateDetails.length === 0 && (
                <tr><td colSpan={4}>No data</td></tr>
              )}

              {dateDetails.map((item) => (
                <tr key={item.id}>
                  <td>{new Date(item.processed_at).toISOString().split('T')[0]}</td>
                  <td>{item.rule_engine?.rule_name || '-'}</td>
                  <td>{item.claims_count}</td>
                  <td>
                    <button onClick={() => handleExportRowCsv(item)}>
                      ⬇ CSV
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>
    )}
  </div>

</div>
      </div>
    </div>
  )
}