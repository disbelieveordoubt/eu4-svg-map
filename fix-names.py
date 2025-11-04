import json
import difflib

with open('paste.txt', 'r', encoding='utf-8') as f:
    svg_names = sorted(set(line.strip().split(' (#')[0] for line in f if ' (#' in line))

with open('territory_colors.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

for territory, data in config.items():
    for prov in data['provinces']:
        if prov not in svg_names:
            matches = difflib.get_close_matches(prov, svg_names, n=5, cutoff=0.6)
            if matches:
                match_list = ', '.join(matches)
            else:
                match_list = '—'
            print(f"{territory:25} | {prov:20} -> {match_list}")