#!/bin/sh
# Runs once, on first container init, alongside the default POSTGRES_DB creation.
# Creates a second database used exclusively by the test suite (DATABASE_URL_TEST).
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE agentops_test;
EOSQL
