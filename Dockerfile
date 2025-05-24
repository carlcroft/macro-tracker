FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the required packages
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# Copy the rest of the application code into the container

COPY . .

# copy your secrets file into the container
COPY .streamlit/secrets.toml .streamlit/secrets.toml

# Expose the port the app runs on
EXPOSE 8501

# Run the application
CMD ["streamlit", "run", "app.py"]