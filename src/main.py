import toml, dotenv, os

if __name__ == "__main__":
    with open(os.path.join(".", "conf", "config.toml"), "r", encoding="utf8") as file:
        cfg = toml.loads(file.read())
    print(cfg)