FROM python:3

# Install discord.py library
RUN pip install discord.py
RUN pip install pillow
RUN pip install requests
RUN pip install pytz
RUN pip install pyyaml

# Create the directory for the bot and set it as the working directory
WORKDIR /usr/src/bot

# Command to run the bot
CMD ["python3", "-u", "index.py"]