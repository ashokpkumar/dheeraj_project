FROM os_image:latest
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Default command (overridden per service in docker-compose)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]