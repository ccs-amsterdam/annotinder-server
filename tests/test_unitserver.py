import math
from typing import List
from tests.conftest import client

def create_job(title: str, rules: dict, with_jobsets: bool, n: int = 10) -> dict:
    job = {"title": title}
    job['codebook'] = dict(type='questions', questions=[dict(name='dummy', type='confirm')])
    job['units'] = [dict(id=str(i), unit={"external_id": i}) for i in range(0,n)]
    job['rules'] = rules
    if with_jobsets: 
        job['jobsets'] = [dict(name=1, ids = [str(i) for i in range(0, math.floor(0.5*n))]),
                          dict(name=2, ids = [str(i) for i in range(math.floor(0.5*n),n)])
                          ]
    return job


def simulate_coding(admin, coders,  rules, n_units=10, units_per_coder=3, with_jobsets=False):
    job = create_job('test', rules, with_jobsets, n_units)
    res = client.post("/codingjob", json=job, headers=admin['headers'])
    assert res.status_code == 201, res.text   
    job_id = res.json()['id']

    ncoded = 0
    for i, coder in enumerate(coders):
        # progress = client.get(f"/codingjob/{job_id}/progress", headers=coder['headers']).json()
        for j in range(0,units_per_coder):
            unit = client.get(f'codingjob/{job_id}/unit', headers=coder['headers']).json()
            if not 'id' in unit:
                yield ncoded, i, None
            else:
                annotation=[dict(variable='dummy', value='confirmed', coder=coder['user'].name)]
                body = dict(annotation=annotation, status='DONE')
                res = client.post(f"/codingjob/{job_id}/unit/{unit['id']}/annotation", json=body, headers=coder['headers'])
                assert res.status_code == 200
                yield ncoded, i, unit['unit']['external_id']
            ncoded += 1

def test_crowd_coding(admin, coders):
    rules = dict(ruleset = 'crowdcoding', crowd_priority='coders_per_unit')
    for i, coder, unit in simulate_coding(admin, coders,  rules, 5, 3):
        ## in coders_per_unit mode, each coder should do the same first three units
        #print(f"i: {i}\tcoder: {coder}\tunit:{unit}")
        assert unit == i % 3  

    rules = dict(ruleset = 'crowdcoding', crowd_priority='many_units')
    for i, coder, unit in simulate_coding(admin, coders,  rules, 5, 3):
        ## in many_units mode, the next coder continues from the next unit, 
        ## giving cycles of five (nr of units)
        #print(f"i: {i}\tcoder: {coder}\tunit:{unit}")
        assert unit == i % 5
    
    
def test_fixed_set(admin, coders):
    rules = dict(ruleset = 'fixedset')
    
    for i, coder, unit in simulate_coding(admin, coders,  rules, 10, 3):
        ## each coder starts the fixed set.
        #print(f"i: {i}\tcoder: {coder}\tunit:{unit}")
        assert unit == i % 3  
        
    # With multiple sets. first coder starts first set, 
    # then second coder starts second set,
    # then third coder starts first set again
    order = [0,1,2,5,6,7,0,1,2]
    for i, coder, unit in simulate_coding(admin, coders,  rules, 10, 3, True):
        ## in coders_per_unit mode, each coder should do the same first three units
        #print(f"i: {i}\tcoder: {coder}\tunit:{unit}")
        assert unit == order[i]  

    
