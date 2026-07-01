import React, { useState, useEffect } from 'react';


export default function ProcessingPage({
  dashboardData = [],
  dashboardMeta = {},   // ✅ SAFE DEFAULT
  dateDetails = [],
  dateMeta = {},        // ✅ SAFE DEFAULT
  claimsSummary = null,
  fetchDashboardData,
  fetchDateDetails,
  handleExportRowCsv,
}) {
  // ---------------- Local Pagination State ----------------
  const [summaryPage, setSummaryPage] = useState(1);
  const [detailPage, setDetailPage] = useState(1);
  const [selectedDate, setSelectedDate] = useState(null);

  const limit = 10;

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
    fetchDateDetails(date, { page: 1, limit: 10 });
  };

  const onDetailPageChange = (page) => {
    setDetailPage(page);
    fetchDateDetails(selectedDate, { page, limit: 10 });
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

              {claimsSummary && (
                <div style={styles.summaryRow}>
                  <div style={{ ...styles.summaryCard, ...styles.summaryProcessed }}>
                    <div style={styles.summaryLabel}>Processed</div>
                    <div style={styles.summaryValue}>{claimsSummary.processed}</div>
                  </div>
                  <div style={{ ...styles.summaryCard, ...styles.summaryUnprocessed }}>
                    <div style={styles.summaryLabel}>Unprocessed</div>
                    <div style={styles.summaryValue}>{claimsSummary.unprocessed}</div>
                  </div>
                  <div style={{ ...styles.summaryCard, ...styles.summaryTotal }}>
                    <div style={styles.summaryLabel}>Total</div>
                    <div style={styles.summaryValue}>{claimsSummary.total}</div>
                  </div>
                </div>
              )}

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
  const getPageNumbers = () => {
    const pages = [];
    const maxVisible = 7 // Show max 7 page buttons
    let start = Math.max(1, page - 3);
    let end = Math.min(totalPages, page + 3);

    // Adjust range if near the ends
    if (end - start < maxVisible - 1) {
      if (start === 1) {
        end = Math.min(totalPages, start + maxVisible - 1);
      } else {
        start = Math.max(1, end - maxVisible + 1);
      }
    }

    // Add "..." if there's a gap from start
    if (start > 1) {
      pages.push(
        <button key={1} onClick={() => onChange(1)} style={styles.pageBtn}>
          1
        </button>
      );
      if (start > 2) {
        pages.push(<span key="dots-start" style={styles.dots}>...</span>);
      }
    }

    // Add page numbers
    for (let i = start; i <= end; i++) {
      pages.push(
        <button
          key={i}
          onClick={() => onChange(i)}
          style={{
            ...styles.pageBtn,
            ...(i === page ? styles.activePageBtn : {}),
          }}
        >
          {i}
        </button>
      );
    }

    // Add "..." if there's a gap to end
    if (end < totalPages) {
      if (end < totalPages - 1) {
        pages.push(<span key="dots-end" style={styles.dots}>...</span>);
      }
      pages.push(
        <button key={totalPages} onClick={() => onChange(totalPages)} style={styles.pageBtn}>
          {totalPages}
        </button>
      );
    }

    return pages;
  };

  return (
    <div style={styles.pagination}>
      <button
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
        style={styles.navBtn}
      >
        ◀ Prev
      </button>

      <div style={styles.pageNumbers}>
        {getPageNumbers()}
      </div>

      <button
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
        style={styles.navBtn}
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
  summaryRow: {
    display: 'flex',
    gap: 12,
    marginBottom: 12,
  },
  summaryCard: {
    flex: 1,
    borderRadius: 6,
    padding: '10px 12px',
    textAlign: 'center',
  },
  summaryProcessed: { background: '#e6f4ea', color: '#16a34a' },
  summaryUnprocessed: { background: '#fdecec', color: '#dc2626' },
  summaryTotal: { background: '#eef2f6', color: '#1f4e92' },
  summaryLabel: { fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 },
  summaryValue: { fontSize: 22, fontWeight: 700, marginTop: 4 },
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
    alignItems: 'center',
    gap: 12,
    marginTop: 12,
    flexWrap: 'wrap',
  },
  pageNumbers: {
    display: 'flex',
    gap: 4,
    alignItems: 'center',
  },
  navBtn: {
    padding: '6px 12px',
    background: '#1f4e92',
    color: 'white',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 14,
  },
  pageBtn: {
    padding: '4px 8px',
    background: '#f1f5fb',
    color: '#1f4e92',
    border: '1px solid #d8dde5',
    borderRadius: 3,
    cursor: 'pointer',
    fontSize: 12,
    minWidth: 28,
  },
  activePageBtn: {
    background: '#1f4e92',
    color: 'white',
    fontWeight: 'bold',
  },
  dots: {
    color: '#6b7280',
    padding: '4px 4px',
  },
};
