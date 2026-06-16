FROM os_image:latest
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Copy entrypoint outside /app so the volume mount on /app cannot overwrite it
COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

# Set entrypoint to handle different service commands
ENTRYPOINT ["/entrypoint.sh"]
CMD ["serve"]