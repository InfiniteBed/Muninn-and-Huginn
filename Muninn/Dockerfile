FROM python:3

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install discord.py library
RUN pip install --upgrade --force-reinstall git+https://github.com/Rapptz/discord.py.git
RUN pip install watchdog
RUN pip install -U discord-py-interactions
RUN pip install requests
RUN pip install pillow
RUN pip install fuzzywuzzy
RUN pip install matplotlib
RUN python -m pip install seaborn
RUN pip install psycopg2
RUN pip install regex
RUN pip install ollama
RUN pip install pyyaml
RUN pip install mplcairo
RUN pip install yt-dlp
RUN pip install PyNaCl
RUN pip install icecream
RUN pip install aiohttp
RUN pip install postgresql

# Create the directory for the bot and set it as the working directory
WORKDIR /usr/src/bot

# Command to run the bot
CMD ["python3", "-u", "index.py"]