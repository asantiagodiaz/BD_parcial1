#!/usr/bin/env bash
# Instala PostgreSQL nativo y crea las dos bases del proyecto.
# Ejecutar UNA vez:   bash backend/setup-postgres-local.sh
set -e

echo ">> Instalando PostgreSQL (pedira tu contrasena de sudo)..."
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib

echo ">> Arrancando el servicio..."
sudo systemctl enable --now postgresql

echo ">> Creando usuario y bases de datos..."
sudo -u postgres psql <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aerolinea') THEN
    CREATE ROLE aerolinea LOGIN PASSWORD 'aerolinea';
  END IF;
END $$;
SELECT 'CREATE DATABASE aerolinea_oltp OWNER aerolinea'
  WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'aerolinea_oltp')\gexec
SELECT 'CREATE DATABASE aerolinea_olap OWNER aerolinea'
  WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'aerolinea_olap')\gexec
SQL

echo ">> Listo."
echo "   OLTP: postgresql+psycopg://aerolinea:aerolinea@localhost:5432/aerolinea_oltp"
echo "   OLAP: postgresql+psycopg://aerolinea:aerolinea@localhost:5432/aerolinea_olap"
echo
echo "   (ambas bases viven en la MISMA instancia local en el puerto 5432;"
echo "    en AWS seran dos instancias RDS separadas - ver docs/07)"
