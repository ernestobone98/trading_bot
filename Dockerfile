# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Using --no-cache-dir to reduce image size
RUN python -m pip install --upgrade pip
RUN pip cache purge && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code to the working directory
COPY . .

# Ensure the trading_bot.log file can be written by the default user in the container
# This might be needed if your logging in trading_bot.py tries to create/write to this file
RUN touch trading_bot.log && chown $(whoami) trading_bot.log
# The above line might require a specific user setup if 'whoami' doesn't map to the expected user.
# A simpler approach if logging to stdout/stderr is preferred for containers:
# Consider configuring your bot's logging to output to stdout/stderr, 
# which is common practice for containerized applications. Docker can then handle log collection.

# Expose the port the app runs on (for metrics)
EXPOSE 8000

# Define the command to run your application
# This will execute trading_bot.py when the container launches
CMD ["python", "trading_bot.py"]
