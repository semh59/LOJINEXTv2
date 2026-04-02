#!/bin/bash
# Creates additional databases if they do not already exist.
# Mounted into postgres as /docker-entrypoint-initdb.d/init-db.sh
set -e

LOCATION_DB="${LOCATION_DB_NAME:-location_service}"
DRIVER_DB="${DRIVER_DB_NAME:-driver_service}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE ${LOCATION_DB}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${LOCATION_DB}')\gexec
    SELECT 'CREATE DATABASE ${DRIVER_DB}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DRIVER_DB}')\gexec
EOSQL
