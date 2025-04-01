import db, os, toml, ZODB

with open(os.path.join(".", "assets", "config.toml"), "r", encoding="utf8") as file:
    cfg = toml.loads(file.read())

db = ZODB.DB("./assets/db.db")