#!/bin/sh
# Первый старт контейнера postgres (docker-entrypoint-initdb.d): роли кластера и БД приложения — как в
# backend/tests/conftest.py. Схему создают миграции (сервис migrate), а не этот скрипт.
# Пароли — из окружения; в SQL они попадают переменными psql (:'pw'), без подстановки в текст команды.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v migrator_pw="$APP_MIGRATOR_PASSWORD" -v rw_pw="$APP_RW_PASSWORD" -v token_pw="$APP_TOKEN_PASSWORD" \
  -v system_pw="$APP_SYSTEM_PASSWORD" -v deleter_pw="$APP_DELETER_PASSWORD" -v db="$APP_DB" <<'SQL'
CREATE ROLE app_migrator LOGIN PASSWORD :'migrator_pw';
CREATE ROLE app_rw LOGIN PASSWORD :'rw_pw';
CREATE ROLE app_token LOGIN PASSWORD :'token_pw';
CREATE ROLE app_system LOGIN PASSWORD :'system_pw';
CREATE ROLE app_deleter LOGIN PASSWORD :'deleter_pw';
GRANT app_rw TO app_token;   -- воркер = права приложения + чтение токенов
GRANT app_rw TO app_system;  -- системные задачи = права приложения без фильтра RLS
CREATE DATABASE :"db" OWNER app_migrator;
\connect :"db"
GRANT CREATE, USAGE ON SCHEMA public TO app_migrator;
GRANT USAGE ON SCHEMA public TO app_rw, app_token, app_system, app_deleter;
SQL
