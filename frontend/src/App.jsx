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
  // Draft text for the answer textarea, keyed by item id — lets the field
  // be responsive while typing without re-fetching. Saved via PATCH on
  // blur; item.final_answer_text (from the server) is the source of truth
  // once loaded/saved.
  const [drafts, setDrafts] = useState({})
  // Per-item save status ("saving" | "error"), purely for UI feedback.
  const [saveState, setSaveState] = useState({})

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
      setDrafts({})
      setSaveState({})
      setLoaded(true)
    } catch (err) {
      setError(err.message)
      setItems([])
      setLoaded(false)
    } finally {
      setLoading(false)
    }
  }

  // Persists a partial update to one item via PATCH, then replaces that
  // item in local state with the server's returned row — the server
  // response (not an optimistic guess) becomes the new source of truth.
  async function patchItem(itemId, payload) {
    setSaveState((prev) => ({ ...prev, [itemId]: 'saving' }))
    try {
      const res = await fetch(
        `${API_BASE}/companies/${companyId.trim()}/questionnaires/${questionnaireId.trim()}/items/${itemId}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        }
      )
      if (!res.ok) {
        throw new Error(`Save failed: ${res.status} ${res.statusText}`)
      }
      const updated = await res.json()
      setItems((prev) => prev.map((it) => (it.id === itemId ? updated : it)))
      setSaveState((prev) => {
        const next = { ...prev }
        delete next[itemId]
        return next
      })
    } catch {
      // Scoped out: no rollback of the draft/approved UI on failure, just
      // surface that the save didn't go through.
      setSaveState((prev) => ({ ...prev, [itemId]: 'error' }))
    }
  }

  function handleAnswerBlur(item) {
    const draft = drafts[item.id]
    if (draft === undefined || draft === item.final_answer_text) return
    patchItem(item.id, { final_answer_text: draft })
  }

  function toggleApprove(item) {
    patchItem(item.id, { approved: !item.approved })
  }

  const [exporting, setExporting] = useState(false)

  async function exportQuestionnaire() {
    setExporting(true)
    setError(null)
    try {
      const res = await fetch(
        `${API_BASE}/companies/${companyId.trim()}/questionnaires/${questionnaireId.trim()}/export`
      )
      if (!res.ok) {
        throw new Error(`Export failed: ${res.status} ${res.statusText}`)
      }
      const blob = await res.blob()
      // Content-Disposition carries the server's real filename (see
      // main.py's CORS expose_headers) — fall back to a generic name if
      // it's missing for any reason rather than failing the download.
      const disposition = res.headers.get('Content-Disposition') || ''
      const match = disposition.match(/filename="?([^";]+)"?/)
      const filename = match ? match[1] : 'export'

      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.message)
    } finally {
      setExporting(false)
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

  const approvedCount = items.filter((item) => item.approved).length

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
        <button onClick={exportQuestionnaire} disabled={!loaded || exporting}>
          {exporting ? 'Exporting…' : 'Export'}
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
                const isApproved = !!item.approved
                const answerValue = drafts[item.id] ?? item.final_answer_text ?? ''
                const status = saveState[item.id]
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
                          setDrafts((prev) => ({ ...prev, [item.id]: e.target.value }))
                        }
                        onBlur={() => handleAnswerBlur(item)}
                        rows={2}
                      />
                      {status === 'saving' && <div className="save-hint">Saving…</div>}
                      {status === 'error' && <div className="save-hint save-error">Save failed</div>}
                    </td>
                    <td className="col-status">
                      <span className={`dot dot-${item.status}`} />
                      {pct != null ? `${pct}%` : '—'}
                      <div className="status-label">{STATUS_LABEL[item.status] ?? item.status}</div>
                    </td>
                    <td className="col-actions">
                      <button
                        className={isApproved ? 'approve-btn approved' : 'approve-btn'}
                        onClick={() => toggleApprove(item)}
                        title="Toggle approved (saved to server)"
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
          ? `${items.length} questions · ${approvedCount} approved`
          : 'No questionnaire loaded'}
      </footer>
    </div>
  )
}
