import express from 'express';
import cors from 'cors';
import Database from 'better-sqlite3';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const db = new Database(join(__dirname, '..', 'music.db'));
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
  CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    year INTEGER,
    genre TEXT,
    status TEXT NOT NULL DEFAULT 'Want to Try',
    notes TEXT,
    dateAdded TEXT NOT NULL DEFAULT (datetime('now'))
  )
`);

// Create index for fast search/filter
db.exec(`
  CREATE INDEX IF NOT EXISTS idx_albums_artist ON albums(artist COLLATE NOCASE);
  CREATE INDEX IF NOT EXISTS idx_albums_status ON albums(status);
  CREATE INDEX IF NOT EXISTS idx_albums_genre ON albums(genre);
`);

const app = express();
app.use(cors());
app.use(express.json({ limit: '10mb' }));

const VALID_STATUSES = ['Love', 'Need on Vinyl', 'Want to Try', 'Hate'];

// GET /api/albums - list with search, filter, sort
app.get('/api/albums', (req, res) => {
  const { search, status, genre, sortBy = 'dateAdded', sortDir = 'desc' } = req.query;

  let where = [];
  let params = {};

  if (search) {
    where.push(`(artist LIKE :search OR title LIKE :search OR notes LIKE :search)`);
    params.search = `%${search}%`;
  }
  if (status) {
    where.push(`status = :status`);
    params.status = status;
  }
  if (genre) {
    where.push(`genre = :genre`);
    params.genre = genre;
  }

  const allowedSort = ['artist', 'title', 'year', 'dateAdded', 'status', 'genre'];
  const col = allowedSort.includes(sortBy) ? sortBy : 'dateAdded';
  const dir = sortDir === 'asc' ? 'ASC' : 'DESC';
  const collate = ['artist', 'title', 'genre', 'status'].includes(col) ? 'COLLATE NOCASE' : '';

  const whereClause = where.length ? `WHERE ${where.join(' AND ')}` : '';
  const sql = `SELECT * FROM albums ${whereClause} ORDER BY ${col} ${collate} ${dir}`;

  const albums = db.prepare(sql).all(params);
  res.json(albums);
});

// GET /api/albums/stats - status counts
app.get('/api/albums/stats', (_req, res) => {
  const rows = db.prepare(`SELECT status, COUNT(*) as count FROM albums GROUP BY status`).all();
  const stats = { total: 0 };
  for (const row of rows) {
    stats[row.status] = row.count;
    stats.total += row.count;
  }
  res.json(stats);
});

// GET /api/albums/genres - distinct genres
app.get('/api/albums/genres', (_req, res) => {
  const rows = db.prepare(`SELECT DISTINCT genre FROM albums WHERE genre IS NOT NULL AND genre != '' ORDER BY genre COLLATE NOCASE`).all();
  res.json(rows.map(r => r.genre));
});

// POST /api/albums - add one
app.post('/api/albums', (req, res) => {
  const { artist, title, year, genre, status, notes } = req.body;
  if (!artist?.trim() || !title?.trim()) {
    return res.status(400).json({ error: 'Artist and title are required' });
  }
  if (status && !VALID_STATUSES.includes(status)) {
    return res.status(400).json({ error: `Invalid status. Must be one of: ${VALID_STATUSES.join(', ')}` });
  }

  // Check for duplicates
  const existing = db.prepare(
    `SELECT id FROM albums WHERE LOWER(artist) = LOWER(:artist) AND LOWER(title) = LOWER(:title)`
  ).get({ artist: artist.trim(), title: title.trim() });

  const stmt = db.prepare(`
    INSERT INTO albums (artist, title, year, genre, status, notes)
    VALUES (:artist, :title, :year, :genre, :status, :notes)
  `);
  const result = stmt.run({
    artist: artist.trim(),
    title: title.trim(),
    year: year ? parseInt(year, 10) : null,
    genre: genre || null,
    status: status || 'Want to Try',
    notes: notes || null,
  });

  const album = db.prepare(`SELECT * FROM albums WHERE id = ?`).get(result.lastInsertRowid);
  res.json({ album, duplicate: !!existing });
});

// PATCH /api/albums/:id - update (used for status cycling)
app.patch('/api/albums/:id', (req, res) => {
  const { id } = req.params;
  const fields = req.body;
  const allowed = ['artist', 'title', 'year', 'genre', 'status', 'notes'];
  const sets = [];
  const params = { id };

  for (const [key, value] of Object.entries(fields)) {
    if (allowed.includes(key)) {
      sets.push(`${key} = :${key}`);
      params[key] = value;
    }
  }
  if (sets.length === 0) return res.status(400).json({ error: 'No valid fields' });
  if (params.status && !VALID_STATUSES.includes(params.status)) {
    return res.status(400).json({ error: 'Invalid status' });
  }

  db.prepare(`UPDATE albums SET ${sets.join(', ')} WHERE id = :id`).run(params);
  const album = db.prepare(`SELECT * FROM albums WHERE id = ?`).get(id);
  if (!album) return res.status(404).json({ error: 'Not found' });
  res.json(album);
});

// DELETE /api/albums/:id
app.delete('/api/albums/:id', (req, res) => {
  const result = db.prepare(`DELETE FROM albums WHERE id = ?`).run(req.params.id);
  if (result.changes === 0) return res.status(404).json({ error: 'Not found' });
  res.json({ ok: true });
});

// GET /api/albums/export - export all as JSON
app.get('/api/albums/export', (_req, res) => {
  const albums = db.prepare(`SELECT artist, title, year, genre, status, notes, dateAdded FROM albums ORDER BY dateAdded`).all();
  res.setHeader('Content-Disposition', 'attachment; filename=music-collection.json');
  res.json(albums);
});

// POST /api/albums/import - bulk import
app.post('/api/albums/import', (req, res) => {
  const { albums } = req.body;
  if (!Array.isArray(albums)) {
    return res.status(400).json({ error: 'Expected { albums: [...] }' });
  }

  const checkDup = db.prepare(
    `SELECT id FROM albums WHERE LOWER(artist) = LOWER(?) AND LOWER(title) = LOWER(?)`
  );
  const insert = db.prepare(`
    INSERT INTO albums (artist, title, year, genre, status, notes)
    VALUES (:artist, :title, :year, :genre, :status, :notes)
  `);

  let added = 0;
  let skipped = 0;
  let errors = [];

  const runImport = db.transaction((items) => {
    for (const item of items) {
      if (!item.artist?.trim() || !item.title?.trim()) {
        errors.push(`Missing artist/title: ${JSON.stringify(item).slice(0, 80)}`);
        continue;
      }
      const dup = checkDup.get(item.artist.trim(), item.title.trim());
      if (dup) {
        skipped++;
        continue;
      }
      insert.run({
        artist: item.artist.trim(),
        title: item.title.trim(),
        year: item.year ? parseInt(item.year, 10) : null,
        genre: item.genre || null,
        status: VALID_STATUSES.includes(item.status) ? item.status : 'Want to Try',
        notes: item.notes || null,
      });
      added++;
    }
  });

  runImport(albums);
  res.json({ added, skipped, errors });
});

const PORT = 3001;
app.listen(PORT, () => {
  console.log(`Music collection API running on http://localhost:${PORT}`);
});
