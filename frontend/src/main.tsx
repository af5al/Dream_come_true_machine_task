import React, { useEffect, useState, useCallback } from 'react';
import { createRoot } from 'react-dom/client';

type Tx = {
  id: number;
  user_id: number;
  amount: string;
  kind: string;
  status: string;
  reference: string | null;
  failure_reason: string | null;
  created_at?: string;
};

type PaginationResponse = {
  items: Tx[];
  next_cursor: number | null;
  has_more: boolean;
};

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

function App() {
  const [userId, setUserId] = useState<string>('1');
  const [items, setItems] = useState<Tx[]>([]);
  const [nextCursor, setNextCursor] = useState<number | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Tx | null>(null);

  const fetchTransactions = useCallback(async (uid: string) => {
    setLoading(true);
    setError(null);
    setSelected(null);
    try {
      const res = await fetch(`${API}/transactions?limit=10`, {
        headers: { 'X-User-Id': uid }
      });
      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}`);
      }
      const data: PaginationResponse = await res.json();
      setItems(data.items || []);
      setNextCursor(data.next_cursor);
      setHasMore(data.has_more);
    } catch (err: any) {
      setError(err.message || 'Failed to load transactions');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const res = await fetch(`${API}/transactions?limit=10&cursor=${nextCursor}`, {
        headers: { 'X-User-Id': userId }
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: PaginationResponse = await res.json();
      setItems(prev => [...prev, ...(data.items || [])]);
      setNextCursor(data.next_cursor);
      setHasMore(data.has_more);
    } catch (err: any) {
      setError(err.message || 'Failed to load more');
    } finally {
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    fetchTransactions(userId);
  }, [userId, fetchTransactions]);

  return (
    <main style={{ maxWidth: 880, margin: '40px auto', fontFamily: 'system-ui, sans-serif', padding: '0 20px', color: '#1e293b' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #e2e8f0', paddingBottom: 16 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700 }}>Wallet Operations</h1>
          <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: 14 }}>Production Assessment Dashboard</p>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <label style={{ fontSize: 13, fontWeight: 600 }}>
            User ID:{' '}
            <select
              value={userId}
              onChange={e => setUserId(e.target.value)}
              style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #cbd5e1' }}
            >
              <option value="1">User 1</option>
              <option value="2">User 2</option>
              <option value="9999">User 9999 (Test)</option>
            </select>
          </label>
          <button
            onClick={() => fetchTransactions(userId)}
            disabled={loading}
            style={{ padding: '6px 14px', borderRadius: 6, background: '#2563eb', color: '#fff', border: 'none', cursor: 'pointer', fontWeight: 500 }}
          >
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </header>

      {error && (
        <div role="alert" style={{ margin: '16px 0', padding: 12, background: '#fee2e2', border: '1px solid #f87171', borderRadius: 6, color: '#991b1b', fontSize: 14 }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      <section style={{ marginTop: 24 }}>
        {loading ? (
          <p style={{ color: '#64748b' }}>Loading transactions...</p>
        ) : items.length === 0 ? (
          <div style={{ padding: 32, textAlign: 'center', background: '#f8fafc', borderRadius: 8, color: '#64748b' }}>
            No transactions found for User {userId}.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: 14 }}>
            <thead>
              <tr style={{ background: '#f1f5f9', borderBottom: '2px solid #cbd5e1' }}>
                <th style={{ padding: '10px 12px' }}>ID</th>
                <th style={{ padding: '10px 12px' }}>Type</th>
                <th style={{ padding: '10px 12px' }}>Amount</th>
                <th style={{ padding: '10px 12px' }}>Status</th>
                <th style={{ padding: '10px 12px' }}>Reference</th>
              </tr>
            </thead>
            <tbody>
              {items.map(t => (
                <tr
                  key={t.id}
                  onClick={() => setSelected(t)}
                  style={{
                    borderBottom: '1px solid #e2e8f0',
                    cursor: 'pointer',
                    background: selected?.id === t.id ? '#eff6ff' : 'transparent'
                  }}
                >
                  <td style={{ padding: '10px 12px' }}>#{t.id}</td>
                  <td style={{ padding: '10px 12px', textTransform: 'capitalize' }}>{t.kind}</td>
                  <td style={{ padding: '10px 12px', fontWeight: 600 }}>${parseFloat(t.amount).toFixed(2)}</td>
                  <td style={{ padding: '10px 12px' }}>
                    <span style={{
                      padding: '2px 8px',
                      borderRadius: 12,
                      fontSize: 12,
                      background: t.status === 'completed' ? '#dcfce7' : '#fee2e2',
                      color: t.status === 'completed' ? '#166534' : '#991b1b'
                    }}>
                      {t.status}
                    </span>
                  </td>
                  <td style={{ padding: '10px 12px', color: '#64748b', fontSize: 13 }}>{t.reference || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {hasMore && (
          <div style={{ textAlign: 'center', marginTop: 16 }}>
            <button
              onClick={loadMore}
              disabled={loadingMore}
              style={{ padding: '8px 16px', borderRadius: 6, background: '#f1f5f9', border: '1px solid #cbd5e1', cursor: 'pointer' }}
            >
              {loadingMore ? 'Loading more...' : 'Load More'}
            </button>
          </div>
        )}
      </section>

      {selected && (
        <section style={{ marginTop: 24, padding: 16, border: '1px solid #cbd5e1', borderRadius: 8, background: '#fafafa' }}>
          <h2 style={{ margin: '0 0 12px', fontSize: 16 }}>Transaction Details (#{selected.id})</h2>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 13 }}>
            <div><strong>Amount:</strong> ${parseFloat(selected.amount).toFixed(2)}</div>
            <div><strong>Kind:</strong> {selected.kind}</div>
            <div><strong>Status:</strong> {selected.status}</div>
            <div><strong>Reference:</strong> {selected.reference || '—'}</div>
            <div><strong>Failure Reason:</strong> {selected.failure_reason || 'None'}</div>
          </div>
        </section>
      )}
    </main>
  );
}

const root = createRoot(document.getElementById('root')!);
root.render(<App />);