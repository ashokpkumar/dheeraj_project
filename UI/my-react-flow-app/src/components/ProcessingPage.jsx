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
    <div style={styles.page}>

      {/* Header */}
      <div style={styles.header}>
        <h2 style={styles.title}>Processing Dashboard</h2>

        <button style={styles.refreshBtn} onClick={fetchDashboardData}>
          🔄 Refresh
        </button>
      </div>

      {/* Main Layout */}
      <div style={styles.grid}>

        {/* LEFT: Aggregated */}
        <div style={styles.card}>
          <h3 style={styles.cardTitle}>📅 Day-wise Summary</h3>

          <div style={styles.tableWrapper}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Date</th>
                  <th style={{ ...styles.th, textAlign: 'right' }}>Claims</th>
                </tr>
              </thead>

              <tbody>
                {dashboardData.length === 0 && (
                  <tr>
                    <td colSpan={2} style={styles.empty}>No data available</td>
                  </tr>
                )}

                {dashboardData.map((item) => (
                  <tr
                    key={item.period_start}
                    onClick={() => fetchDateDetails(item.period_start)}
                    style={{
                      ...styles.tr,
                      background:
                        selectedDate === item.period_start
                          ? '#e0edff'
                          : 'transparent',
                    }}
                  >
                    <td style={styles.td}>{item.period_start}</td>
                    <td style={{ ...styles.td, textAlign: 'right', fontWeight: 600 }}>
                      {item.claims_count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* RIGHT: Details */}
        <div style={styles.card}>
          <h3 style={styles.cardTitle}>📊 Rule-wise Details</h3>

          {!selectedDate && (
            <div style={styles.placeholder}>
              Select a date from the left to view details
            </div>
          )}

          {selectedDate && (
            <>
              <div style={styles.selectedDate}>
                Showing: <strong>{selectedDate}</strong>
              </div>

              <div style={styles.tableWrapper}>
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={styles.th}>Date</th>
                      <th style={styles.th}>Rule Name</th>
                      <th style={{ ...styles.th, textAlign: 'right' }}>Claims</th>
                      <th style={styles.th}></th>
                    </tr>
                  </thead>

                  <tbody>
                    {dateDetails.length === 0 && (
                      <tr>
                        <td colSpan={4} style={styles.empty}>
                          No data for selected date
                        </td>
                      </tr>
                    )}

                    {dateDetails.map((item) => (
                      <tr key={item.id} style={styles.tr}>
                        <td style={styles.td}>
                          {new Date(item.processed_at).toISOString().split('T')[0]}
                        </td>

                        <td style={styles.td}>
                          {item.rule_engine?.rule_name || '-'}
                        </td>

                        <td style={{ ...styles.td, textAlign: 'right', fontWeight: 600 }}>
                          {item.claims_count}
                        </td>

                        <td style={styles.td}>
                          <button
                            style={styles.csvBtn}
                            onClick={() => handleExportRowCsv(item)}
                          >
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
  )
}

const styles = {
  page: {
    paddingTop: 60,
    paddingLeft: 20,
    paddingRight: 20,
    background: '#eef3f8',
    height: '100vh',
    boxSizing: 'border-box',
  },

  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  },

  title: {
    color: '#0f3d84',
    margin: 0,
  },

  refreshBtn: {
    background: 'linear-gradient(135deg, #00438f, #0062c4)',
    color: 'white',
    border: 'none',
    borderRadius: 6,
    padding: '8px 14px',
    cursor: 'pointer',
    fontWeight: 600,
    boxShadow: '0 2px 6px rgba(0,0,0,0.15)',
    transition: '0.2s',
  },

  grid: {
    display: 'flex',
    gap: 20,
    height: 'calc(100% - 80px)',
  },

  card: {
    flex: 1,
    background: 'white',
    borderRadius: 10,
    padding: 16,
    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
    display: 'flex',
    flexDirection: 'column',
  },

  cardTitle: {
    marginBottom: 12,
    color: '#073c71',
  },

  tableWrapper: {
    overflowY: 'auto',
    borderRadius: 6,
  },

  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: '0.9rem',
  },

  th: {
    position: 'sticky',
    top: 0,
    background: '#f1f5fb',
    textAlign: 'left',
    padding: '8px',
    borderBottom: '1px solid #d8dde5',
    color: '#0f3d84',
    fontWeight: 600,
  },

  td: {
    padding: '8px',
    borderBottom: '1px solid #eef2f6',
  },

  tr: {
    cursor: 'pointer',
    transition: 'background 0.15s',
  },

  empty: {
    padding: 10,
    textAlign: 'center',
    color: '#6b7280',
  },

  placeholder: {
    color: '#6b7280',
    padding: 10,
  },

  selectedDate: {
    marginBottom: 10,
    color: '#1f4e92',
  },

  csvBtn: {
    background: '#16a34a',
    color: 'white',
    border: 'none',
    borderRadius: 4,
    padding: '4px 8px',
    fontSize: '0.75rem',
    cursor: 'pointer',
    fontWeight: 600,
    transition: '0.2s',
  },
}