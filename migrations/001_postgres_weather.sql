-- Idempotent Digital Bonsai weather schema for PostgreSQL / Supabase.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at_utc TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS api_requests (
    id BIGSERIAL PRIMARY KEY,
    requested_at_utc TIMESTAMPTZ NOT NULL,
    completed_at_utc TIMESTAMPTZ,
    endpoint TEXT NOT NULL,
    request_type TEXT NOT NULL,
    parameters_json JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('started', 'success', 'error')),
    response_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS hourly_weather (
    id BIGSERIAL PRIMARY KEY,
    weather_timestamp_utc TIMESTAMPTZ NOT NULL,
    retrieval_timestamp_utc TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    data_type TEXT NOT NULL CHECK (data_type IN ('forecast', 'historical')),
    temperature_2m DOUBLE PRECISION,
    relative_humidity_2m DOUBLE PRECISION,
    cloud_cover DOUBLE PRECISION,
    precipitation DOUBLE PRECISION,
    sunshine_duration DOUBLE PRECISION,
    weather_code INTEGER,
    wind_speed_10m DOUBLE PRECISION,
    units_json JSONB NOT NULL,
    data_quality TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    request_id BIGINT REFERENCES api_requests(id),
    UNIQUE (source, data_type, weather_timestamp_utc, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_hourly_time ON hourly_weather(weather_timestamp_utc);

CREATE TABLE IF NOT EXISTS current_weather (
    id BIGSERIAL PRIMARY KEY,
    weather_timestamp_utc TIMESTAMPTZ NOT NULL,
    retrieval_timestamp_utc TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    temperature_2m DOUBLE PRECISION,
    relative_humidity_2m DOUBLE PRECISION,
    cloud_cover DOUBLE PRECISION,
    precipitation DOUBLE PRECISION,
    weather_code INTEGER,
    wind_speed_10m DOUBLE PRECISION,
    is_day INTEGER,
    units_json JSONB NOT NULL,
    data_quality TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    request_id BIGINT REFERENCES api_requests(id),
    UNIQUE (source, weather_timestamp_utc, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_current_time ON current_weather(weather_timestamp_utc);

INSERT INTO schema_migrations(version) VALUES ('001_postgres_weather')
ON CONFLICT (version) DO NOTHING;
