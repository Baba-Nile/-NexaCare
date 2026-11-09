CREATE TABLE users (id {PK}, email TEXT NOT NULL UNIQUE, full_name TEXT NOT NULL, role TEXT NOT NULL, password_hash TEXT NOT NULL, must_change_password INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, last_login_at TEXT, password_changed_at TEXT);
CREATE TABLE sessions (id {PK}, token_hash TEXT NOT NULL UNIQUE, realm TEXT NOT NULL, subject_id BIGINT NOT NULL, csrf TEXT NOT NULL, created_at TEXT NOT NULL, last_seen TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE INDEX idx_sessions_subject ON sessions(realm, subject_id);
CREATE TABLE login_attempts (id {PK}, realm TEXT NOT NULL, identifier_hash TEXT NOT NULL, ip_hash TEXT NOT NULL, ts TEXT NOT NULL, success INTEGER NOT NULL);
CREATE INDEX idx_attempts_ident ON login_attempts(identifier_hash, ts);
CREATE INDEX idx_attempts_ip ON login_attempts(ip_hash, ts);
CREATE TABLE audit_events (id {PK}, ts TEXT NOT NULL, actor_type TEXT, actor_id BIGINT, action TEXT NOT NULL, target_type TEXT, target_id BIGINT, outcome TEXT NOT NULL, detail TEXT NOT NULL, ip TEXT, prev_hash TEXT NOT NULL, row_hash TEXT NOT NULL);
CREATE INDEX idx_audit_ts ON audit_events(ts);
