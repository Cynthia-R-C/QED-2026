import mesa

# Starting info
ENEMY_STARTING_POS = (5, 5)
FORMATION_INIT_POS = {1: (4, 4), 2: (6, 0), 3: (2, -2), 4: (0, 0), 5: (-4, 0), 6: (-8, -1), 7: (-12, -4), 8: ENEMY_STARTING_POS}
EYE = 4       # id of the eye of the formation

# Initial lists
agent_list = []  # later will not be empty
agent_pos = {}

# Initial simulation logic
STRATEGY = None  # options: None, "weakest", "eye" - strategy for enemy cultivator
CENTER = EYE     # options: EYE (4) or 8 (enemy), center of formation

def update_pos_list(agent_list):
    '''Update the dict of current agent pos'''
    for agent in agent_list:
        id = agent.get_id()
        pos = agent.get_pos()
        agent_pos[id] = pos

class CultivatorAgent(mesa.Agent):
    '''An agent that represents a cultivator in a grid environment.'''
    def __init__(self, model, health=100, power=10, windup_time=1, strike_time=1, recovery_time=1, speed=2, attack_range=1, max_defense=10, type="formation", strategy=None):
        # Mesa 3.0 automatically assigns a unique_id if not provided
        super().__init__(model)

        # Stats
        self.health = health
        self.max_health = health
        self.power = power
        self.windup_time = windup_time
        self.strike_time = strike_time
        self.recovery_time = recovery_time
        self.speed = speed

        # Info
        self.type = type  # formation or enemy
        self.id = None  # is later assigned with set_id()
        self.position = None  # remains None until placed on the grid; tuple

        # Attack/defense
        self.attack_range = attack_range
        self.max_defense = max_defense  # the maximum amount of damage this cultivator can defend against (for formation agents they do the connection thing so this sums, but this is just for a single cultivator)

        # Use these to determine whether in windup or strike or neither
        self.attacking = False  # whether the agent is currently attacking
        self.windup_time_remaining = 0  # time left in windup phase

# ======= BASIC HELPERS ======= #

    def set_id(self, id):
        '''Assign a formation ID to the agent.'''
        self.id = id

    def initialize_position(self):
        '''Assign initial formation position; requires id to be set already'''
        self.position = FORMATION_INIT_POS[self.id]

    def get_id(self):
        return self.id

    def get_pos(self):
        return self.position

    def get_health(self):
        return self.health

    def get_max_health(self):
        return self.max_health

# ======= ATTACK/DEFENSE ======= #

    def attack(self):
        '''Attack the enemy if within range'''
        # This is a placeholder for the attack logic
        # Find all enemies within range
        # For enemy cultivator:
            # if no strategy, the pick a random cultivator
            # if strategy, pick the target cultivator if the target cultivator is in range, else pick a random cultivator
        # For formation cultivator: check if enemy is in range, if so, all formation cultivators should give their power to this cultivator and this cultivator should attack the enemy

        # For now, just print an attack message
        print(f"Agent {self.id} attacks the enemy at position {enemy_starting_pos} with power {self.power}")

    def defend(self, damage):  # model should call this and calculate the total aimed damage from all attackers
        '''Defend against incoming attacks'''
        # This is a placeholder for the defense logic
        damage = damage - self.max_defense  # reduce damage by max defense
        if damage > 0:
            self.health -= damage
            print(f"Agent {self.id} defends and takes {damage} damage, health now {self.health}")

    def escape(self):
        '''Escape from the range of hostile attack - should only be called if the agent actually able to move out of the range of attack
        Overrides all other movement logic, so should be called first in the step() method if the agent is being attacked'''
        # formation agent should move out of the range of the attack of the hostile entirely, and pick the point in its range of movement that minimizes its summed distance from the other formation members (so that they can still do the combo attack)

        # the enemy should try to move to the point in its movement range that is both out of the attack range and farthest from all formation agents

        # placeholder, for now just print an escape message
        print(f"Agent {self.id} escapes!")

# ======= MOVEMENT ======= #

    def step_new_pos(self, alpha, beta, gamma):
        '''Calculate the best new position for each member'''
        change = alpha * self.encircle(agent_pos[8]) + beta * self.shape()

        # I guess self.shape should be pretty weighty since when attacking the cultivators need to be within each other's ranges in order to do the combo attack

        # add logic about moore neighborhood and stuff: as in, make sure the member can only move in the moore neighborhood a distance of their speed, like if their speed is 1 they can only move to their direct moore neighborhood in 1 tick, or if thier speed is 2 they can only move 1 farther than their direct moore neighborhood; if the ideal change is outside their movememt range then keep the direction but shrink the magnitude until it is within the range; make helper functions for this if necessary

        # Before avoidance, set the new pos as self.pos so that avoidance function can call it to check and change if necessary

        # avoidance will just be make sure the new position isn't already occupied, if so randomly pick a spot in that position's moore neighborhood that isn't occupied, if that position's entire moore neighborhood is occupied pick a random position in a more outer circle, etc

    def encircle(self, target_pos):
        '''Calculate the best change in pos for each member to encircle the target'''
        # placeholder
        return (0,0)

    def shape(self):
        '''Calculate the best change in pos for each member to maintain formation shape'''
        # placeholder
        return (0,0)

    def rotate(self):
        '''Calculate the best change in pos for each member to rotate the formation with the eye/enemy as the center once the enemy is near the eye'''
        # placeholder
        return (0,0)

    def avoid(self, other_agents):
        '''Check whether self.pos already has another agent, if so move to unoccupied Moore neighborhood, if still all occupied move to more outer circle, etc.'''
        # placeholder
        return (0,0)
        
    def step(self):   # 
        '''Define the agent's behavior for a single clock step.'''
        # 1. Get neighboring coordinates (Moore neighborhood: includes diagonals)
        # modify this to be x speed in the moore neighborhood in each direction - that's how far they can move in 1 tick, they can choose any range within that accessible range
        possible_steps = self.model.grid.get_neighborhood(
            self.pos,
            moore=True,
            include_center=False
        )
        
        # 2. Select a random coordinate from the list
        new_position = self.random.choice(possible_steps)
        
        # 3. Move the agent to the new cell
        self.model.grid.move_agent(self, new_position)


class GridModel(mesa.Model):
    '''A baseline model managing a grid and a collection of wandering agents.'''
    def __init__(self, width=50, height=50, agents, seed=None):   # agents = list of agents with indices corresponding to id-1
        # Mesa 3.0 explicitly requires seed initializing the base class
        super().__init__(seed=seed)
        self.agents = agents
        self.steps = 0  # global step counter
        
        # Initialize a MultiGrid (allows multiple agents per cell)
        # Toroidal=True means the grid wraps around the edges like a donut
        self.grid = mesa.space.MultiGrid(width, height, torus=True)
        
        # Create and place agents on their initial grid coordinates
        for i in range(7):  # for formation cultivators
            agent = CultivatorAgent(self)  # default vals
            agent.set_id(i+1)  # id = 1-7
            agent.initialize_position()  # sets position based on id
            
            self.grid.place_agent(agent, agent.get_pos())

        # Create and place the enemy cultivator
        # self, model, health, power, windup_time, strike_time, recovery_time, speed, attack_range, type
        enemy_agent = CultivatorAgent(self, health=200, power=20, windup_time=0, strike_time=1, recovery_time=0, speed=3, attack_range=1, max_defense=20, type="enemy", strategy=STRATEGY)
        enemy_agent.set_id(8)  # id = 8 for enemy
        agent.initialize_position()  # sets position based on id

        self.grid.place_agent(enemy_agent, enemy_agent.get_pos())

    def get_score(self):
        '''Calculate the final score based on the health of the enemy and formation members.'''
        score = 0

        # If formation won
        if self.agents[8].get_health() <= 0:
            for id in range(7):  # for formation cultivators
                score += self.agents[id].get_health() / self.agents[id].get_max_health()  # normalize health

            score -= self.steps  # faster victory is better; look into normalizing this if the # of steps overshadows the health aspect of the score too much

        # If enemy won
        else: # score will be in negatives; relative value still matters because it tells us how badly we lost
            # loss condition = entire formation dead
            score -= self.agents[8].get_health() / self.agents[8].get_max_health()  # normalize health
            score += self.steps  # slower loss is better; look into normalizing this if the # of steps overshadows the health aspect of the score too much

        return score

    def step(self):
        '''Advance the simulation by one step.'''
        # Mesa 3.0 Scheduler replacement: 
        # Shuffles the agents container and calls their step() method
        self.agents.shuffle_do("step")


# --- Execution Example ---
if __name__ == "__main__":
    # Instantiate the model
    sim_model = GridModel(width=5, height=5, num_agents=5, seed=42)
    
    print("Initial Positions:")
    for agent in sim_model.agents:
        print(f"Agent {agent.unique_id}: {agent.pos}")
        
    # Advance the simulation by 3 steps
    for i in range(3):
        sim_model.step()
        print(f"\nPositions after Step {i+1}:")
        for agent in sim_model.agents:
            print(f"Agent {agent.unique_id}: {agent.pos}")
