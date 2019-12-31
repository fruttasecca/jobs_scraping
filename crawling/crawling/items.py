import json


# maps a country to its glassdoor id, used for starting a crawl
country_to_id = dict()

with open('country_to_id.json') as json_file:
    data = json.load(json_file)
    for d in data:
        country_to_id[d["country"].lower()] = d["ID"]
