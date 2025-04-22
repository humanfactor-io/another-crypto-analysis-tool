# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the scripts into the container at /app
COPY *.py .
# Remove Flask-specific directory copies
# COPY templates/ /app/templates/
# COPY static/ /app/static/
# COPY crypto_data.db . # Keep commented out 

# Expose the default Streamlit port
EXPOSE 8501

# Remove Flask environment variables
# ENV FLASK_APP=app.py
# ENV FLASK_RUN_HOST=0.0.0.0 

# Set the command to run the Streamlit app
CMD ["streamlit", "run", "/app/data_viewer_app.py"]