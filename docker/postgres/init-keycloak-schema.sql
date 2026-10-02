-- Keycloak creates its own tables in this schema on first start.
-- The Postgres entrypoint runs this only when the data volume is empty.
CREATE SCHEMA IF NOT EXISTS keycloak AUTHORIZATION tenant;
GRANT ALL ON SCHEMA keycloak TO tenant;
