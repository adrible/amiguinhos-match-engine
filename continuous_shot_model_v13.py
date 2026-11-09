"""Pure, runtime-standard-library model from the complete-league fit."""
import json,math
from pathlib import Path
MODEL=json.loads((Path(__file__).parent/'data/continuous_shot_model_v13.json').read_text())
def chance(frame,*,header=False,source='open_play',cross=None,through_ball=None):
    values={'intercept':1.,'distance':frame['distance'],'angle':frame['angle'],'header':float(header),
            'pressure':float(frame['pressure']),'cross':(source in {'cross','corner'}) if cross is None else cross,'through_ball':(source=='through_ball') if through_ball is None else through_ball,
            'rebound':source=='rebound','keeper_depth':frame.get('keeper_depth'),'keeper_lateral':frame.get('keeper_lateral'),
            'nearest_defender':frame.get('nearest_defender'),'keeper_missing':frame.get('keeper') is None}
    for key,value in MODEL['imputation'].items():
        if values[key] is None:values[key]=value
    z=sum(MODEL['coefficients'][key]*values[key] for key in MODEL['features'])
    return 1./(1.+math.exp(-max(-40.,min(40.,z))))
