# Use an official Python runtime as a parent image (Windows version)
FROM python:3.10-windowsservercore-ltsc2022

# Install Chocolatey and IrfanView automatically
SHELL ["powershell", "-Command", "$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue';"]
RUN Set-ExecutionPolicy Bypass -Scope Process -Force; \
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; \
    iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1')); \
    choco install irfanview64 -y

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Set environment variable for IrfanView inside container
# Default path for IrfanView 64-bit installed via Chocolatey
ENV IRFANVIEW_PATH="C:\Program Files\IrfanView\i_view64.exe"

# Copy IrfanView settings to the program directory
COPY IrfanViewSettings/i_view64.ini "C:/Program Files/IrfanView/i_view64.ini"

# Expose the port the app runs on
EXPOSE 8000

# Run the application
CMD ["python", "main.py"]
