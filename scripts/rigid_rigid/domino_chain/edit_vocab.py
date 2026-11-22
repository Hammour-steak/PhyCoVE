"""D01--D05 edit vocabulary using the existing PCVE single-edit DSL."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl
from simulate_domino_chain import BASELINE_PHYSICS,RENDER

# Display names say what a viewer sees (the row runs left to right from the tilted first domino);
# the D01--D05 ids stay internal and never reach a prompt.
_ORDINAL_ZH='一二三四五'
_ORDINAL_EN=['first','second','third','fourth','fifth']
OBJECTS={f'D{i+1:02}':{'zh':f'第{_ORDINAL_ZH[i]}块骨牌','en':f'the {_ORDINAL_EN[i]} domino'} for i in range(5)}
# domino_N aliases name the same objects as D0N.
OBJECTS.update({f'domino_{i+1}':OBJECTS[f'D{i+1:02}'] for i in range(5)})
PROPERTIES={'mass':dsl.PropertySpec('scalar','kg','质量','mass'),
            'friction':dsl.PropertySpec('scalar','','摩擦系数','friction coefficient'),
            'restitution':dsl.PropertySpec('scalar','','恢复系数','restitution')}
SIM_BINDINGS={(name,prop):dsl.SimBinding(key,index=i) for i in range(5) for name in [f'D{i+1:02}',f'domino_{i+1}']
              for prop,key in [('mass','domino_masses'),('friction','domino_frictions'),('restitution','domino_restitutions')]}
DELETE_BINDINGS={name:dsl.DeleteBinding('domino_active',index=i) for i in range(5) for name in [f'D{i+1:02}',f'domino_{i+1}']}
TOTAL_FRAMES=round(RENDER['fps']*RENDER['duration_sec'])
VOCAB=dsl.Vocabulary(objects=OBJECTS,properties=PROPERTIES,sim_bindings=SIM_BINDINGS,
                     delete_bindings=DELETE_BINDINGS,baseline_physics=BASELINE_PHYSICS,total_frames=TOTAL_FRAMES)
