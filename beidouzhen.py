import math
import mesa

# ======= INTIAL PARAMETERS ======= #

# Starting info
ENEMY_STARTING_POS = (10, -5)
FORMATION_INIT_POS = {1: (14, 9), 2: (16, 5), 3: (12, 3), 4: (10, 5), 5: (6, 5), 6: (2, 4), 7: (-2, 1), 8: ENEMY_STARTING_POS}
EYE = 4       # id of formation eye
# HEAD = 1  # 天枢 - no longer needed, facing is now a best-fit rotation of all members (formation_turn), not just eye->head
ENEMY = 8     # id of the enemy
GRID_OFFSET = (20, 25)  # FORMATION_INIT_POS has negative coords, so shift everything onto the grid

# Sections of the formation for attack/defense (edit if splitting differently)
HEAD_IDS = {1, 2, 3}    # spoon
MIDDLE_IDS = {4}        # 天权
TAIL_IDS = {5, 6, 7}    # handle

# Initial lists
agent_list = []  # later will not be empty; index = id - 1
agent_pos = {}   # id -> (x, y), updated live as each agent moves (so later movers see who already moved)

# Initial simulation logic
STRATEGY = None  # options: None, 'weakest', 'eye' - strategy for enemy cultivator
CENTER = EYE     # options: EYE (4) or 8 (enemy), center of formation
CLOSE_IN_OVERRIDE = False  # True: when the middle is attacked, head/tail drop the movement equation and charge the enemy; False: close-in stays in the movement equation as the delta term
MAX_TICKS = 300  # stop the fight after this many rounds (round = formation turn + enemy turn)

# Movement weights: change = ALPHA * f_encircle + BETA * f_shape + GAMMA * f_rotate (tune later)
ALPHA = 3.0   # f_encircle is a unit vector, so ALPHA = cells/tick of pull toward the enemy
BETA = 1.0    # f_shape is the full vector to the ideal slot, so BETA = fraction of the gap closed per tick
GAMMA = 0.3  # f_rotate has magnitude r, so GAMMA ~ angular speed in rad/tick (0.15 rad ~ 8.6 deg)
DELTA = 3.0   # f_close_in is the full vector to the ideal slot, so DELTA = fraction of the gap closed per tick; only used when the middle is attacked
ROTATE_TRIGGER = 6  # rotation kicks in once the enemy is within this many cells (Chebyshev) of the eye

# ======= STATS ======= #

# Formation members
QZ_HEALTH = 50
QZ_POWER = 10
QZ_WINDUP = 1
QZ_STRIKE = 1
QZ_RECOVERY = 2
QZ_SPEED = 4
QZ_ATT_RANGE = 5
QZ_MAX_DEF = 10

# Enemy
E_HEALTH = 100
E_POWER = 37.5
E_WINDUP = 0
E_STRIKE = 1
E_RECOVERY = 0
E_SPEED = 12
E_ATT_RANGE = 2
E_MAX_DEF = 40


# ======= GENERAL HELPERS ======= #

def update_pos_list(agent_list):
    '''Update the dict of current agent pos'''
    agent_pos.clear()  # so dead agents drop out

    for agent in agent_list:
        if not agent.is_alive():
            continue
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


def pivot_id():
    '''Member the formation pivots on: the eye, or the lowest-id living member once the eye is dead'''
    if EYE in agent_pos:
        return EYE

    alive = [i for i in range(1, 8) if i in agent_pos]
    return min(alive) if alive else None


def formation_turn():  # used in ideal_pos
    '''Best-fit rotation angle (rad) of the formation about the eye vs. its starting layout.
    For each member, u = starting offset from eye, v = current offset from eye; the angle that best lines up all u's with all v's is atan2(sum(u x v), sum(u dot v)).'''

    p = pivot_id()  # the eye, unless it's dead
    if p is None:
        return 0.0

    # init_eye, eye = FORMATION_INIT_POS[EYE], agent_pos[EYE]  # replaced by the pivot so this still works after the eye dies
    init_eye, eye = FORMATION_INIT_POS[p], agent_pos[p]
    cross = 0
    dot = 0

    for i in range(1, 8):
        if i == p or i not in agent_pos:
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

    def __init__(self, model, health=100, power=10, windup_time=1, strike_time=1, recovery_time=1, speed=2, attack_range=2, max_defense=10, type='formation', strategy=None):
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
        self.strategy = strategy
        self.id = None  # is later assigned with set_id()
        self.position = None  # remains None until placed on the grid; tuple (kept in sync with Mesa's self.pos)
        self.exact_pos = None  # un-rounded position: keeps the sub-cell leftover so slow moves (< half a cell/tick) still add up

        # Attack/defense
        self.attack_range = attack_range
        self.max_defense = max_defense  # the maximum amount of damage this cultivator can defend against (for formation agents they do the connection thing so this sums, but this is just for a single cultivator)

        # Use these to determine whether in windup or strike or neither
        # self.attacking = False  # replaced by self.state ('windup' = attacking)
        # self.windup_time_remaining = 0  # replaced by self.ticks_left
        self.state = 'idle'   # idle, windup, recover, defend, support
        self.ticks_left = 0     # turns left in windup / recover
        self.target = None    # who I'm attacking (for the enemy: who I'm going after)
        self.supporters = []    # chain members passing me power (attack) or defense (defend)
        self.support_of = None    # the member I'm passing power/defense to
        self.last_action = 'idle'  # what I did on my last turn (for the visualization)

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

    def is_alive(self):
        return self.health > 0

    def can_hit(self, other):
        '''Whether other is within my attack range (Chebyshev)'''
        return chebyshev(self.get_pos(), other.get_pos()) <= self.attack_range

    def log(self, msg):
        '''One-line action log, only when the model is verbose'''
        if self.model.verbose:
            print(f'[t{self.model.steps}] Agent {self.id}: {msg}')

    def move_to(self, cell):
        '''Move to cell and keep every position record in sync'''
        self.model.grid.move_agent(self, cell)
        self.position = cell
        self.exact_pos = cell
        agent_pos[self.id] = cell

    def reachable_cells(self):
        '''Free cells within speed (Moore radius), plus staying put'''
        grid = self.model.grid
        cells = grid.get_neighborhood(self.get_pos(), moore=True, include_center=False, radius=self.speed)

        return [c for c in cells if grid.is_cell_empty(c)] + [self.get_pos()]

# ======= ATTACK/DEFENSE ======= #

    def chain(self, pool):
        '''Everyone in pool linked to me through members within attack range of each other (includes me)'''
        linked = [self]  # everyone in the chain so far
        frontier = [self]  # chain members whose neighbors haven't been checked yet
        rest = [m for m in pool if m is not self]  # everyone not in the chain yet

        while frontier:  # keep adding anyone within range of someone already in the chain (checking order doesn't matter, the chain ends up the same)
            cur = frontier.pop()
            near = [m for m in rest if chebyshev(cur.get_pos(), m.get_pos()) <= min(cur.attack_range, m.attack_range)]  # both have to be in each other's range

            for m in near:  # move them into the chain, then check their neighbors too
                rest.remove(m)
                linked.append(m)
                frontier.append(m)

        return linked  # me first, then everyone linked to me

    def attack_power(self):
        '''My power + power passed down the chain from living supporters'''
        return self.power + sum(s.power for s in self.supporters if s.is_alive())  # dead supporters don't pass anything

    def defense_power(self):
        '''My max defense + defense coupled in from living supporters'''
        return self.max_defense + sum(s.max_defense for s in self.supporters if s.is_alive())  # dead supporters don't pass anything

    def enlist(self, supporters):
        '''Lock supporters into passing me power/defense'''
        self.supporters = supporters

        for s in supporters:  # supporters can't attack/move/defend for themselves while lending
            s.state = 'support'
            s.support_of = self  # so they know who they're lending to
            s.last_action = 'support'

    def release_supporters(self):
        '''Free everyone who was passing me power/defense'''
        for s in self.supporters:
            if s.support_of is self:  # only free them if they're still lending to me
                s.state = 'idle'
                s.support_of = None

        self.supporters = []

    def attack(self, target=None, supporters=()):
        '''Attack the enemy if within range'''
        # Find all enemies within range
        # For enemy cultivator:
            # if no strategy, the pick a random cultivator
            # if strategy, pick the target cultivator if the target cultivator is in range, else pick a random cultivator
        # For formation cultivator: check if enemy is in range, if so, all formation cultivators should give their power to this cultivator and this cultivator should attack the enemy

        # For now, just print an attack message
        # print(f'Agent {self.id} attacks the enemy at position {agent_pos[ENEMY]} with power {self.power}')  # replaced by the real attack below

        # Declare the attack (the chain passes its power in); lands right away if windup_time is 0
        self.target = target
        self.enlist(list(supporters))  # the rest of the chain is locked in until the strike lands
        self.state = 'windup'
        self.ticks_left = self.windup_time  # counts down at the start of each of my turns (begin_turn)
        self.last_action = 'attack'
        self.log(f'winds up on {target.get_id()} with power {self.attack_power()} (chain of {len(self.supporters) + 1})')

        if self.windup_time <= 0:  # no windup (e.g. enemy): hits right away, so the target gets no warning
            self.strike()

    def strike(self):
        '''The attack lands (if the target is still in range), then recovery'''
        t = self.target

        if t is not None and t.is_alive() and self.can_hit(t):  # range is checked again now, since the target might've moved during my windup
            t.defend(self.attack_power(), self)  # target works out how much actually gets through
        else:
            self.log('strike misses (target escaped or gone)')

        self.release_supporters()  # hit's done, chain members are free again

        busy = max(self.strike_time - 1, 0) + self.recovery_time  # landing turn already used 1 strike tick
        if busy > 0:  # stuck recovering (can't attack, move, or defend) for this many turns
            self.state, self.ticks_left = 'recover', busy
        else:
            self.state, self.ticks_left = 'idle', 0

    def brace(self, supporters=()):
        '''Take a defensive stance until my next turn (chain supporters couple their defense in)'''
        self.enlist(list(supporters))  # chain members add their max defense to mine
        self.state = 'defend'  # damage only gets reduced while I'm in this state
        self.last_action = 'defend'
        self.log(f'defends with max defense {self.defense_power()} (chain of {len(self.supporters) + 1})')

    def defend(self, damage, attacker=None):  # model should call this and calculate the total aimed damage from all attackers
        '''Defend against incoming attacks'''
        # damage = damage - self.max_defense  # reduce damage by max defense  (now only if actually defending, and chain-summed)
        if self.state == 'defend':
            damage = damage - self.defense_power()  # reduce damage by max defense (summed over the defense chain)
        # not defending: take the full hit

        if damage > 0:  # fully blocked hits do nothing
            self.health = max(self.health - damage, 0)
            self.log(f'takes {damage} damage from {attacker.get_id() if attacker else "?"}, health now {self.health}')
            # print(f'Agent {self.id} defends and takes {damage} damage, health now {self.health}')  # now goes through log() so it only prints when verbose

        if self.health <= 0:  # dead: off the grid, but stays in agent_list for the score
            self.model.kill(self)

    def end_stance(self):
        '''Defensive stance only lasts until my next turn'''
        if self.state == 'defend':
            self.release_supporters()  # defense chain breaks up too
            self.state = 'idle'

    def begin_turn(self):
        '''Advance windup/recovery/support; returns True if busy this turn'''
        if self.state == 'support':
            boss = self.support_of  # whoever I'm lending power/defense to
            if boss is not None and boss.is_alive() and boss.state in ('windup', 'defend'):  # still needs me
                return True
            self.state, self.support_of = 'idle', None  # they're done (or dead), so I'm free this turn

        if self.state == 'windup':
            self.ticks_left -= 1
            if self.ticks_left <= 0:  # windup's over: hit lands this turn
                self.strike()
            return True  # winding up or striking uses up my turn

        if self.state == 'recover':
            self.ticks_left -= 1
            if self.ticks_left <= 0:  # free again starting next turn
                self.state = 'idle'
            self.last_action = 'recover'
            return True

        return False  # idle: free to choose what to do

    def escape(self, threat=None, toward=None):
        '''Escape from the range of hostile attack - should only be called if the agent actually able to move out of the range of attack
        Overrides all other movement logic, so should be called first in the step() method if the agent is being attacked
        Returns True if escaped, False if cornered'''
        # formation agent should move out of the range of the attack of the hostile entirely, and pick the point in its range of movement that minimizes its summed distance from the other formation members (so that they can still do the combo attack)

        # the enemy should try to move to the point in its movement range that is both out of the attack range and farthest from all formation agents

        if self.type == 'enemy':
            # hostiles = [m for m in self.model.members() if m.is_alive()]  # old: had to get out of EVERY member's range
            members = [m for m in self.model.members() if m.is_alive()]
            hostiles = [m for m in members if m.state == 'windup' and m.target is self]  # only the attacks actually coming at me, since getting out of their range makes them miss
            if not hostiles:
                hostiles = members  # nothing winding up: just get away from everyone
            if self.boxed_in():  # surrounded in the von Neumann neighborhood: can't escape
                return False
        else:
            hostiles = [threat]  # formation member just has to get away from the enemy

        # safe = [c for c in self.reachable_cells() if all(chebyshev(c, h.get_pos()) > h.attack_range for h in hostiles)]  # out of everyone's range
        safe = [c for c in self.reachable_cells() if c != self.get_pos() and all(chebyshev(c, h.get_pos()) > h.attack_range for h in hostiles)]  # out of the attackers' range (staying put isn't escaping)
        if not safe:  # cornered: caller has to defend instead
            return False

        if self.type == 'enemy':
            def exposure(c):  # how many members could still reach me there next turn (fewer = better)
                return sum(chebyshev(c, m.get_pos()) <= m.attack_range for m in members)

            if toward is not None:  # strategy: escape toward the target member
                # best = min(safe, key=lambda c: math.dist(c, toward.get_pos()))
                best = min(safe, key=lambda c: (exposure(c), math.dist(c, toward.get_pos())))
            else:  # no strategy: farthest from all formation agents
                # best = max(safe, key=lambda c: sum(math.dist(c, h.get_pos()) for h in hostiles))
                best = min(safe, key=lambda c: (exposure(c), -sum(math.dist(c, m.get_pos()) for m in members)))
    
        else:  # formation: stay close to everyone else so the combo still works
            others = [m for m in self.model.members() if m is not self and m.is_alive()]
            best = min(safe, key=lambda c: sum(math.dist(c, m.get_pos()) for m in others))

        self.move_to(best)  # escape skips the movement equation entirely
        self.last_action = 'escape'
        self.log(f'escapes to {best}')
        return True

    def boxed_in(self):
        '''Can't escape if all 4 von Neumann neighbors are taken (or off the grid)'''
        x, y = self.get_pos()
        grid = self.model.grid

        for c in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):  # right, left, up, down
            if not grid.out_of_bounds(c) and grid.is_cell_empty(c):  # one open side is enough to get out
                return False

        return True

    def approach(self, target):
        '''Greedy move: reachable free cell closest to target'''
        best = min(self.reachable_cells(), key=lambda c: math.dist(c, target.get_pos()))  # straight-line closest, ignores formation shape

        if best != self.get_pos():  # stay put if nothing gets me closer
            self.move_to(best)
        self.last_action = 'move'

# ======= ENEMY ======= #

    def surrounded_sides(self):  # not used right now (was the old escape trigger), kept in case
        '''How many of my 4 sides (N/E/S/W) have a formation member that can hit me'''
        sides = set()  # set, so two members on the same side only count once

        for m in self.model.members():
            if m.is_alive() and m.can_hit(self):
                dx, dy = m.get_pos()[0] - self.get_pos()[0], m.get_pos()[1] - self.get_pos()[1]

                if abs(dx) >= abs(dy):  # diagonal ties count as the horizontal side
                    sides.add('E' if dx > 0 else 'W')
                else:
                    sides.add('N' if dy > 0 else 'S')

        return len(sides)

    def incoming_power(self):
        '''Total power of formation attacks currently winding up on me'''
        return sum(m.attack_power() for m in self.model.members() if m.is_alive() and m.state == 'windup' and m.target is self)  # windups are visible, so the enemy can see the hit coming (this is what lets it escape/defend in time)

    def strategy_target(self):
        '''Member the enemy is going after: the eye or the weakest (None = no strategy)'''
        members = [m for m in self.model.members() if m.is_alive()]
        if not members:
            return None

        weakest = min(members, key=lambda m: (m.get_health(), m.get_id()))  # lowest health, ties go to the lower id

        if self.strategy == 'eye':
            eye = [m for m in members if m.get_id() == EYE]
            return eye[0] if eye else weakest  # eye dead -> go for the weakest
        if self.strategy == 'weakest':
            return weakest

        return None

    def enemy_turn(self):
        '''Enemy picks attack / escape / defend / move for its turn'''
        self.end_stance()  # last turn's defense is over
        if self.begin_turn():  # still mid-attack or recovering
            return

        members = [m for m in self.model.members() if m.is_alive()]
        if not members:
            return

        in_range = [m for m in members if self.can_hit(m)]  # who I could hit right now
        # sides = self.surrounded_sides()
        # threatened = sides >= 2 or self.incoming_power() > self.max_defense  # surrounded on 2+ sides, or a hit coming that's bigger than my defense
        incoming = self.incoming_power()  # total power winding up on me
        goal = self.strategy_target()  # None if no strategy

        # 1. Incoming attack too strong to block -> escape (toward the goal if I have a strategy); defend only if I can't
        if incoming > self.max_defense:
            if self.escape(toward=goal):
                return
            self.brace()
            return

        # 2. Incoming attack I can fully block -> defend
        if incoming > 0:
            self.brace()
            return

        # 3. Nothing coming at me -> go on the offensive
        # No strategy: react to immediate circumstances
        if goal is None:
            # if sides >= 2 and self.escape():  # old escape trigger (surrounded on 2+ sides): with attack range 4 this fired most turns, and it ignored how strong the attack actually was
            #     return

            # if threatened:
            #     self.brace()
            if in_range:
                self.attack(self.random.choice(in_range))  # random member in range
            else:
                self.target = min(members, key=lambda m: math.dist(self.get_pos(), m.get_pos()))
                self.approach(self.target)
            return

        # Strategy: get to the goal member and hit it
        self.target = goal

        if self.can_hit(goal):  # always hit the goal over anyone else
            self.attack(goal)  # enemy has windup 0, so this lands immediately

        # elif threatened:  # prefer escaping toward the goal, else defend  (now handled in 1. and 2. above)
        #     if not self.escape(toward=goal):
        #         self.brace()

        else:
            best = min(self.reachable_cells(), key=lambda c: math.dist(c, goal.get_pos()))  # best I could get toward the goal this turn

            if math.dist(best, goal.get_pos()) >= math.dist(self.get_pos(), goal.get_pos()) and in_range:  # can't get any closer
                self.attack(self.random.choice(in_range))  # blocked from the goal: hit whoever's in the way instead
            else:
                self.approach(goal)

# ======= MOVEMENT ======= #

    def step_new_pos(self, alpha, beta, gamma, delta=0):
        '''Calculate the best new position for each member'''
        e = self.encircle(agent_pos[ENEMY])
        s = self.shape()
        r = self.rotate()
        c = (0, 0)  # no close-in unless delta > 0 (was unset before -> crash when delta = 0)
        if delta > 0:
            c = self.close_in()   # the head and tail closes in to attack the enemy if the middle is attacked, and the middle escapes

        change = (alpha * e[0] + beta * s[0] + gamma * r[0] + delta * c[0],
                  alpha * e[1] + beta * s[1] + gamma * r[1] + delta * c[1])

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

        p = pivot_id()  # the eye, unless it's dead
        # init_eye, eye = FORMATION_INIT_POS[EYE], agent_pos[EYE]  # replaced by the pivot so this still works after the eye dies
        init_eye, eye = FORMATION_INIT_POS[p], agent_pos[p]
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

        p = pivot_id()
        if chebyshev(agent_pos[ENEMY], agent_pos[p]) > ROTATE_TRIGGER:  # if enemy is outside rotating range
            return (0, 0)

        if self.model.center == EYE:
            center = agent_pos[p]
        else:
            center = agent_pos[ENEMY]

        rx, ry = self.pos[0] - center[0], self.pos[1] - center[1]  # dist from center

        return (-ry, rx)  # (rx, ry) turned 90 dg counterclockwise; tangent vector around center

    def close_in(self):
        '''f_close_in: full vector to the nearest free cell where I can hit the enemy (so delta = fraction of the gap closed per tick)'''

        enemy_pos = agent_pos[ENEMY]
        grid = self.model.grid
        ring = grid.get_neighborhood(enemy_pos, moore=True, include_center=False, radius=self.attack_range)  # cells that can hit the enemy
        open_cells = [c for c in ring if grid.is_cell_empty(c) or c == self.pos]

        if open_cells:
            goal = min(open_cells, key=lambda c: math.dist(c, self.pos))
        else:
            goal = enemy_pos  # all attack spots taken: just head for the enemy

        return (goal[0] - self.pos[0], goal[1] - self.pos[1])

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

    def step(self, delta=0):
        '''Define the agent's behavior for a single clock step (normal formation movement).'''
        if self.type == 'enemy':
            return  # enemy moves in enemy_turn() instead

        # possible_steps = self.model.grid.get_neighborhood(self.pos, moore=True, include_center=False)  # old random walk, replaced by step_new_pos
        # new_position = self.random.choice(possible_steps)
        new_position = self.step_new_pos(self.model.alpha, self.model.beta, self.model.gamma, delta)

        self.model.grid.move_agent(self, new_position)
        self.position = new_position
        agent_pos[self.id] = new_position  # live update, so members moving after me see where I went
        self.last_action = 'move'


class GridModel(mesa.Model):
    '''The grid model for modeling formation and enemy movements / battle.'''
    def __init__(self, width=60, height=60, alpha=ALPHA, beta=BETA, gamma=GAMMA, delta=DELTA, center=CENTER, strategy=STRATEGY,
                 close_in_override=CLOSE_IN_OVERRIDE, max_ticks=MAX_TICKS, verbose=False, seed=None):
        # Mesa 3.0 explicitly requires seed initializing the base class
        super().__init__(seed=seed)
        # self.agents = agents  # Mesa already owns model.agents (read-only), so the list lives in agent_list and don't need this
        self.steps = 0  # global step counter
        self.alpha, self.beta, self.gamma, self.delta = alpha, beta, gamma, delta
        self.center = center
        self.close_in_override = close_in_override
        self.max_ticks = max_ticks
        self.verbose = verbose   # print every action
        self.winner = None       # 'formation', 'enemy', or 'timeout' once the fight ends
        self.action_counts = {}  # (who, action) -> count, to check which rules actually fire

        # fresh globals for every new model (e.g. hitting Reset in the visualization)
        agent_list.clear()
        agent_pos.clear()

        # Initialize a MultiGrid (allows multiple agents per cell)
        # self.grid = mesa.space.MultiGrid(width, height, torus=True)  # torus off: wrapping splits the formation across edges and breaks the shape/rotation vectors
        self.grid = mesa.space.MultiGrid(width, height, torus=False)

        # Create and place agents on their initial grid coordinates
        for i in range(7):  # for formation cultivators
            # agent = CultivatorAgent(self)  # default vals (attack_range 1 -> members 2-4 cells apart in the shape could never chain)
            agent = CultivatorAgent(self, health=QZ_HEALTH, power=QZ_POWER, strike_time=QZ_STRIKE, recovery_time=QZ_RECOVERY, speed=QZ_SPEED, attack_range=QZ_ATT_RANGE, max_defense=QZ_MAX_DEF, type='formation')
            agent.set_id(i + 1)  # id = 1-7
            agent.initialize_position()  # sets position based on id
            self.grid.place_agent(agent, agent.get_pos())
            agent_list.append(agent)

        # Create and place the enemy cultivator
        # self, model, health, power, windup_time, strike_time, recovery_time, speed, attack_range, type
        enemy_agent = CultivatorAgent(self, health=E_HEALTH, power=E_POWER, strike_time=E_STRIKE, recovery_time=E_RECOVERY, speed=E_SPEED, attack_range=E_ATT_RANGE, max_defense=E_MAX_DEF, type='enemy', strategy=strategy)
        enemy_agent.set_id(ENEMY)  # id = 8 for enemy
        # agent.initialize_position()  # bug: this re-initialized the last formation agent instead of the enemy
        enemy_agent.initialize_position()  # sets position based on id
        self.grid.place_agent(enemy_agent, enemy_agent.get_pos())
        agent_list.append(enemy_agent)

        # Update for start
        # The data collector lambda m thing is a standard Mesa initialization method
        update_pos_list(agent_list)
        # 'Eye-enemy dist': lambda m: chebyshev(agent_pos[EYE], agent_pos[ENEMY])  # removed: crashes once the eye or enemy dies
        self.datacollector = mesa.DataCollector(model_reporters={'Shape error': lambda m: m.shape_error(), 'Formation angle (deg)': lambda m: m.formation_angle(),
                                                                 'Enemy health': lambda m: m.enemy().get_health(), 'Formation health': lambda m: sum(a.get_health() for a in m.members())})
        self.datacollector.collect(self)

    def members(self):
        return agent_list[:7]

    def enemy(self):
        return agent_list[ENEMY - 1]

    def kill(self, agent):
        '''Take a dead agent off the grid (it stays in agent_list so the score indexing still works)'''
        agent.release_supporters()

        if agent.support_of is not None and agent in agent.support_of.supporters:
            agent.support_of.supporters.remove(agent)

        agent.state = 'dead'
        self.grid.remove_agent(agent)
        agent_pos.pop(agent.get_id(), None)
        agent.log('dies')

    def count(self, who, action):
        self.action_counts[(who, action)] = self.action_counts.get((who, action), 0) + 1

    def shape_error(self):
        '''Avg distance (cells) between each member and its ideal slot, 0 = perfect formation'''
        # return sum(math.dist(a.get_pos(), a.ideal_pos()) for a in agent_list[:7]) / 7  # now only counts living members
        alive = [a for a in self.members() if a.is_alive()]

        if not alive or not self.enemy().is_alive():
            return 0.0

        return sum(math.dist(a.get_pos(), a.ideal_pos()) for a in alive) / len(alive)

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

            score -= self.steps / self.max_ticks  # faster victory is better; look into normalizing this if the # of steps overshadows the health aspect of the score too much

        # If enemy won
        else: # score will be in negatives; relative value still matters because it tells us how badly we lost
            # loss condition = entire formation dead
            score -= enemy.get_health() / enemy.get_max_health()  # normalize health
            score += self.steps / self.max_ticks  # normalize steps, slower loss is better; look into normalizing this if the # of steps overshadows the health aspect of the score too much

        return score

    def formation_turn(self):
        '''Formation's turn: the attacked member reacts first, then attacks, then head/tail close in, then everyone else moves'''
        enemy = self.enemy()
        alive = [m for m in self.members() if m.is_alive()]

        for m in alive:
            m.end_stance()  # defenses from last turn are over

        # windup members go first, so a strike that lands frees its supporters this same turn
        free = []
        for m in sorted(alive, key=lambda m: m.state != 'windup'):
            if m.is_alive() and not m.begin_turn():  # begin_turn() also lands any strikes that finish winding up
                free.append(m)  # free = can choose an action this turn

        if not enemy.is_alive():  # a strike that just landed killed it
            return

        acted = set()       # members who've already used their turn
        responders = set()  # head/tail members who come in when the middle is attacked

        # who is the enemy going for? (its target, if it can hit them on its next turn)
        attacked = None
        if enemy.target is not None and enemy.target.is_alive() and enemy.can_hit(enemy.target):
            attacked = enemy.target

        # 1. attacked member reacts first (escape overrides all other movement)
        if attacked is not None and attacked in free:

            if attacked.get_id() in MIDDLE_IDS:  # middle: escape unless cornered; head + tail close in to hit the enemy
                responders = HEAD_IDS | TAIL_IDS

                if attacked.escape(enemy):
                    self.count('formation', 'middle escape')
                else:
                    attacked.brace()
                    self.count('formation', 'middle cornered -> defend')

            else:  # head/tail: couple defense along the chain
                pool = [m for m in free if m is not attacked]  # only free members can lend defense
                chain = attacked.chain([attacked] + pool)

                # only couple as much defense as it takes to block the hit (nearest first), so the rest stay free to attack
                # used = chain[1:]  # whole chain locked defending every turn -> nobody left to attack (stalemate vs. the weakest strategy)
                needed = enemy.power - attacked.max_defense  # how much more defense it takes to block the full hit
                used = []
                for s in sorted(chain[1:], key=lambda s: chebyshev(s.get_pos(), attacked.get_pos())):  # nearest first
                    if needed <= 0:  # enough to block it
                        break
                    used.append(s)
                    needed -= s.max_defense

                if used:  # empty if there's no chain, or if the member can already block it alone
                    attacked.brace(used)
                    acted.update(used)
                    self.count('formation', 'chain defense')
                elif attacked.escape(enemy):  # no chain to lean on: escape if possible
                    self.count('formation', 'head/tail escape (no chain)')
                else:
                    attacked.brace()
                    self.count('formation', 'head/tail defend alone')

            acted.add(attacked)  # attacked member used its turn either way

        # 2. attacks: anyone free in range of the enemy attacks with their chain's power (counter-attackers first)
        hitters = [m for m in free if m not in acted and m.can_hit(enemy)]
        hitters.sort(key=lambda m: m.get_id() not in responders)  # False sorts before True, so responders first

        for m in hitters:
            if not enemy.is_alive():  # an instant strike (windup 0) can kill it mid-turn
                return
            if m in acted:  # already lending power to an earlier attacker's chain
                continue

            chain = m.chain([x for x in free if x not in acted])  # everyone free who links to me
            m.attack(enemy, chain[1:])  # I strike, the rest of the chain passes me their power
            acted.update(chain)  # one attack per chain
            self.count('formation', 'counter attack' if m.get_id() in responders else 'attack')
            self.count('formation', f'attack chain size {len(chain)}')

        if not enemy.is_alive():  # nobody left to move toward
            return

        # 3. head/tail close in when the middle is attacked (override toggle: skip the movement equation and charge)
        if responders and self.close_in_override:
            for m in free:
                if m not in acted and m.get_id() in responders:
                    m.approach(enemy)
                    acted.add(m)
                    self.count('formation', 'close in (override)')

        # 4. everyone else: normal movement (responders get the delta close-in term when not overriding)
        for m in sorted(free, key=lambda m: m.get_id() != pivot_id()):  # pivot (eye) claims its cell first
            if m in acted or not m.is_alive():
                continue

            d = self.delta if m.get_id() in responders else 0  # close-in term only for responders
            m.step(delta=d)

    def step(self):
        '''Advance the simulation by one round: formation turn, then enemy turn.'''
        update_pos_list(agent_list)

        # self.agents.shuffle_do('step')  # replaced: fixed order so the eye claims its cell first (later: attacked agent goes first)
        # order = [agent_list[EYE - 1]] + [a for a in agent_list if a.get_id() != EYE]  # replaced by the turn system below
        # for agent in order:
        #     agent.step()
        self.formation_turn()

        enemy = self.enemy()
        if enemy.is_alive():
            enemy.enemy_turn()
            self.count('enemy', enemy.last_action)

        update_pos_list(agent_list)
        self.datacollector.collect(self)

        # end conditions
        if not enemy.is_alive():
            self.winner, self.running = 'formation', False
        elif not any(m.is_alive() for m in self.members()):
            self.winner, self.running = 'enemy', False
        elif self.steps >= self.max_ticks:
            self.winner, self.running = 'timeout', False


# ======= EXECUTION ======= #
if __name__ == '__main__':
    for strategy in (None, 'weakest', 'eye'):
        sim_model = GridModel(strategy=strategy, seed=42)

        while sim_model.running:
            sim_model.step()

        print(f'strategy={strategy}: {sim_model.winner} at step {sim_model.steps}, enemy hp {sim_model.enemy().get_health()}, formation hp {[m.get_health() for m in sim_model.members()]}, score {sim_model.get_score():.2f}')