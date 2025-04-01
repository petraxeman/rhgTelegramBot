import re



def model_decode(string: str):
    variants_map = {
        "1.0": "gemini-1.5-flash",
        "2.0": "gemini-2.0-flash",
        "2.5": "gemini-2.5-pro-exp-03-25"
    }
    
    return variants_map.get(string, "gemini-2.0-flash")


def str_to_bool(string: str, default: bool = False):
    variants_map = {
        True: ["y", "yes", "true", "t", "да"],
        False: ["n", "no", "false", "f", "нет"]
    }
    
    for key, values in variants_map.items():
        if string.lower() in values:
            return key
    
    return default


def parse_ask_msg(text: str, tg_bot_name: str, hr_bot_name):
    regex = f"(?P<full_command>{tg_bot_name}\/?(?P<flags>[fsdn012]+)?(?P<direction>=?[+-]\d*)?)"
    match = re.match(regex, text)
    
    flags = ""
    direction = ""
    clear_msg = text
    if match:
        flags = match.group("flags")
        direction = match.group("direction")
        clear_msg = text.replace(match.group("full_command"), hr_bot_name)
    
    flags = set(flags) if flags else set()
    direction = parse_direction(direction) if direction else {}
    return flags, direction, clear_msg


def parse_direction(direction: str):
    data = {"strict": False}
    match = re.match(r"(?P<exact>=)?(?P<vec>[+-l])(?P<count>\d+)?", direction)
    if match.group("exact"):
        data["strict"] = True
    
    if match.group("vec") == "+":
        data["vector"] = 1
    else:
        data["vector"] = -1
    
    try:
        data["count"] = int(match.group("count"))
    except:
        data["count"] = 10
    
    return data