FROM python:3.11-slim

ENV DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl unzip ca-certificates fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN URL=$(curl -s https://api.github.com/repos/lay295/TwitchDownloader/releases/latest \
    | grep browser_download_url | grep 'TwitchDownloaderCLI' | grep 'Linux-x64' \
    | head -1 | cut -d '"' -f 4) \
    && curl -L -o /tmp/tdl.zip "$URL" \
    && unzip /tmp/tdl.zip -d /usr/local/bin \
    && chmod +x /usr/local/bin/TwitchDownloaderCLI \
    && rm /tmp/tdl.zip

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["python", "bot.py"]
