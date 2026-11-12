from mesa.visualization import SolaraViz, make_space_component, make_plot_component
from beidouzhen import GridModel, EYE, ENEMY, ALPHA, BETA, GAMMA

# graphics
def agent_portrayal(agent):
    '''Enemy = red X; 阵眼 = star; other members = blue dots.'''
    if agent.type == 'enemy':
        return {'color': 'tab:red', 'marker': 'X', 'size': 150}
    if agent.get_id() == EYE:
        return {'color': 'tab:orange', 'marker': '*', 'size': 150}
    return {'color': 'tab:blue', 'marker': 'o', 'size': 60}

# sliders
model_params = {
    'alpha': {'type': 'SliderFloat', 'value': ALPHA, 'label': 'alpha (encircle)', 'min': 0, 'max': 3, 'step': 0.1},
    'beta': {'type': 'SliderFloat', 'value': BETA, 'label': 'beta (shape)', 'min': 0, 'max': 3, 'step': 0.1},
    'gamma': {'type': 'SliderFloat', 'value': GAMMA, 'label': 'gamma (rotate, rad/tick)', 'min': 0, 'max': 0.5, 'step': 0.01},
    'center': {'type': 'Select', 'value': EYE, 'values': [EYE, ENEMY], 'label': 'Center (4 = eye, 8 = enemy)'},
}

model = GridModel()

page = SolaraViz(
    model,
    components=[   # sliders + graph data
        make_space_component(agent_portrayal),
        make_plot_component('Shape error'),
        make_plot_component('Formation angle (deg)'),
    ],
    model_params=model_params,
    name='北斗阵 (Movement)',
)

page  # solara run visual.py