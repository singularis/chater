# Gunicorn configuration file for production deployment
import multiprocessing
import os

# Server socket
port = os.getenv("PORT", "5000")
bind = f"0.0.0.0:{port}"
backlog = 2048

# Worker processes
workers = min(4, multiprocessing.cpu_count() * 2 + 1)
worker_class = "sync"
worker_connections = 1000
timeout = 60
graceful_timeout = 30
keepalive = 2

# Restart workers after this many requests, to prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging - use environment variable for log level
accesslog = "-"
errorlog = "-"
log_level_env = os.getenv("LOG_LEVEL", "WARNING").lower()
loglevel = log_level_env
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
capture_output = True

# Process naming
proc_name = "chater_ui"

# Server mechanics
preload_app = True
daemon = False
pidfile = None
user = None
group = None
tmp_upload_dir = None

# SSL (if certificates are available)
# keyfile = None
# certfile = None
