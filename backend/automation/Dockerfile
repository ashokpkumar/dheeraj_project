FROM os_image:latest

# Build arguments
ARG ROLE=orchestrator
ARG NODE_NAME=default
ARG IS_ORCHESTRATOR=True

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/app:$PATH" \
    ROLE=${ROLE} \
    NODE_NAME=${NODE_NAME} \
    IS_ORCHESTRATOR=${IS_ORCHESTRATOR}

# Set work directory
WORKDIR /app

# Install system dependencies

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy project
COPY . .

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create a non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose ports
EXPOSE 8000

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Default command based on role
CMD ["serve"]
