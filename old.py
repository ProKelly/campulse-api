import json

with open("serviceAccountKey.json") as f:
    creds = json.load(f)

print(json.dumps(creds))  # copy the full output
