from mesa.visualization import SolaraViz, make_space_component
from walk_model import GridModel


def agent_portrayal(agent):
    '''How each agent is drawn.'''
    return {'color': 'tab:blue', 'marker': 'o', 'size': 40}


# sliders show up in the sidebar; changing one + hitting Reset rebuilds the model
model_params = {
    'width': 10,
    'height': 10,
    'num_agents': {'type': 'SliderInt', 'value': 15, 'label': 'Agents', 'min': 1, 'max': 50, 'step': 1},
    'seed': {'type': 'InputText', 'value': 42, 'label': 'Seed'},
}

# SolaraViz wants a model *instance*, not the class
model = GridModel(width=10, height=10, num_agents=15, seed=42)

page = SolaraViz(
    model,
    components=[make_space_component(agent_portrayal)],  # draws the grid + agents each step
    model_params=model_params,
    name='Baseline Grid Simulation',
)

page  # `solara run visual.py` serves this