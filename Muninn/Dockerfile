FROM python:3

# Install discord.py library
RUN pip install discord.py
RUN pip install requests
RUN pip install pillow
RUN pip install fuzzywuzzy
RUN pip install matplotlib
RUN python -m pip install seaborn
RUN pip install psycopg2
RUN pip install regex
RUN pip install icecream
RUN pip install PyYAML

# Create the directory for the bot and set it as the working directory
WORKDIR /usr/src/bot

# Command to run the bot
CMD ["python3", "-u", "index.py"]