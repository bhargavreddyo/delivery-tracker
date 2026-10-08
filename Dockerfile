#Uses a lightweight Python 3.12 base image
FROM python:3.12-slim

#Sets /app as the working directory inside the container
WORKDIR /app

# Prevents Python from creating .pyc files
ENV PYTHONDONTWRITEBYTECODE=1


# Makes Python output appear immediately in Docker logs
ENV PYTHONUNBUFFERED=1


#Copies requirements.txt from my project into /app inside the container
COPY requirements.txt .

#Installs all python dependencies listed in requirements.txt
#no cache dir prevents pip from storing its package cache, keeping the image smaller
RUN python -m pip instal --no-cache-dir -r requirements.txt

#Copies the local /app directory inti /app/app inside the container
COPY app ./app

#Creates a non-root user named appuser inside the container
RUN useradd --create-home appuser

#Runs the application as appuser instead of the root user
USER appuser

#Documents that the FastAPI application listens on port 8080
EXPOSE 8080

#Starts the FastAPI application using Uvicorn on port 8080
CMD ["uvicorn" , "app.main:app" , "--host" , "0.0.0.0" , "--port" , "8080"]