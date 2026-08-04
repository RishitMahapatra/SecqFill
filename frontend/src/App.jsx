import { useMemo, useState } from 'react'

const API_BASE = 'http://localhost:8000'

// The /items endpoint doesn't return the questionnaire's original filename
// (it's stored on the questionnaires row but not joined into this response),
// so there's no real data to show here yet — hardcoded placeholder only.
const PLACEHOLDER_FILENAME = 'Security_Audit_2024.xlsx'

const STATUS_LABEL = { green: 'Confident', yellow: 'Needs review', red: 'No match' }
const FILTERS = ['all', 'green', 'yellow', 'red']

export default function App() {
  const [companyId, setCompanyId] = useState('')
  const [questionnaireId, setQuestionnaireId] = useState('')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [loaded, setLoaded] = useState(false)

  const [filter, setFilter] = useState('all')
  // Local-only edits to the extracted answer, keyed by item id. Not
  // persisted anywhere — there is no PATCH endpoint for questionnaire_items
  // yet, so this is UI-state-only until that exists.
  const [edits, setEdits] = useState({})
  // Local-only "approved" toggle, keyed by item id. Same caveat as above:
  // nothing is written back to the backend.
  const [approved, setApproved] = useState({})

  async function loadItems() {
    if (!companyId.trim() || !questionnaireId.trim()) {
      setError('Enter both a company ID and questionnaire ID.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(
        `${API_BASE}/companies/${companyId.trim()}/questionnaires/${questionnaireId.trim()}/items`
      )
      if (!res.ok) {
        throw new Error(`Request failed: ${res.status} ${res.statusText}`)
      }
      const data = await res.json()
      setItems(data)
      setEdits({})
      setApproved({})
      setLoaded(true)
    } catch (err) {
      setError(err.message)
      setItems([])
      setLoaded(false)
    } finally {
      setLoading(false)
    }
  }

  const counts = useMemo(() => {
    const c = { green: 0, yellow: 0, red: 0 }
    for (const item of items) {
      if (c[item.status] !== undefined) c[item.status] += 1
    }
    return c
  }, [items])

  const filteredItems = useMemo(() => {
    if (filter === 'all') return items
    return items.filter((item) => item.status === filter)
  }, [items, filter])

  const approvedCount = Object.values(approved).filter(Boolean).length

  return (
    <div className="page">
      <header className="header">
        <div className="header-top">
          <h1>Security Questionnaire Reviewer</h1>
          <span className="filename" title="Placeholder — not wired to real data, see notes">
            {PLACEHOLDER_FILENAME}
          </span>
        </div>
        <div className="summary-strip">
          <span className="summary-pill dot-green">{counts.green} green</span>
          <span className="summary-pill dot-yellow">{counts.yellow} yellow</span>
          <span className="summary-pill dot-red">{counts.red} red</span>
        </div>
      </header>

      <section className="loader-bar">
        <input
          type="text"
          placeholder="Company ID"
          value={companyId}
          onChange={(e) => setCompanyId(e.target.value)}
        />
        <input
          type="text"
          placeholder="Questionnaire ID"
          value={questionnaireId}
          onChange={(e) => setQuestionnaireId(e.target.value)}
        />
        <button onClick={loadItems} disabled={loading}>
          {loading ? 'Loading…' : 'Load'}
        </button>
        {error && <span className="error-text">{error}</span>}
      </section>

      <nav className="filter-tabs">
        {FILTERS.map((f) => (
          <button
            key={f}
            className={f === filter ? 'tab active' : 'tab'}
            onClick={() => setFilter(f)}
          >
            {f === 'all' ? 'All' : f[0].toUpperCase() + f.slice(1)}
          </button>
        ))}
      </nav>

      <main className="table-wrap">
        {!loaded && !loading && (
          <p className="empty-state">Enter a company and questionnaire ID above, then Load.</p>
        )}
        {loaded && filteredItems.length === 0 && (
          <p className="empty-state">No items match this filter.</p>
        )}
        {filteredItems.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Question Text</th>
                <th>Extracted Answer</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.map((item) => {
                const isApproved = !!approved[item.id]
                const answerValue = edits[item.id] ?? item.final_answer_text ?? ''
                const pct =
                  item.confidence_score != null
                    ? Math.round(item.confidence_score * 100)
                    : null
                return (
                  <tr key={item.id} className={isApproved ? 'row-approved' : ''}>
                    <td className="col-id">{item.row_number}</td>
                    <td className="col-question">{item.question_text}</td>
                    <td className="col-answer">
                      <textarea
                        value={answerValue}
                        onChange={(e) =>
                          setEdits((prev) => ({ ...prev, [item.id]: e.target.value }))
                        }
                        rows={2}
                      />
                    </td>
                    <td className="col-status">
                      <span className={`dot dot-${item.status}`} />
                      {pct != null ? `${pct}%` : '—'}
                      <div className="status-label">{STATUS_LABEL[item.status] ?? item.status}</div>
                    </td>
                    <td className="col-actions">
                      <button
                        className={isApproved ? 'approve-btn approved' : 'approve-btn'}
                        onClick={() =>
                          setApproved((prev) => ({ ...prev, [item.id]: !prev[item.id] }))
                        }
                        title="Toggle approved (local only, not saved)"
                      >
                        {isApproved ? '✓ Approved' : 'Approve'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </main>

      <footer className="footer">
        {loaded
          ? `${items.length} questions · ${approvedCount} approved (not saved)`
          : 'No questionnaire loaded'}
      </footer>
    </div>
  )
}
