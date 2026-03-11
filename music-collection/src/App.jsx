import React, { useState, useEffect, useCallback, useRef } from 'react';

const STATUSES = ['Love', 'Need on Vinyl', 'Want to Try', 'Hate'];
const STATUS_COLORS = {
  'Love': '#f5c842',
  'Need on Vinyl': '#ff6b35',
  'Want to Try': '#7b68ee',
  'Hate': '#ff3860',
};

const GENRE_PRESETS = [
  'Grunge', 'Alt Rock', 'Hip Hop', 'Metal', 'Punk', 'Industrial',
  'Prog Metal', 'Nu Metal', 'Alt Metal', 'Funk Rock', 'Stoner Rock',
  'Electronic', 'Trip Hop', 'Dream Pop', 'Ska Punk', 'Groove Metal',
  'Gothic Metal', 'Funk Metal', 'Post-Hardcore', 'Rap Metal',
  'Classic Rock', 'Blues', 'Jazz', 'Country', 'R&B', 'Pop', 'Indie',
  'Shoegaze', 'Post-Punk', 'Hardcore', 'Doom Metal', 'Black Metal',
  'Death Metal', 'Thrash Metal', 'Ambient', 'Other',
];

const API = '/api/albums';

function App() {
  const [albums, setAlbums] = useState([]);
  const [stats, setStats] = useState({});
  const [genres, setGenres] = useState([]);
  const [search, setSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterGenre, setFilterGenre] = useState('');
  const [sortBy, setSortBy] = useState('dateAdded');
  const [sortDir, setSortDir] = useState('desc');
  const [showImport, setShowImport] = useState(false);
  const [importText, setImportText] = useState('');
  const [importResult, setImportResult] = useState(null);
  const [notification, setNotification] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  const artistRef = useRef();

  // Form state
  const [form, setForm] = useState({
    artist: '', title: '', year: '', genre: '', status: 'Want to Try', notes: '',
  });

  const notify = useCallback((msg, type = 'info') => {
    setNotification({ msg, type });
    setTimeout(() => setNotification(null), 3000);
  }, []);

  const fetchAlbums = useCallback(async () => {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    if (filterStatus) params.set('status', filterStatus);
    if (filterGenre) params.set('genre', filterGenre);
    params.set('sortBy', sortBy);
    params.set('sortDir', sortDir);
    const res = await fetch(`${API}?${params}`);
    setAlbums(await res.json());
  }, [search, filterStatus, filterGenre, sortBy, sortDir]);

  const fetchStats = useCallback(async () => {
    const res = await fetch(`${API}/stats`);
    setStats(await res.json());
  }, []);

  const fetchGenres = useCallback(async () => {
    const res = await fetch(`${API}/genres`);
    const data = await res.json();
    const merged = [...new Set([...GENRE_PRESETS, ...data])].sort();
    setGenres(merged);
  }, []);

  useEffect(() => { fetchAlbums(); }, [fetchAlbums]);
  useEffect(() => { fetchStats(); fetchGenres(); }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!form.artist.trim() || !form.title.trim()) return;

    const res = await fetch(API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    });
    const data = await res.json();
    if (data.duplicate) {
      notify(`Duplicate detected — added anyway: ${form.artist} - ${form.title}`, 'warn');
    } else {
      notify(`Added: ${form.artist} - ${form.title}`, 'success');
    }
    setForm({ artist: '', title: '', year: '', genre: form.genre, status: form.status, notes: '' });
    artistRef.current?.focus();
    fetchAlbums();
    fetchStats();
    fetchGenres();
  };

  const cycleStatus = async (album) => {
    const idx = STATUSES.indexOf(album.status);
    const next = STATUSES[(idx + 1) % STATUSES.length];
    await fetch(`${API}/${album.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: next }),
    });
    fetchAlbums();
    fetchStats();
  };

  const deleteAlbum = async (id) => {
    await fetch(`${API}/${id}`, { method: 'DELETE' });
    setDeleteConfirm(null);
    fetchAlbums();
    fetchStats();
    notify('Album deleted', 'info');
  };

  const handleExport = () => {
    window.open(`${API}/export`, '_blank');
  };

  const handleImport = async () => {
    let parsed;
    try {
      parsed = JSON.parse(importText);
      if (!Array.isArray(parsed)) parsed = [parsed];
    } catch {
      notify('Invalid JSON', 'error');
      return;
    }
    const res = await fetch(`${API}/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ albums: parsed }),
    });
    const result = await res.json();
    setImportResult(result);
    notify(`Imported ${result.added} albums (${result.skipped} duplicates skipped)`, 'success');
    fetchAlbums();
    fetchStats();
    fetchGenres();
  };

  const handleFileImport = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setImportText(ev.target.result);
    };
    reader.readAsText(file);
  };

  const handleSort = (col) => {
    if (sortBy === col) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(col);
      setSortDir(col === 'dateAdded' ? 'desc' : 'asc');
    }
  };

  const sortIndicator = (col) => {
    if (sortBy !== col) return '';
    return sortDir === 'asc' ? ' ▲' : ' ▼';
  };

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '16px 20px' }}>
      {notification && (
        <div style={{
          position: 'fixed', top: 12, right: 12, padding: '8px 16px',
          background: notification.type === 'error' ? '#ff3860' :
            notification.type === 'warn' ? '#ff6b35' :
            notification.type === 'success' ? '#2d6' : '#555',
          color: '#fff', borderRadius: 4, zIndex: 1000, fontSize: 12,
        }}>
          {notification.msg}
        </div>
      )}

      <header style={{ marginBottom: 16 }}>
        <h1 style={{ fontSize: 18, marginBottom: 8, color: '#fff' }}>
          Music Collection
          <span style={{ fontSize: 12, color: 'var(--text-dim)', marginLeft: 12 }}>
            {stats.total || 0} albums
          </span>
        </h1>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 12 }}>
          {STATUSES.map(s => (
            <span key={s} style={{ color: STATUS_COLORS[s] }}>
              {s}: {stats[s] || 0}
            </span>
          ))}
        </div>
      </header>

      {/* Add Album Form */}
      <form onSubmit={handleAdd} style={{
        display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16,
        padding: 10, background: 'var(--bg-secondary)', borderRadius: 4,
      }}>
        <input
          ref={artistRef}
          placeholder="Artist *"
          value={form.artist}
          onChange={e => setForm({ ...form, artist: e.target.value })}
          style={{ width: 160 }}
          required
        />
        <input
          placeholder="Title *"
          value={form.title}
          onChange={e => setForm({ ...form, title: e.target.value })}
          style={{ width: 180 }}
          required
        />
        <input
          placeholder="Year"
          value={form.year}
          onChange={e => setForm({ ...form, year: e.target.value })}
          style={{ width: 60 }}
          type="number"
          min="1900"
          max="2099"
        />
        <input
          list="genre-list"
          placeholder="Genre"
          value={form.genre}
          onChange={e => setForm({ ...form, genre: e.target.value })}
          style={{ width: 130 }}
        />
        <datalist id="genre-list">
          {genres.map(g => <option key={g} value={g} />)}
        </datalist>
        <select
          value={form.status}
          onChange={e => setForm({ ...form, status: e.target.value })}
          style={{ width: 130, color: STATUS_COLORS[form.status] }}
        >
          {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <input
          placeholder="Notes"
          value={form.notes}
          onChange={e => setForm({ ...form, notes: e.target.value })}
          style={{ flex: 1, minWidth: 120 }}
        />
        <button type="submit" style={{ background: '#2a4a2a', borderColor: '#3a6a3a' }}>+ Add</button>
      </form>

      {/* Filters & Controls */}
      <div style={{
        display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center', flexWrap: 'wrap',
      }}>
        <input
          placeholder="Search artist, title, notes..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ width: 250 }}
        />
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
          <option value="">All statuses</option>
          {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={filterGenre} onChange={e => setFilterGenre(e.target.value)}>
          <option value="">All genres</option>
          {genres.map(g => <option key={g} value={g}>{g}</option>)}
        </select>
        <div style={{ flex: 1 }} />
        <button onClick={handleExport}>Export JSON</button>
        <button onClick={() => setShowImport(!showImport)}>
          {showImport ? 'Close Import' : 'Import / Seed'}
        </button>
      </div>

      {/* Import Panel */}
      {showImport && (
        <div style={{
          padding: 12, background: 'var(--bg-secondary)', borderRadius: 4, marginBottom: 12,
        }}>
          <div style={{ marginBottom: 8, fontSize: 12, color: 'var(--text-dim)' }}>
            Paste a JSON array of albums, or load a file. Format: {`[{"artist":"...","title":"...","year":1994,"genre":"...","status":"Love","notes":"..."}]`}
          </div>
          <textarea
            value={importText}
            onChange={e => setImportText(e.target.value)}
            placeholder='[{"artist": "Alice in Chains", "title": "Dirt", "year": 1992, "genre": "Grunge", "status": "Love"}]'
            style={{ width: '100%', height: 100, resize: 'vertical', marginBottom: 8 }}
          />
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button onClick={handleImport} style={{ background: '#2a4a2a', borderColor: '#3a6a3a' }}>
              Import Albums
            </button>
            <label style={{ cursor: 'pointer', padding: '6px 12px', background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 3 }}>
              Load File
              <input type="file" accept=".json" onChange={handleFileImport} style={{ display: 'none' }} />
            </label>
            {importResult && (
              <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                Added: {importResult.added} | Skipped: {importResult.skipped}
                {importResult.errors.length > 0 && ` | Errors: ${importResult.errors.length}`}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Album Table */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)', fontSize: 11, color: 'var(--text-dim)' }}>
              <th style={thStyle} onClick={() => handleSort('artist')}>
                Artist{sortIndicator('artist')}
              </th>
              <th style={thStyle} onClick={() => handleSort('title')}>
                Title{sortIndicator('title')}
              </th>
              <th style={{ ...thStyle, width: 50 }} onClick={() => handleSort('year')}>
                Year{sortIndicator('year')}
              </th>
              <th style={{ ...thStyle, width: 110 }} onClick={() => handleSort('genre')}>
                Genre{sortIndicator('genre')}
              </th>
              <th style={{ ...thStyle, width: 120 }} onClick={() => handleSort('status')}>
                Status{sortIndicator('status')}
              </th>
              <th style={thStyle}>Notes</th>
              <th style={{ ...thStyle, width: 90 }} onClick={() => handleSort('dateAdded')}>
                Added{sortIndicator('dateAdded')}
              </th>
              <th style={{ ...thStyle, width: 30 }}></th>
            </tr>
          </thead>
          <tbody>
            {albums.map(album => (
              <tr key={album.id} style={{ borderBottom: '1px solid #222' }}>
                <td style={tdStyle}>{album.artist}</td>
                <td style={tdStyle}>{album.title}</td>
                <td style={{ ...tdStyle, color: 'var(--text-dim)' }}>{album.year || ''}</td>
                <td style={{ ...tdStyle, color: 'var(--text-dim)', fontSize: 11 }}>{album.genre || ''}</td>
                <td style={tdStyle}>
                  <button
                    onClick={() => cycleStatus(album)}
                    style={{
                      background: 'transparent',
                      border: `1px solid ${STATUS_COLORS[album.status]}`,
                      color: STATUS_COLORS[album.status],
                      padding: '2px 8px',
                      borderRadius: 3,
                      fontSize: 11,
                      cursor: 'pointer',
                      width: '100%',
                      textAlign: 'center',
                    }}
                    title="Click to cycle status"
                  >
                    {album.status}
                  </button>
                </td>
                <td style={{ ...tdStyle, color: 'var(--text-dim)', fontSize: 11, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {album.notes || ''}
                </td>
                <td style={{ ...tdStyle, color: 'var(--text-dim)', fontSize: 10 }}>
                  {album.dateAdded?.slice(0, 10)}
                </td>
                <td style={tdStyle}>
                  {deleteConfirm === album.id ? (
                    <span style={{ display: 'flex', gap: 2 }}>
                      <button
                        onClick={() => deleteAlbum(album.id)}
                        style={{ background: '#ff3860', color: '#fff', border: 'none', padding: '2px 6px', fontSize: 10 }}
                      >✓</button>
                      <button
                        onClick={() => setDeleteConfirm(null)}
                        style={{ padding: '2px 6px', fontSize: 10 }}
                      >✗</button>
                    </span>
                  ) : (
                    <button
                      onClick={() => setDeleteConfirm(album.id)}
                      style={{ background: 'transparent', border: 'none', color: '#666', cursor: 'pointer', fontSize: 12 }}
                      title="Delete"
                    >×</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {albums.length === 0 && (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-dim)' }}>
            No albums yet. Add some above or import a collection.
          </div>
        )}
      </div>
    </div>
  );
}

const thStyle = {
  textAlign: 'left',
  padding: '6px 8px',
  cursor: 'pointer',
  userSelect: 'none',
  whiteSpace: 'nowrap',
};

const tdStyle = {
  padding: '5px 8px',
  whiteSpace: 'nowrap',
};

export default App;
