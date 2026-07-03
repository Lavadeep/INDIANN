# IndiAnn Setup Guide

IndiAnn is a web-based annotation platform for low-resource Indic languages supporting:

- POS Annotation
- Span–Relation Annotation
- Dependency Annotation
- Semantic Role Labeling (SRL)
- Multi-user annotation and curation workflows

View application demo: [INDIANN_DEMO](https://drive.google.com/file/d/1CD0LyeBIGgxbgfe4vYIV3kVwFl-1CyO4/view?usp=sharing)

Backend:
- FastAPI (Python)

Frontend:
- HTML/CSS/JavaScript

Database:
- PostgreSQL

Production Web Server:
- NGINX

---

# Project Structure

```text
annotation/
├── backend/
├── frontend/
├── requirements.txt
└── README.md
```

---

# Local Machine Setup

## 1. Clone Repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd annotation
```

---

## 2. Create Virtual Environment

### Linux / Mac

```bash
python3 -m venv venv
source venv/bin/activate
```

### Windows

```powershell
python -m venv venv
venv\Scripts\activate
```

---

## 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

# PostgreSQL Setup

## 1. Install PostgreSQL

### Ubuntu

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
```

### Windows

Install PostgreSQL from:

https://www.postgresql.org/download/

---

## 2. Create Database and User

Login to PostgreSQL:

```bash
sudo -u postgres psql
```

Run:

```sql
CREATE USER anno_admin WITH PASSWORD 'admin@annoiitbbs';

CREATE DATABASE "Annotation";

GRANT ALL PRIVILEGES ON DATABASE "Annotation" TO anno_admin;
```

Exit:

```sql
\q
```

---

# Configure Database Connection

Open:

```text
backend/database.py
```

Set:

```python
DATABASE_URL = "postgresql://anno_admin:admin%40annoiitbbs@localhost:5432/Annotation"
```

---

# Run Backend

From project root:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend API:

```text
http://localhost:8000/docs
```

---

# Run Frontend

Since frontend API calls use:

```javascript
const API = "/api";
```

the frontend must be served through a web server/proxy.

---

## Start Frontend Server

```bash
cd frontend
python -m http.server 5500
```

Frontend URL:

```text
http://localhost:5500/login.html
```

---

# Local Development API Proxy (Important)

Because frontend uses:

```javascript
const API = "/api";
```

you should either:

- use a local reverse proxy (recommended)
OR
- temporarily change API to:

```javascript
const API = "http://localhost:8000";
```

during local-only testing.

---

# Production Server Deployment (Ubuntu + NGINX)

---

# 1. Install Dependencies

```bash
sudo apt update

sudo apt install python3-pip python3-venv nginx postgresql postgresql-contrib
```

---

# 2. Clone Repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd annotation
```

---

# 3. Setup Python Environment

```bash
python3 -m venv venv

source venv/bin/activate

pip install -r requirements.txt
```

---

# 4. Setup PostgreSQL

```bash
sudo -u postgres psql
```

Run:

```sql
CREATE USER anno_admin WITH PASSWORD 'admin@annoiitbbs';

CREATE DATABASE "Annotation";

GRANT ALL PRIVILEGES ON DATABASE "Annotation" TO anno_admin;
```

Exit:

```sql
\q
```

---

# 5. Configure Database URL

Edit:

```text
backend/database.py
```

Set:

```python
DATABASE_URL = "postgresql://anno_admin:admin%40annoiitbbs@localhost:5432/Annotation"
```

---

# 6. Start Backend

From project root:

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

---

# 7. Deploy Frontend

Create frontend directory:

```bash
sudo mkdir -p /var/www/annotation
```

Copy frontend:

```bash
sudo cp -r frontend/* /var/www/annotation/
```

---

# 8. Configure NGINX

Edit:

```bash
sudo nano /etc/nginx/sites-available/default
```

Replace server block with:

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    server_name _;

    root /var/www/annotation;
    index login.html;

    location / {
        try_files $uri $uri/ =404;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

# 9. Restart NGINX

Test configuration:

```bash
sudo nginx -t
```

Restart nginx:

```bash
sudo systemctl restart nginx
```

---

# 10. Access Application

Open:

```text
http://SERVER_IP
```

Example:

```text
http://10.10.107.46
```

---

# Run Backend Automatically (Recommended)

Create service:

```bash
sudo nano /etc/systemd/system/annotation.service
```

Paste:

```ini
[Unit]
Description=IndiAnn Backend
After=network.target

[Service]
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/annotation
ExecStart=/home/YOUR_USERNAME/annotation/venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

---

# Enable Service

Reload systemd:

```bash
sudo systemctl daemon-reload
```

Enable service:

```bash
sudo systemctl enable annotation
```

Start service:

```bash
sudo systemctl start annotation
```

Check service status:

```bash
sudo systemctl status annotation
```

---

# Useful Commands

## Restart Backend

```bash
sudo systemctl restart annotation
```

---

## Stop Backend

```bash
sudo systemctl stop annotation
```

---

## Restart NGINX

```bash
sudo systemctl restart nginx
```

---

## Check Backend Logs

```bash
journalctl -u annotation -f
```

---

# Production Architecture

```text
Users
   ↓
NGINX (Port 80)
   ↓
FastAPI Backend (127.0.0.1:8000)
   ↓
PostgreSQL
```

---

## Citation

```bibtex
@inproceedings{indiann2026,
  title     = {IndiAnn: A Web-based Annotation Platform for Indic Languages},
  author    = {Bandaru, Lavadeep and Raghav, Ritwik and Jana, Abhik},
  booktitle = {Proceedings of the Linguistic Annotation Workshop (LAW XX)},
  year      = {2026}
}
```

---
