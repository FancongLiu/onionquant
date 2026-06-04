import json
import os

ext_path = os.path.expanduser(
    r"~\.vscode\extensions\github.copilot-chat-0.48.1\package.json"
)
with open(ext_path, "r", encoding="utf-8") as f:
    d = json.load(f)

props_list = d["contributes"]["configuration"]
for section in props_list:
    props = section.get("properties", {})
    for k, v in props.items():
        if any(
            x in k.lower()
            for x in ["nextedit", "editsuggest", "keep", "accept", "review", "confirm"]
        ):
            desc = v.get("description") or v.get("markdownDescription", "")
            default = v.get("default", "N/A")
            print(f"{k}")
            print(f"  default: {default}")
            print(f"  desc: {desc[:150]}")
            print()
