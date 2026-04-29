import json, uuid
from datetime import datetime, timezone

with open('backend/data/journal/journal.json', encoding='utf-8') as f:
    journal = json.load(f)

with open('data/discovery/discoveries_adjacent.json', encoding='utf-8') as f:
    disc = json.load(f)

discoveries = disc.get('discoveries', [])

added = 0
for d in discoveries:
    entry = {
        'id': str(uuid.uuid4()),
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'type': 'probe_discovery',
        'coordinates_2d': [0.0, 0.0],
        'coordinates_highD': None,
        'desert_value': d.get('desert_max', 0.0),
        'nearest_concepts': [
            {'term': c.get('term',''), 'distance': c.get('distance',0.0),
             'roget_categories': None, 'roget_class': c.get('class_name')}
            for c in d.get('deepest_step',{}).get('nearest_concepts',[])[:5]
        ],
        'roget_context': None,
        'generated_description': None,
        'user_notes': d.get('term_a','') + ' vs ' + d.get('term_b',''),
        'fabrication_notes': {'material':'','method':'','dimensions':'','status':'idea','photos':[]},
        'tags': ['adjacent_cat'],
        'starred': False,
        'v1_source': None,
        'schema_version': 1
    }
    journal.append(entry)
    added += 1

with open('backend/data/journal/journal.json', 'w', encoding='utf-8') as f:
    json.dump(journal, f, indent=2, ensure_ascii=False)

print('Added', added, 'entries. Total:', len(journal))
