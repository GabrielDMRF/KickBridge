-- Esquema SQLite de KickBridge. La migración aplicable es alembic/versions/20261120_0001_initial.py.
-- No guarda tokens en claro: api_token_hash es HMAC-SHA256 y los tokens de Kick van cifrados con AES-256-GCM.

PRAGMA foreign_keys = ON;

CREATE TABLE streamers (
  id INTEGER PRIMARY KEY,
  name VARCHAR(64) NOT NULL UNIQUE,
  kick_broadcaster_user_id BIGINT NOT NULL,
  api_token_hash VARCHAR(64) NOT NULL UNIQUE,
  status VARCHAR(16) NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);
CREATE INDEX ix_streamers_kick_broadcaster_user_id ON streamers (kick_broadcaster_user_id);
CREATE INDEX ix_streamers_status ON streamers (status);

CREATE TABLE minecraft_accounts (
  id INTEGER PRIMARY KEY,
  streamer_id INTEGER NOT NULL REFERENCES streamers(id) ON DELETE CASCADE,
  uuid VARCHAR(36) NOT NULL,
  username VARCHAR(16) NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  CONSTRAINT uq_mc_streamer_uuid UNIQUE (streamer_id, uuid)
);
CREATE INDEX ix_minecraft_accounts_streamer_id ON minecraft_accounts (streamer_id);

CREATE TABLE kick_accounts (
  id INTEGER PRIMARY KEY,
  streamer_id INTEGER NOT NULL REFERENCES streamers(id) ON DELETE CASCADE,
  minecraft_account_id INTEGER NOT NULL UNIQUE REFERENCES minecraft_accounts(id) ON DELETE CASCADE,
  kick_user_id BIGINT NOT NULL,
  kick_username VARCHAR(64) NOT NULL,
  access_token_enc TEXT NOT NULL,
  refresh_token_enc TEXT NOT NULL,
  access_expires_at DATETIME NOT NULL,
  refresh_expires_at DATETIME,
  scopes VARCHAR(256) NOT NULL,
  status VARCHAR(16) NOT NULL,
  linked_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  CONSTRAINT uq_kick_streamer_user UNIQUE (streamer_id, kick_user_id)
);
CREATE INDEX ix_kick_accounts_streamer_id ON kick_accounts (streamer_id);
CREATE INDEX ix_kick_accounts_status ON kick_accounts (status);

CREATE TABLE link_sessions (
  id INTEGER PRIMARY KEY,
  streamer_id INTEGER NOT NULL REFERENCES streamers(id) ON DELETE CASCADE,
  minecraft_uuid VARCHAR(36) NOT NULL,
  minecraft_username VARCHAR(16) NOT NULL,
  code_hash VARCHAR(64) NOT NULL UNIQUE,
  state_enc TEXT NOT NULL,
  state_hash VARCHAR(64) NOT NULL UNIQUE,
  verifier_enc TEXT NOT NULL,
  code_challenge VARCHAR(128) NOT NULL,
  expires_at DATETIME NOT NULL,
  used_at DATETIME,
  created_at DATETIME NOT NULL
);

CREATE TABLE audit_logs (
  id INTEGER PRIMARY KEY,
  streamer_id INTEGER REFERENCES streamers(id) ON DELETE SET NULL,
  minecraft_uuid VARCHAR(36),
  action VARCHAR(64) NOT NULL,
  result VARCHAR(32) NOT NULL,
  detail VARCHAR(300) NOT NULL,
  created_at DATETIME NOT NULL
);
CREATE INDEX ix_audit_streamer_created ON audit_logs (streamer_id, created_at);

CREATE TABLE message_events (
  id INTEGER PRIMARY KEY,
  streamer_id INTEGER NOT NULL REFERENCES streamers(id) ON DELETE CASCADE,
  minecraft_uuid VARCHAR(36) NOT NULL,
  kick_user_id BIGINT NOT NULL,
  success BOOLEAN NOT NULL,
  kick_status INTEGER,
  kick_message_id VARCHAR(36),
  created_at DATETIME NOT NULL
);
CREATE INDEX ix_message_streamer_player_created ON message_events (streamer_id, minecraft_uuid, created_at);

CREATE TABLE request_nonces (
  id INTEGER PRIMARY KEY,
  streamer_id INTEGER NOT NULL REFERENCES streamers(id) ON DELETE CASCADE,
  nonce_hash VARCHAR(64) NOT NULL UNIQUE,
  expires_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL
);
