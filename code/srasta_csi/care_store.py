"""Summary-only SQLite history. Camera images, I/Q, identities and secrets never enter it."""
import sqlite3
import threading
import time

class CareEventStore:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(str(path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('''CREATE TABLE IF NOT EXISTS care_events (
          id INTEGER PRIMARY KEY, occurred_at REAL NOT NULL, source_time_s REAL,
          state TEXT NOT NULL, reason TEXT NOT NULL, source TEXT NOT NULL,
          confidence REAL, acknowledged_at REAL)''')
        self.connection.commit()

    def append(self, state, reason, source, source_time_s=None, confidence=None):
        from .care_state import STATES
        if state not in STATES or source not in ('simulator','replay','serial'):
            raise ValueError('invalid event classification')
        allowed = {'no_confirmed_presence','ordinary_activity','prolonged_inactivity','possible_fall','breathing_pattern','uncertain_result','insufficient_signal','persistent_anomaly','post_anomaly_inactivity','activity_recovered','anomaly_supported_by_pose','simulated_state'}
        if reason not in allowed:
            raise ValueError('event reason must be a bounded code')
        with self.lock:
            cursor = self.connection.execute('INSERT INTO care_events(occurred_at,source_time_s,state,reason,source,confidence) VALUES(?,?,?,?,?,?)', (time.time(),source_time_s,state,reason,source,confidence))
            self.connection.commit()
            return cursor.lastrowid

    def acknowledge(self, event_id):
        with self.lock:
            result = self.connection.execute('UPDATE care_events SET acknowledged_at=? WHERE id=? AND state IN (?,?,?) AND acknowledged_at IS NULL', (time.time(),event_id,'inactive','anomaly','critical'))
            self.connection.commit()
            return result.rowcount == 1

    def list(self, limit=50):
        with self.lock:
            return [dict(row) for row in self.connection.execute('SELECT * FROM care_events ORDER BY id DESC LIMIT ?', (max(1,min(limit,200)),))]

    def latest(self, source):
        with self.lock:
            row = self.connection.execute('SELECT * FROM care_events WHERE source=? ORDER BY id DESC LIMIT 1',(source,)).fetchone()
            return dict(row) if row else None

    def close(self):
        self.connection.close()
