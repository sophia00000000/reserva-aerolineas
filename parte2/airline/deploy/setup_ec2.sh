#!/bin/bash
# Ejecutar EN la EC2 (Amazon Linux 2023), dentro de ~/airline:  bash deploy/setup_ec2.sh
set -e
sudo dnf install -y postgresql15-server postgresql15 python3.11 python3.11-pip
sudo postgresql-setup --initdb
sudo sed -i 's/ident$/scram-sha-256/' /var/lib/pgsql/data/pg_hba.conf
sudo systemctl enable --now postgresql
sudo -u postgres psql -c "CREATE USER airline WITH PASSWORD 'airline';" \
                      -c "CREATE DATABASE airline OWNER airline;"
cd ~/airline/backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
PGPASSWORD=airline psql -h 127.0.0.1 -U airline -d airline -f schema.sql
sudo cp ~/airline/deploy/airline.service /etc/systemd/system/airline.service
sudo systemctl daemon-reload
sudo systemctl enable --now airline
sleep 3; curl -s localhost/health && echo " <- backend arriba"
