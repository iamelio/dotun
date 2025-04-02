# dotun ✨

a telegram bot for renaming files.

## features

- file processing capabilities
- docker support
- configurable through environment variables or config file
- modular handler system

## setup

1. clone the repository
2. create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # on unix/macos
   ```
3. install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. configure the bot:
   - copy `config.ini.template` to `config.ini`
   - fill in your telegram api credentials
   - or set environment variables:
     - `API_ID`
     - `API_HASH`
     - `BOT_TOKEN`
     - `SESSION_NAME` (optional)

## running the bot

### locally

```bash
python main.py
```

### with docker

```bash
docker build -t dotun-bot .
docker run -d --name dotun-bot dotun-bot
```

## license

this project is licensed under the mit license - see the [license](license) file for details.
