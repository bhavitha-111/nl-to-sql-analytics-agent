# =====================================================================
# STAGE 1: Build & Dependency Isolation
# =====================================================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system configuration tools required to build C-dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Optimize Docker layer caching by analyzing package requirements first
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# =====================================================================
# STAGE 2: Lightweight Runtime Execution Environment
# =====================================================================
FROM python:3.11-slim AS runner

WORKDIR /app

# Pull user-space globally compiled packages forward from build phase
COPY --from=builder /root/.local /root/.local
COPY . .

# Set explicit python layer variables to block caching and maintain standard logs
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Expose Streamlit's structural networking bridge port
EXPOSE 8501

# Add responsive health queries to evaluate interface status
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Launch the orchestrator application 
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]