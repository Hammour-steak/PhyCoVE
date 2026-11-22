"""Measure attachment/body rocking independently of the render and shader."""
import numpy as np

def rocking_metrics(result):
    ts=result['trajectory_samples'];t=np.array([s['time_sec'] for s in ts])
    events=[e['time_sec'] for e in result['contact_events'] if e['kind']=='ball_ball']
    metrics={}
    for name in ts[0]['objects']:
        b=[s['objects'][name] for s in ts]
        if not b[0]['rope']['present']:continue
        p=np.array([s['location'] for s in b]);end=np.array([s['rope']['attachment_world_m'] for s in b])
        up=np.array([s['rope']['anchor_m'] for s in b])-end;arm=end-p
        cosine=np.sum(arm*up,axis=1)/(np.linalg.norm(arm,axis=1)*np.linalg.norm(up,axis=1))
        angle=np.degrees(np.arccos(np.clip(cosine,-1,1)))
        post=t>events[0] if events else np.ones(len(t),dtype=bool)
        tails=[];turns=[]
        for lo,hi in zip(events,events[1:]+[result['configuration']['render']['duration_sec']]):
            sel=(t>lo+.15)&(t<hi-.02)
            if sel.any():tails.append(float(np.max(angle[sel])))
            ix=np.where((t>lo+.01)&(t<hi-.01))[0]
            turns.append([float(t[k]) for k in ix[1:] if b[k-1]['linear_velocity'][0]*b[k]['linear_velocity'][0]<0])
        metrics[name]={'max_relative_body_cord_angle_deg':float(np.max(angle[post])),
            'max_relative_angle_after_150ms_deg':max(tails) if tails else float(np.max(angle)),
            'per_flight_max_after_150ms_deg':tails,'inter_contact_horizontal_turn_times_sec':turns,
            'signed_planar_relative_angle_deg':(np.degrees(np.unwrap(np.arctan2(arm[:,0],arm[:,2]))-np.unwrap(np.arctan2(up[:,0],up[:,2])))).tolist()}
    return metrics
