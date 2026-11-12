import math
import mesa

# Starting info
ENEMY_STARTING_POS = (5, 5)
FORMATION_INIT_POS = {1: (4, 4), 2: (6, 0), 3: (2, -2), 4: (0, 0), 5: (-4, 0), 6: (-8, -1), 7: (-12, -4), 8: ENEMY_STARTING_POS}
EYE = 4       # id of formation eye
# HEAD = 1  # 天枢 - no longer needed, facing is now a best-fit rotation of all members (formation_turn), not just eye->head
ENEMY = 8     # id of the enemy
GRID_OFFSET = (20, 25)  # FORMATION_INIT_POS has negative coords, so shift everything onto the grid

# Initial lists
agent_list = []  # later will not be empty; index = id - 1
agent_pos = {}   # id -> (x, y), snapshot taken at the start of each tick

# Initial simulation logic
STRATEGY = None  # options: None, 'weakest', 'eye' - strategy for enemy cultivator
CENTER = EYE     # options: EYE (4) or 8 (enemy), center of formation

# Movement weights: change = ALPHA * f_encircle + BETA * f_shape + GAMMA * f_rotate (tune later)
ALPHA = 1.5   # f_encircle is a unit vector, so ALPHA = cells/tick of pull toward the enemy
BETA = 0.5    # f_shape is the full vector to the ideal slot, so BETA = fraction of the gap closed per tick
GAMMA = 0.15  # f_rotate has magnitude r, so GAMMA ~ angular speed in rad/tick (0.15 rad ~ 8.6 deg)
ROTATE_TRIGGER = 3  # rotation kicks in once the enemy is within this many cells (Chebyshev) of the eye


def update_pos_list(agent_list):
    '''Update the dict of current agent pos'''
    for agent in agent_list:
        id = agent.get_id()
        pos = agent.get_pos()
        agent_pos[id] = pos


def chebyshev(a, b):
    '''Moore-neighborhood distance'''
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def rotate_vec(v, angle):
    '''Rotate a 2D vector counterclockwise by angle (rad)'''
    c, s = math.cos(angle), math.sin(angle)
    return (c * v[0] - s * v[1], s * v[0] + c * v[1])


def formation_turn():  # used in ideal_pos
    '''Best-fit rotation angle (rad) of the formation about the eye vs. its starting layout. 
    For each member, u = starting offset from eye, v = current offset from eye; the angle that best lines up all u's with all v's is atan2(sum(u x v), sum(u dot v)).'''

    init_eye, eye = FORMATION_INIT_POS[EYE], agent_pos[EYE]
    cross = 0
    dot = 0

    for i in range(1, 8):
        if i == EYE or i not in agent_pos:
            continue

        u = (FORMATION_INIT_POS[i][0] - init_eye[0], FORMATION_INIT_POS[i][1] - init_eye[1])
        v = (agent_pos[i][0] - eye[0], agent_pos[i][1] - eye[1])

        cross += u[0] * v[1] - u[1] * v[0]
        dot += u[0] * v[0] + u[1] * v[1]
    
    return math.atan2(cross, dot)


# centroid of the 7 members' starting positions (used when the formation is centered on the enemy)
FORMATION_CENTROID = (sum(FORMATION_INIT_POS[i][0] for i in range(1, 8)) / 7, sum(FORMATION_INIT_POS[i][1] for i in range(1, 8)) / 7)


class CultivatorAgent(mesa.Agent):
    '''An agent that represents a cultivator in a grid environment.'''
    
    def __init__(self, model, health=100, power=10, windup_time=1, strike_time=1, recovery_time=1, speed=2, attack_range=1, max_defense=10, type='formation', strategy=None):
        # Mesa 3.0 automatically assigns a unique_id if not provided
        super().__init__(model)

        # Stats
        self.health = health
        self.max_health = health
        self.power = power
        self.windup_time = windup_time
        self.strike_time = strike_time
        self.recovery_time = recovery_time
        self.speed = speed  # max cells per tick in any direction (Moore radius)

        # Info
        self.type = type  # formation or enemy
        self.strategy = strategy
        self.id = None  # is later assigned with set_id()
        self.position = None  # remains None until placed on the grid; tuple (kept in sync with Mesa's self.pos)
        self.exact_pos = None  # un-rounded position: keeps the sub-cell leftover so slow moves (< half a cell/tick) still add up

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
        x, y = FORMATION_INIT_POS[self.id]
        self.position = (x + GRID_OFFSET[0], y + GRID_OFFSET[1])
        self.exact_pos = self.position

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
        print(f'Agent {self.id} attacks the enemy at position {agent_pos[ENEMY]} with power {self.power}')

    def defend(self, damage):  # model should call this and calculate the total aimed damage from all attackers
        '''Defend against incoming attacks'''
        # This is a placeholder for the defense logic
        damage = damage - self.max_defense  # reduce damage by max defense
        if damage > 0:
            self.health -= damage
            print(f'Agent {self.id} defends and takes {damage} damage, health now {self.health}')

    def escape(self):
        '''Escape from the range of hostile attack - should only be called if the agent actually able to move out of the range of attack
        Overrides all other movement logic, so should be called first in the step() method if the agent is being attacked'''
        # formation agent should move out of the range of the attack of the hostile entirely, and pick the point in its range of movement that minimizes its summed distance from the other formation members (so that they can still do the combo attack)

        # the enemy should try to move to the point in its movement range that is both out of the attack range and farthest from all formation agents

        # placeholder, for now just print an escape message
        print(f'Agent {self.id} escapes!')

# ======= MOVEMENT ======= #

    def step_new_pos(self, alpha, beta, gamma):
        '''Calculate the best new position for each member'''
        e = self.encircle(agent_pos[ENEMY])
        s = self.shape()
        r = self.rotate()
        change = (alpha * e[0] + beta * s[0] + gamma * r[0], alpha * e[1] + beta * s[1] + gamma * r[1])

        # I guess self.shape should be pretty weighty since when attacking the cultivators need to be within each other's ranges in order to do the combo attack

        # Keep direction, shrink magnitude until it's within the Chevyshev range of speed
        change = self.clamp_to_speed(change)

        # Move the exact (float) position, then snap to the nearest grid cell (keep on the grid)
        w, h = self.model.grid.width, self.model.grid.height
        ex = min(max(self.exact_pos[0] + change[0], 0), w - 1)
        ey = min(max(self.exact_pos[1] + change[1], 0), h - 1)
        new_pos = (round(ex), round(ey))

        # Avoidance: if that cell's taken, find the nearest free one we can still reach
        final = self.avoid(new_pos)

        if final == new_pos:
            self.exact_pos = (ex, ey)
        else:
            self.exact_pos = final
         
        return final

    def clamp_to_speed(self, change):
        '''Shrink the change vector (same direction) so it fits within speed cells of Moore distance'''

        biggest = max(abs(change[0]), abs(change[1]))  # Moore distance of the move

        if biggest <= self.speed:
            return change
        k = self.speed / biggest

        return (change[0] * k, change[1] * k)

    def encircle(self, target_pos):
        '''f_encircle: unit vector toward the target (constant-strength pull, so alpha is in cells/tick)'''

        dx, dy = target_pos[0] - self.pos[0], target_pos[1] - self.pos[1]
        d = math.hypot(dx, dy)

        return (dx / d, dy / d) if d > 0 else (0, 0)

    def shape(self):
        '''f_shape: vector from where I am to my ideal slot (spring: bigger gap = bigger pull)'''

        ideal = self.ideal_pos()
        return (ideal[0] - self.pos[0], ideal[1] - self.pos[1])

    def ideal_pos(self):
        '''Where this member should be to keep the formation shape, given where the center is and which way the formation faces'''

        init_eye, eye = FORMATION_INIT_POS[EYE], agent_pos[EYE]
        phi = formation_turn()  # how far the whole formation has turned since the start
        mine = FORMATION_INIT_POS[self.id]

        if self.model.center == EYE:  # shape built around the eye's current spot
            center, ref = eye, init_eye
        
        else:  # shape built around the enemy (enemy sits at the formation's centroid)
            center, ref = agent_pos[ENEMY], FORMATION_CENTROID
        
        off = rotate_vec((mine[0] - ref[0], mine[1] - ref[1]), phi)
        
        return (center[0] + off[0], center[1] + off[1])

    def rotate(self):
        '''f_rotate: tangent vector around the center (|f| = r, like rigid rotation v = omega * r), only once the enemy is near the eye'''

        if chebyshev(agent_pos[ENEMY], agent_pos[EYE]) > ROTATE_TRIGGER:  # if enemy is outside rotating range
            return (0, 0)

        if self.model.center == EYE:
            center = agent_pos[EYE]
        else:
            center = agent_pos[ENEMY] 
        
        rx, ry = self.pos[0] - center[0], self.pos[1] - center[1]  # dist from center

        return (-ry, rx)  # (rx, ry) turned 90 dg counterclockwise; tangent vector around center

    def avoid(self, new_pos):
        '''Check whether new_pos already has another agent, if so move to unoccupied Moore neighborhood, if still all occupied move to more outer circle, etc.'''
        grid = self.model.grid

        def free(cell):
            return cell == self.pos or grid.is_cell_empty(cell)

        if free(new_pos):  # if free it's fine
            return new_pos
        
        for radius in range(1, 2 * self.speed + 2):  # rings around new_pos, nearest first

            ring = [c for c in grid.get_neighborhood(new_pos, moore=True, include_center=False, radius=radius) if chebyshev(c, new_pos) == radius]  # ring = list of positions
            options = [c for c in ring if free(c) and chebyshev(c, self.pos) <= self.speed]  # must still be reachable this tick

            if options:   # pick random one from options if it exists
                return self.random.choice(options)
        
        return self.pos  # boxed in: stay put this tick

# ======= UPDATE PER TICK ======= #

    def step(self):
        '''Define the agent's behavior for a single clock step.'''
        if self.type == 'enemy':
            return  # enemy holds still for now -- movement comes with the attack/escape logic

        # possible_steps = self.model.grid.get_neighborhood(self.pos, moore=True, include_center=False)  # old random walk, replaced by step_new_pos
        # new_position = self.random.choice(possible_steps)
        new_position = self.step_new_pos(self.model.alpha, self.model.beta, self.model.gamma)

        self.model.grid.move_agent(self, new_position)
        self.position = new_position


class GridModel(mesa.Model):
    '''The grid model for modeling formation and enemy movements / battle.'''
    def __init__(self, width=50, height=50, alpha=ALPHA, beta=BETA, gamma=GAMMA, center=CENTER, seed=None):
        # Mesa 3.0 explicitly requires seed initializing the base class
        super().__init__(seed=seed)
        # self.agents = agents  # Mesa already owns model.agents (read-only), so the list lives in agent_list and don't need this
        self.steps = 0  # global step counter
        self.alpha, self.beta, self.gamma = alpha, beta, gamma
        self.center = center

        # fresh globals for every new model (e.g. hitting Reset in the visualization)
        agent_list.clear()
        agent_pos.clear()

        # Initialize a MultiGrid (allows multiple agents per cell)
        # self.grid = mesa.space.MultiGrid(width, height, torus=True)  # torus off: wrapping splits the formation across edges and breaks the shape/rotation vectors
        self.grid = mesa.space.MultiGrid(width, height, torus=False)

        # Create and place agents on their initial grid coordinates
        for i in range(7):  # for formation cultivators
            agent = CultivatorAgent(self)  # default vals
            agent.set_id(i + 1)  # id = 1-7
            agent.initialize_position()  # sets position based on id
            self.grid.place_agent(agent, agent.get_pos())
            agent_list.append(agent)

        # Create and place the enemy cultivator
        # self, model, health, power, windup_time, strike_time, recovery_time, speed, attack_range, type
        enemy_agent = CultivatorAgent(self, health=200, power=20, windup_time=0, strike_time=1, recovery_time=0, speed=3, attack_range=1, max_defense=20, type='enemy', strategy=STRATEGY)
        enemy_agent.set_id(ENEMY)  # id = 8 for enemy
        # agent.initialize_position()  # bug: this re-initialized the last formation agent instead of the enemy
        enemy_agent.initialize_position()  # sets position based on id
        self.grid.place_agent(enemy_agent, enemy_agent.get_pos())
        agent_list.append(enemy_agent)

        # Update for start
        # The data collector lambda m thing is a standard Mesa initialization method
        update_pos_list(agent_list)
        self.datacollector = mesa.DataCollector(model_reporters={'Shape error': lambda m: m.shape_error(), 'Formation angle (deg)': lambda m: m.formation_angle(), 'Eye-enemy dist': lambda m: chebyshev(agent_pos[EYE], agent_pos[ENEMY])})
        self.datacollector.collect(self)

    def shape_error(self):
        '''Avg distance (cells) between each member and its ideal slot, 0 = perfect formation'''
        return sum(math.dist(a.get_pos(), a.ideal_pos()) for a in agent_list[:7]) / 7

    def formation_angle(self):
        '''How far the formation has turned since start (deg)'''
        return math.degrees(formation_turn())

    def get_score(self):
        '''Calculate the final score based on the health of the enemy and formation members.'''
        score = 0
        enemy = agent_list[ENEMY - 1]

        # If formation won
        if enemy.get_health() <= 0:
            for id in range(7):  # for formation cultivators
                score += agent_list[id].get_health() / agent_list[id].get_max_health()  # normalize health

            score -= self.steps  # faster victory is better; look into normalizing this if the # of steps overshadows the health aspect of the score too much

        # If enemy won
        else: # score will be in negatives; relative value still matters because it tells us how badly we lost
            # loss condition = entire formation dead
            score -= enemy.get_health() / enemy.get_max_health()  # normalize health
            score += self.steps  # slower loss is better; look into normalizing this if the # of steps overshadows the health aspect of the score too much

        return score

    def step(self):
        '''Advance the simulation by one step.'''
        # everyone's forces are computed from the positions at the START of the tick (snapshot),
        # but occupancy is checked live, so agents moving later in the tick dodge the ones that already moved
        update_pos_list(agent_list)

        # self.agents.shuffle_do('step')  # replaced: fixed order so the eye claims its cell first (later: attacked agent goes first)
        order = [agent_list[EYE - 1]] + [a for a in agent_list if a.get_id() != EYE]
        for agent in order:
            agent.step()

        update_pos_list(agent_list)
        self.datacollector.collect(self)


# ======= EXECUTION ======= #
if __name__ == '__main__':
    sim_model = GridModel(seed=42)

    print('Initial Positions:')
    for agent in agent_list:
        print(f'Agent {agent.get_id()}: {agent.get_pos()}')

    for i in range(30):
        sim_model.step()
        print(f'Step {i + 1}: shape error {sim_model.shape_error():.2f}, angle {sim_model.formation_angle():.0f} deg, eye-enemy {chebyshev(agent_pos[EYE], agent_pos[ENEMY])}')