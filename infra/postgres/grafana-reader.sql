-- Read-only role for Grafana: the metrics views only, never the raw tables.
-- Run once per environment (psql -v password='…' -f grafana-reader.sql), then set
-- GRAFANA_PG_USER=grafana_reader and GRAFANA_PG_PASSWORD for the grafana service.
CREATE ROLE grafana_reader LOGIN PASSWORD :'password';
GRANT CONNECT ON DATABASE kainem TO grafana_reader;
GRANT USAGE ON SCHEMA public TO grafana_reader;
DO $$
DECLARE v record;
BEGIN
    FOR v IN SELECT table_name FROM information_schema.views
             WHERE table_schema = 'public' AND table_name LIKE 'metrics_%' LOOP
        EXECUTE format('GRANT SELECT ON %I TO grafana_reader', v.table_name);
    END LOOP;
END $$;
