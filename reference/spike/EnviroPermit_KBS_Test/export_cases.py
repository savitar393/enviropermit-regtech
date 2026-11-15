import copy
import json
from pathlib import Path
from enviro import assess
from test_enviro import BASE

variants = [
    ('A', {}),
    ('B', {'impact_extent':[False]}),
    ('U', {'impact_extent':[]}),
    ('M', {'project_changes':['ManagementMonitoringChange'],
           'water_change':'WastewaterManagementChange', 'impact_extent':[False]}),
    ('I', {'project_changes':['IdentityChange'], 'water_change':None, 'impact_extent':[]}),
    ('X', {'project_changes':['IdentityChange','CapacityIncrease']}),
    ('D', {'screening':'AMDAL'}),
    ('C', {'impact_extent':[True,False]}),
]
results = {}
inputs = {}
for name, update in variants:
    data = copy.deepcopy(BASE)
    data.update(update)
    data['id'] = name
    inputs[name] = data
    results[name] = assess(data, 'outputs')
Path('cases.json').write_text(json.dumps(inputs,indent=2)+'\n')
Path('outputs/results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({k:{'status':v['status'], 'obligations':v['obligations'],
                     'precedence':v['precedence'], 'evidence_gaps':v['evidence_gaps']}
                  for k,v in results.items()},indent=2))
