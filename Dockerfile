
# Use a specific, lightweight Python image
FROM python:3.12.7-slim-bookworm

# Set the working directory inside the container
WORKDIR /app

# Prevent Python cache files and display logs immediately
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy the list of Python dependencies
COPY requirements.txt .

# Install the required Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and database migrations
COPY app/ ./app/
COPY migrations/ ./migrations/

# Create a normal, non-root user
RUN useradd --create-home appuser

# Run the application as the non-root user
USER appuser

# Document the port used by the application
EXPOSE 8080

# Start the FastAPI application using Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
