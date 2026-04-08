import json

input_path = "full_translation.json"
output_path = "full_translation_fixed.json"

with open(input_path, "r", encoding="utf-8") as f:
    data = json.load(f)

for img in data.get("images", []):
    new_nodes = {}
    for k, v in img.get("nodes", {}).items():
        fixed_key = k.replace(" ", "_")  # 핵심
        new_nodes[fixed_key] = v
    img["nodes"] = new_nodes

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("done")