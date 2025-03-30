import db, os, toml

with open(os.path.join(".", "conf", "config.toml"), "r", encoding="utf8") as file:
    cfg = toml.loads(file.read())

cache = {}
adb = db.DB()