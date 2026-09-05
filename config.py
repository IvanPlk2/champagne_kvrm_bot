import os

SQLITE_DB_PATH = os.environ["SQLITE_PATH"]
API_KEY = os.environ["API_KEY"]
TEAM_CHAT_ID = os.environ["TEAM_CHAT_ID"]
ANOTHER_CHAT_ID = os.environ["ANOTHER_CHAT_ID"]
TEAM_NAME = os.environ["TEAM_NAME"]
TEAM_ID = int(os.environ["TEAM_ID"])
TEAM_LINK = f"https://rating.pecheny.me/teams/{TEAM_ID}"
