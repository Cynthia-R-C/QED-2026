import solara
from mesa.visualization import SolaraViz, make_space_component, make_plot_component
from mesa.visualization.utils import update_counter
from beidouzhen import GridModel, EYE, ENEMY, ALPHA, BETA, GAMMA, DELTA

# color = what the agent did on its last turn
ACTION_COLORS = {'move': 'tab:blue', 'idle': 'tab:blue', 'attack': 'tab:red', 'defend': 'tab:green',
                 'support': 'tab:purple', 'escape': 'tab:cyan', 'recover': 'tab:gray'}

# graphics
def agent_portrayal(agent):
    '''Enemy = X; 阵眼 = star; other members = dots. Color = last action (red attack, green defend, purple chain support, cyan escape, gray recover).'''
    color = ACTION_COLORS.get(agent.last_action, 'tab:blue')

    if agent.type == 'enemy':
        return {'color': color, 'marker': 'X', 'size': 180}
    if agent.get_id() == EYE:
        return {'color': color, 'marker': '*', 'size': 150}
    return {'color': color, 'marker': 'o', 'size': 60}

# score card
@solara.component
def ScoreCard(model):
    '''Shows the result + score once someone wins or the sim times out'''
    update_counter.get()  # re-render every step

    if model.running:
        solara.Markdown(f'**Fighting...** round {model.steps}')
        return

    result = {'formation': 'Formation wins', 'enemy': 'Enemy wins', 'timeout': 'Timed out'}.get(model.winner, 'Stopped')
    solara.Markdown(f'## {result} at round {model.steps}\n### Score: {model.get_score():.2f}\n'
                    f'Enemy health: {model.enemy().get_health():.0f} / {model.enemy().get_max_health()}  \n'
                    f'Formation health: {sum(m.get_health() for m in model.members()):.0f} / {sum(m.get_max_health() for m in model.members())}')

# sliders
model_params = {
    'mode': {'type': 'Select', 'value': 'formation', 'values': ['formation', 'baseline'], 'label': 'Group (formation or baseline)'},
    'baseline_collisions': {'type': 'Checkbox', 'value': True, 'label': 'Baseline: members block each other'},
    'strategy': {'type': 'Select', 'value': 'none', 'values': ['none', 'weakest', 'eye'], 'label': 'Enemy strategy'},
    'close_in_override': {'type': 'Checkbox', 'value': False, 'label': 'Head/tail close-in overrides movement'},
    'full_speed': {'type': 'Checkbox', 'value': True, 'label': 'Members move at full speed'},
    'alpha': {'type': 'SliderFloat', 'value': ALPHA, 'label': 'alpha (encircle)', 'min': 0, 'max': 6, 'step': 0.1},
    'beta': {'type': 'SliderFloat', 'value': BETA, 'label': 'beta (shape)', 'min': 0, 'max': 6, 'step': 0.1},
    'gamma': {'type': 'SliderFloat', 'value': GAMMA, 'label': 'gamma (rotate, rad/tick)', 'min': 0, 'max': 6, 'step': 0.1},
    'delta': {'type': 'SliderFloat', 'value': DELTA, 'label': 'delta (close in)', 'min': 0, 'max': 6, 'step': 0.1},
    'center': {'type': 'Select', 'value': EYE, 'values': [EYE, ENEMY], 'label': 'Center (4 = eye, 8 = enemy)'},
}


class VizModel(GridModel):
    '''Same model; the dropdown can't hold None, so 'none' -> None'''
    def __init__(self, strategy='none', **kwargs):
        super().__init__(strategy=None if strategy == 'none' else strategy, **kwargs)


model = VizModel()

page = SolaraViz(
    model,
    components=[   # sliders + graph data
        make_space_component(agent_portrayal),
        make_plot_component(['Enemy health', 'Formation health']),
        # make_plot_component('Shape error'),
        # make_plot_component('Formation angle (deg)'),
        ScoreCard,   # result + score once the fight ends (last, so it doesn't push the graphs down)
    ],
    model_params=model_params,
    name='北斗阵 (Battle)',
    play_interval=1,
)

page  # solara run visual.py