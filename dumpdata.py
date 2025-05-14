# fix_encoding.py
with open("data.json", "r", encoding="utf-8-sig") as infile:
    data = infile.read()

with open("clean_data.json", "w", encoding="utf-8") as outfile:
    outfile.write(data)
