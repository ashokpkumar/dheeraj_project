import React, { useState, useEffect } from 'react';


export default function ProcessingPage({
  dashboardData = [],
  dashboardMeta = {},   // ✅ SAFE DEFAULT
  dateDetails = [],
  dateMeta = {},        // ✅ SAFE DEFAULT
  fetchDashboardData,
  fetchDateDetails,
  handleExportRowCsv,
}) {
  // ---------------- Local Pagination State ----------------
  const [summaryPage, setSummaryPage] = useState(1);
  const [detailPage, setDetailPage] = useState(1);
  const [selectedDate, setSelectedDate] = useState(null);

  const limit = 25;

  // ---------------- Derived Meta (SAFE) ----------------
  const summaryCurrent = dashboardMeta.current_page || summaryPage;
  const summaryTotal = dashboardMeta.total_pages || 1;

  const detailCurrent = dateMeta.current_page || detailPage;
  const detailTotal = dateMeta.total_pages || 1;

  // ---------------- Effects ----------------
  useEffect(() => {
    fetchDashboardData({
      aggregate: true,
      group_by: 'day',
      page: summaryPage,
      limit,
    });
  }, [summaryPage]);

  // ---------------- Handlers ----------------
  const onSummaryPageChange = (page) => {
    setSummaryPage(page);
  };

  const onDateClick = (date) => {
    setSelectedDate(date);
    setDetailPage(1);
    fetchDateDetails(date, { page: 1, limit });
  };

  const onDetailPageChange = (page) => {
    setDetailPage(page);
    fetchDateDetails(selectedDate, { page, limit });
  };

  return (
    <div style={styles.page}>
      <div style={styles.grid}>
        {/* ================= LEFT: DAY-WISE SUMMARY ================= */}
        <div style={styles.card}>
          <h3 style={styles.cardTitle}>📅 Day-wise Summary</h3>

          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Date</th>
                <th style={styles.th}>Claims</th>
              </tr>
            </thead>
            <tbody>
              {dashboardData.length === 0 && (
                <tr>
                  <td colSpan={2} style={styles.empty}>No data</td>
                </tr>
              )}

              {dashboardData.map((row) => (
                <tr
                  key={row.period_start}
                  style={styles.tr}
                  onClick={() => onDateClick(row.period_start)}
                >
                  <td style={styles.td}>{row.period_start}</td>
                  <td style={styles.td}>{row.claims_count}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <Pagination
            page={summaryCurrent}
            totalPages={summaryTotal}
            onChange={onSummaryPageChange}
          />
        </div>

        {/* ================= RIGHT: RULE-WISE DETAILS ================= */}
        <div style={styles.card}>
          <h3 style={styles.cardTitle}>📊 Rule-wise Details</h3>

          {!selectedDate && (
            <div style={styles.placeholder}>
              Select a date from the left
            </div>
          )}

          {selectedDate && (
            <>
              <div style={styles.selectedDate}>
                Showing: <b>{selectedDate}</b>
              </div>

              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Date - Time</th>
                    <th style={styles.th}>Rule</th>
                    <th style={styles.th}>Claims</th>
                    <th style={styles.th}></th>
                  </tr>
                </thead>
                <tbody>
                  {dateDetails.length === 0 && (
                    <tr>
                      <td colSpan={4} style={styles.empty}>
                        No data
                      </td>
                    </tr>
                  )}

                  {dateDetails.map((item) => (
                    <tr key={item.id}>
                      <td style={styles.td}>
                        {new Date(item.processed_at)
                          .toISOString()
                          .replace('T', ' ')
                          .slice(0, 16)}
                      </td>
                      <td style={styles.td}>
                        {item.rule_engine?.rule_name || '-'}
                      </td>
                      <td style={styles.td}>{item.claims_count}</td>
                      <td style={styles.td}>
                        <button
                          style={styles.csvBtn}
                          onClick={() => handleExportRowCsv(item)}
                        >
                          CSV
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <Pagination
                page={detailCurrent}
                totalPages={detailTotal}
                onChange={onDetailPageChange}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------- Pagination Component ----------------
function Pagination({ page, totalPages, onChange }) {
  return (
    <div style={styles.pagination}>
      <button
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >
        ◀ Prev
      </button>

      <span>
        Page {page} of {totalPages}
      </span>

      <button
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
      >
        Next ▶
      </button>
    </div>
  );
}

// ---------------- Styles ----------------
const styles = {
  page: { padding: 20, background: '#eef3f8', minHeight: '100vh' },
  grid: { display: 'flex', gap: 20 },
  card: {
    flex: 1,
    background: 'white',
    padding: 16,
    borderRadius: 8,
    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
  },
  cardTitle: { color: '#073c71' },
  table: { width: '100%', borderCollapse: 'collapse' },
  th: {
    background: '#f1f5fb',
    padding: 8,
    textAlign: 'left',
    borderBottom: '1px solid #d8dde5',
  },
  td: { padding: 8, borderBottom: '1px solid #eef2f6' },
  tr: { cursor: 'pointer' },
  empty: { textAlign: 'center', padding: 10, color: '#6b7280' },
  placeholder: { color: '#6b7280', padding: 10 },
  selectedDate: { marginBottom: 8, color: '#1f4e92' },
  csvBtn: {
    background: '#16a34a',
    color: 'white',
    border: 'none',
    padding: '4px 8px',
    cursor: 'pointer',
  },
  pagination: {
    display: 'flex',
    justifyContent: 'center',
    gap: 12,
    marginTop: 12,
  },
};
