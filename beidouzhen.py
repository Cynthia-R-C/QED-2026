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
MODE = 'formation'  # options: 'formation' (北斗阵) or 'baseline' (same 7 members, no formation: everyone fights for themselves)
BASELINE_COLLISIONS = True  # baseline only: True = members can't share a cell; False = they can stack on each other (not on the enemy)
ENEMY_BLOCKS_SMALL = False  # True = enemy spends its turn defending against any attack it can fully block; False = ignores those and keeps fighting (hit chance only matters when this is False)

# Movement weights: change = ALPHA * f_encircle + BETA * f_shape + GAMMA * f_rotate (tune later)
ALPHA = 3.0   # f_encircle is a unit vector, so ALPHA = cells/tick of pull toward the enemy
# ALPHA = 3.0   # f_encircle points at my spot on the encirclement circle; ALPHA = cells/tick toward it (never overshooting the spot)  (circle version, reverted)
BETA = 1.0    # f_shape is the full vector to the ideal slot, so BETA = fraction of the gap closed per tick
GAMMA = 0.3  # f_rotate has magnitude r, so GAMMA ~ angular speed in rad/tick (0.15 rad ~ 8.6 deg)
DELTA = 3.0   # f_close_in is the full vector to the ideal slot, so DELTA = fraction of the gap closed per tick; only used when the middle is attacked
ROTATE_TRIGGER = 6  # rotation kicks in once the enemy is within this many cells (Chebyshev) of the eye
FULL_SPEED = True  # True: move at full speed in the direction the movement equation points (tiny corrections < 1 cell stay small); False: move only as far as the forces add up to
FENCE_GAP = 1  # if the enemy is within this many cells of the line between two members, it's standing in their gap, so that fence doesn't block it

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
# QZ_HIT = 0.05  # chance a single member's strike connects (a chain of n connects with 1 - (1 - QZ_HIT)^n)
QZ_HIT = 0.05  # chance a single member's strike connects
QZ_CHAIN_HIT = 0.8  # chance a chain attack (2+ members) connects - the combined force is much harder to slip without moving, but not certain (蛤蟆功 counter, breaking the weakest link)

# Enemy
E_HEALTH = 100
E_POWER = 37.5
E_WINDUP = 0
E_STRIKE = 1
E_RECOVERY = 0
E_SPEED = 12
E_ATT_RANGE = 2
E_MAX_DEF = 40
E_HIT = 0.99  # chance the enemy's strike connects (nearly certain)


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


def crosses(p, q, a, b):
    '''Whether the move p -> q crosses the fence a to b (touching counts, but just starting on the fence doesn't), assumes single member fence'''

    def cross(p, q, t):  # returns z = (q - p) x (t - p) - which side of line p->q point t is on
        return (q[0] - p[0]) * (t[1] - p[1]) - (q[1] - p[1]) * (t[0] - p[0])

    d = (q[0] - p[0], q[1] - p[1])  # move
    f = (b[0] - a[0], b[1] - a[1])  # fence

    if f == (0, 0):  # fence is a single point (one member) = blocked only if the move goes right through it

        if cross(p, q, a) != 0:  # not on the move's line
            return False
        
        dd = d[0] * d[0] + d[1] * d[1]  # dd = |d|^2
        if dd == 0:  # magnitude of move is 0
            return False
        
        t = ((a[0] - p[0]) * d[0] + (a[1] - p[1]) * d[1]) / dd  # fraction of the move to the fence
        # t = ((a − p) dot d) / |d|^2

        return 0 < t <= 1

    # General case
    denom = d[0] * f[1] - d[1] * f[0]  # d x f

    if denom == 0:  # parallel
        if cross(a, b, p) != 0:  # parallel but not on the same line: can't cross
            return False
        
        # same line
        dd = d[0] * d[0] + d[1] * d[1]  # move != 0
        if dd == 0:
            return False

        # ensure move is not beyond the fence segment
        ta = ((a[0] - p[0]) * d[0] + (a[1] - p[1]) * d[1]) / dd
        tb = ((b[0] - p[0]) * d[0] + (b[1] - p[1]) * d[1]) / dd
        return max(ta, tb) > 0 and min(ta, tb) <= 1

    ap = (a[0] - p[0], a[1] - p[1])
    t = (ap[0] * f[1] - ap[1] * f[0]) / denom  # how far along the move it hits the fence's line
    u = (ap[0] * d[1] - ap[1] * d[0]) / denom  # how far along the fence that is
    return 0 < t <= 1 and 0 <= u <= 1  # t = 0 counts as not on fence, tbh redundant cause path_blocked() already checks for this but might as well keep for good practice


def dist_to_segment(p, a, b):
    '''Shortest distance from point p to the segment a to b'''
    d = (b[0] - a[0], b[1] - a[1])
    dd = d[0] * d[0] + d[1] * d[1]  # |d|^2

    if dd == 0:  # a and b are the same point
        return math.dist(p, a)

    t = ((p[0] - a[0]) * d[0] + (p[1] - a[1]) * d[1]) / dd  # fraction along a -> b of the point closest to p
    t = max(0, min(1, t))  # stay on the segment (closest segment could be from extension of the line)

    return math.dist(p, (a[0] + t * d[0], a[1] + t * d[1]))  # dist from point found via t


def pivot_id():
    '''Member the formation pivots on: the eye, or the lowest-id living member once the eye is dead'''
    if EYE in agent_pos:
        return EYE

    alive = [i for i in range(1, 8) if i in agent_pos]
    return min(alive) if alive else None


def formation_turn():  # used in ideal_pos
    '''Best-fit rotation angle (rad) of the formation about the eye vs. its starting layout.
    For each member, u = starting offset from eye, v = current offset from eye'''

    p = pivot_id()  # the eye, unless it's dead
    if p is None:
        return 0.0

    # init_eye, eye = FORMATION_INIT_POS[EYE], agent_pos[EYE]  # replaced by the pivot so this still works after the eye dies
    init_eye, eye = FORMATION_INIT_POS[p], agent_pos[p]
    cross = 0
    dot = 0

    for i in range(1, 8):
        if i == p or i not in agent_pos:  # make sure there still exists some sort of pivot
            continue

        # The angle that best lines up all u's with all v's is arctan((u x v) / (u dot v))
        u = (FORMATION_INIT_POS[i][0] - init_eye[0], FORMATION_INIT_POS[i][1] - init_eye[1])  # starting offset from eye
        v = (agent_pos[i][0] - eye[0], agent_pos[i][1] - eye[1])   # current offset from eye

        cross += u[0] * v[1] - u[1] * v[0]
        dot += u[0] * v[0] + u[1] * v[1]

    return math.atan2(cross, dot)


# centroid of the 7 members' starting positions (used when the formation is centered on the enemy)
FORMATION_CENTROID = (sum(FORMATION_INIT_POS[i][0] for i in range(1, 8)) / 7, sum(FORMATION_INIT_POS[i][1] for i in range(1, 8)) / 7)


class CultivatorAgent(mesa.Agent):
    '''An agent that represents a cultivator in a grid environment.'''

    def __init__(self, model, health=100, power=10, windup_time=1, strike_time=1, recovery_time=1, speed=2, attack_range=2, max_defense=10, hit_chance=1.0, chain_hit_chance=1.0, type='formation', strategy=None):
        # Mesa 3.0 automatically assigns a unique_id if not provided
        super().__init__(model)

        # Stats
        self.health = health
        self.max_health = health
        self.power = power
        self.windup_time = windup_time      # turns between declaring an attack and it landing (0 = lands immediately)
        self.strike_time = strike_time      # turns the strike takes (the landing turn counts as 1)
        # self.recovery_time = recovery_time  # turns stuck after the strike
        self.recovery_time = recovery_time  # turns stuck after taking damage (staggered by the hit)
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
        self.hit_chance = hit_chance  # chance my strike connects at all (the target can dodge without moving)
        self.chain_hit_chance = chain_hit_chance  # chance my strike connects when I'm sending a chain attack (2+ members)

        # Use these to determine whether in windup or strike or neither
        # self.attacking = False  # replaced by self.state ('windup' = attacking)
        # self.windup_time_remaining = 0  # replaced by self.ticks_left
        self.state = 'idle'   # idle, windup, recover, defend, support
        self.ticks_left = 0     # turns left in windup / recover
        self.target = None    # who I'm attacking (for the enemy: who I'm going after)
        self.supporters = []    # chain members passing me power (attack)
        self.support_of = None    # the member I'm passing power to
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

    def reachable_cells(self, stack=False):
        '''Free cells within speed (Moore radius), plus staying put; stack=True also allows cells with only teammates in them'''
        grid = self.model.grid
        cells = grid.get_neighborhood(self.get_pos(), moore=True, include_center=False, radius=self.speed)

        if stack:  # baseline with collisions off - teammates don't block, the enemy still does
            return [c for c in cells if all(a.type == self.type for a in grid.get_cell_list_contents([c]))] + [self.get_pos()]

        return [c for c in cells if grid.is_cell_empty(c)] + [self.get_pos()]  # teammates do block

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

    def enlist(self, supporters):
        '''Lock supporters into passing me power'''
        self.supporters = supporters

        for s in supporters:  # supporters can't attack/move/defend for themselves while lending
            s.state = 'support'
            s.support_of = self  # so they know who they're lending to
            s.last_action = 'support'

    def release_supporters(self):
        '''Release all supporters in chain'''
        for s in self.supporters:
            if s.support_of is self:  # only free them if they're still lending to me
                s.state = 'idle'
                s.support_of = None

        self.supporters = []

    def attack(self, target=None, supporters=()):
        '''Attack the enemy if within range'''
        # This is a placeholder for the attack logic
        # Find all enemies within range
        # For enemy cultivator:
            # if no strategy, the pick a random cultivator
            # if strategy, pick the target cultivator if the target cultivator is in range, else pick a random cultivator
        # For formation cultivator: check if enemy is in range, if so, all formation cultivators should give their power to this cultivator and this cultivator should attack the enemy

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

        # chance the strike connects
        n = 1 + len([s for s in self.supporters if s.is_alive()])  # me + living supporters
        if n >= 2:  # chain attack: only the member sending it rolls, the rest just pass power
            p_hit = self.chain_hit_chance
        else:  # alone
            p_hit = self.hit_chance

        # check if hit still valid
        if t is not None and t.is_alive() and self.can_hit(t):  # range is checked again now, since the target might've moved during my windup
            if self.random.random() < p_hit:
                t.defend(self.attack_power(), self)  # target works out how much actually gets through
            else:
                self.log(f'strike misses (dodged, hit chance {p_hit:.2f})')
        else:
            self.log('strike misses (target escaped or gone)')

        self.release_supporters()  # hit's done, chain members are free again

        # if strike time is greater than one tick keep busy
        busy = max(self.strike_time - 1, 0)  # landing turn already used 1 strike tick
        if busy > 0:  # strike takes more turns: stuck for this many
            self.state, self.ticks_left = 'recover', busy
        else:
            self.state, self.ticks_left = 'idle', 0

    def brace(self):
        '''Take a defensive stance until my next turn'''
        self.state = 'defend'  # damage only gets reduced while I'm in this state
        self.last_action = 'defend'
        self.log(f'defends with max defense {self.max_defense}')

    def defend(self, damage, attacker=None):  # model should call this and calculate the total aimed damage from all attackers
        '''Defend against incoming attacks'''
        # This is a placeholder for the defense logic
        # damage = damage - self.max_defense  # reduce damage by max defense  (now only if actually defending, and chain-summed)
        if self.state == 'defend':
            damage = damage - self.max_defense  # reduce damage by max defense
        # not defending: take the full hit

        if damage > 0:
            self.health = max(self.health - damage, 0)
            self.log(f'takes {damage} damage from {attacker.get_id() if attacker else "?"}, health now {self.health}')

        if self.health <= 0:  # dead: off the grid, but stays in agent_list for the score
            self.model.kill(self)

        elif damage > 0:  # got hurt: stuck recovering for a bit
            self.stagger()

    def stagger(self):
        '''Taking damage interrupts whatever I was doing and leaves me recovering for recovery_time turns'''
        if self.recovery_time <= 0:  # no effect
            return

        if self.state == 'windup':  # my attack gets interrupted, so my chain is freed
            self.release_supporters()
            self.log('attack interrupted')

        if self.state == 'support' and self.support_of is not None:  # stop lending to whoever I was supporting
            if self in self.support_of.supporters:
                self.support_of.supporters.remove(self)
            self.support_of = None

        self.state = 'recover'
        self.ticks_left = self.recovery_time  # counts down at the start of each of my turns (begin_turn)
        self.last_action = 'recover'

    def end_stance(self):
        '''Defensive stance only lasts until my next turn'''
        if self.state == 'defend':
            self.state = 'idle'

    def begin_turn(self):
        '''Advance windup/recovery/support; returns True if busy this turn'''
        if self.state == 'support':
            boss = self.support_of  # whoever this member is lending power to
            if boss is not None and boss.is_alive() and boss.state == 'windup':  # remain in support
                return True
            self.state, self.support_of = 'idle', None  # they're done (or dead), so am free this turn

        if self.state == 'windup':
            self.ticks_left -= 1
            if self.ticks_left <= 0:  # windup's over, hit lands this turn
                self.strike()
            return True  # winding up or striking uses up the turn

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
            hostiles = [m for m in members if m.state == 'windup' and m.target is self]  # only the attacks actually actively targeting
            if not hostiles:
                hostiles = members  # nothing winding up: just get away from everyone
            if self.boxed_in():  # surrounded in the von Neumann neighborhood: can't escape
                return False
        else:
            hostiles = [threat]  # formation member just has to get away from the enemy

        safe = [c for c in self.reachable_cells() if c != self.get_pos() and all(chebyshev(c, h.get_pos()) > h.attack_range for h in hostiles)]  # out of the attackers' range (staying put isn't escaping)

        if self.type == 'enemy':  # can't teleport through the encirclement: the path out can't cross between members whose ranges meet
            safe = [c for c in safe if not self.path_blocked(c, members)]

        if not safe:  # cornered, caller has to defend instead
            return False

        if self.type == 'enemy':

            def exposure(c):  # how many members could still reach me there next turn (fewer = better)
                return sum(chebyshev(c, m.get_pos()) <= m.attack_range for m in members)

            if toward is not None:  # strategy: escape toward the target member
                best = min(safe, key=lambda c: (exposure(c), math.dist(c, toward.get_pos())))

            else:  # no strategy: farthest from all formation agents
                best = min(safe, key=lambda c: (exposure(c), -sum(math.dist(c, m.get_pos()) for m in members)))
    
        elif self.model.mode == 'baseline':  # no formation to stay close to: just step out of range, staying close enough to fight back
            best = min(safe, key=lambda c: math.dist(c, threat.get_pos()))

        else:  # formation: stay close to everyone else so the combo still works
            others = [m for m in self.model.members() if m is not self and m.is_alive()]
            best = min(safe, key=lambda c: sum(math.dist(c, m.get_pos()) for m in others))

        # placeholder, for now just print an escape message
        # print(f'Agent {self.id} escapes!')  # now goes through log()
        self.move_to(best)  # escape skips the movement equation entirely
        self.last_action = 'escape'
        self.log(f'escapes to {best}')
        return True

    def path_blocked(self, cell, members):
        '''Whether the straight path from me to cell is blocked by the formation: passing through a member, or between two members whose attack ranges meet'''
        me = self.get_pos()

        for i, a in enumerate(members):  # pair loops, every possible combo of 2 members
            for b in members[i + 1:]:

                if chebyshev(a.get_pos(), b.get_pos()) <= a.attack_range + b.attack_range:  # ranges cover gap between them
                    if dist_to_segment(me, a.get_pos(), b.get_pos()) <= FENCE_GAP:  # I'm standing right in their gap, not behind their fence: it can't stop me
                        continue
                    if crosses(me, cell, a.get_pos(), b.get_pos()):
                        return True

            if crosses(me, cell, a.get_pos(), a.get_pos()):  # single member check - both for single members in pairs and if a member isn't in a pair (not within att range to form fence OR only one member alive)
                return True

        return False

    def boxed_in(self):
        '''Can't escape if all 4 von Neumann neighbors are taken (or off the grid)'''
        x, y = self.get_pos()
        grid = self.model.grid

        for c in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):  # right, left, up, down
            if not grid.out_of_bounds(c) and grid.is_cell_empty(c):  # one open side is enough to get out
                return False

        return True

    def approach(self, target, stack=False):
        '''Greedy move: reachable free cell closest to target'''
        best = min(self.reachable_cells(stack), key=lambda c: math.dist(c, target.get_pos()))  # straight-line closest, ignores formation shape

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
        if not members:  # if no members left end turn
            return

        in_range = [m for m in members if self.can_hit(m)]  # members that enemy could attack
        incoming = self.incoming_power()  # total power winding up on me
        goal = self.strategy_target()  # None if no strategy

        # 1. Incoming attack too strong to block --> escape (toward the goal if have a strategy), can't escape --> brace
        if incoming > self.max_defense:
            if self.escape(toward=goal):
                return
            self.brace()
            return

        # 2. Incoming attack below max defense --> defend(?)
        if incoming > 0 and self.model.enemy_blocks_small:  # off by default, blocking every weak hit kept the enemy on the defensive forever
            self.brace()
            return

        # 3. No incoming attack --> go on offense
        # No strategy: react to immediate circumstances
        if goal is None:
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

        else:
            
            best = min(self.reachable_cells(), key=lambda c: math.dist(c, goal.get_pos()))  # best get toward the goal this turn
            if math.dist(best, goal.get_pos()) >= math.dist(self.get_pos(), goal.get_pos()) and in_range:  # can't get any closer
                self.attack(self.random.choice(in_range))  # blocked from the goal: hit whoever's in the way instead

            else:
                self.approach(goal)

# ======= FORMATION MOVEMENT ======= #

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

        # Normalize to maximum formation speed
        if self.model.full_speed:
            biggest = max(abs(change[0]), abs(change[1]))  # largest change out of delta x delta y

            if biggest >= 1:  # tiny corrections (< 1 cell) stay tiny so I can settle into place
                k = self.speed / biggest
                change = (change[0] * k, change[1] * k)  # dilate so that max coord change = max speed (overshoot)

        # Keep direction, shrink magnitude until it's within the Chevyshev range of speed
        change = self.clamp_to_speed(change)

        # Move the exact (float) position, then snap to the nearest grid cell
        w, h = self.model.grid.width, self.model.grid.height
        ex = min(max(self.exact_pos[0] + change[0], 0), w - 1)  # keep within grid boundaries
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
        '''f_shape: vector from current member position to ideal slot (spring: bigger gap = bigger pull)'''
        ideal = self.ideal_pos()
        return (ideal[0] - self.pos[0], ideal[1] - self.pos[1])

    def ideal_pos(self):
        '''Where this member should ideally be to keep the formation shape, helper for shape()'''

        p = pivot_id()  # the eye, unless it's dead
        init_eye, eye = FORMATION_INIT_POS[p], agent_pos[p]
        phi = formation_turn()  # curr angle of formation
        orig_pos = FORMATION_INIT_POS[self.id]

        if self.model.center == EYE:  # shape built around the eye's current spot
            curr_piv, ref_piv = eye, init_eye

        else:  # shape built around the enemy (enemy sits at the formation's centroid)
            curr_piv, ref_piv = agent_pos[ENEMY], FORMATION_CENTROID

        off = rotate_vec((orig_pos[0] - ref_piv[0], orig_pos[1] - ref_piv[1]), phi)  # u, phi

        return (curr_piv[0] + off[0], curr_piv[1] + off[1])

    def rotate(self):
        '''f_rotate: tangent vector around center CCW, only once the enemy is near the eye'''

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
        '''f_close_in: full vector to the nearest free cell where the agent can hit the enemy (so delta = fraction of the gap closed per tick)'''

        enemy_pos = agent_pos[ENEMY]
        grid = self.model.grid
        ring = grid.get_neighborhood(enemy_pos, moore=True, include_center=False, radius=self.attack_range)  # cells that can hit the enemy
        open_cells = [c for c in ring if grid.is_cell_empty(c) or c == self.pos]  # current cell counts as open too

        if open_cells:
            dists = []
            for c in open_cells:
                dists.append(math.dist(c, self.pos))

            min_ind = dists.index(min(dists))
            goal = open_cells[min_ind]  # closest option to current pos

        else:
            goal = enemy_pos  # all attack spots taken, just head for the enemy

        return (goal[0] - self.pos[0], goal[1] - self.pos[1])

    def avoid(self, new_pos):
        '''Check whether new_pos already has another agent, if so move to unoccupied Moore neighborhood, if still all occupied move to more outer circle, etc.'''
        grid = self.model.grid

        def free(cell):
            return cell == self.pos or grid.is_cell_empty(cell)

        if free(new_pos):  # if free it's fine
            return new_pos

        for radius in range(1, 2 * self.speed + 2):  # rings around new_pos, nearest first

            ring = []  # list of pos
            for c in grid.get_neighborhood(new_pos, moore=True, include_center=False, radius=radius):
                if chebyshev(c, new_pos) == radius:  # only the outer ring
                    ring.append(c)

            options = []
            for c in grid.get_neighborhood(new_pos, moore=True, include_center=False, radius=radius):
                if chebyshev(c, new_pos) == radius and free(c) and chebyshev(c, self.pos) <= self.speed:  # must still be reachable this tick
                    options.append(c)

            if options:   # pick random option
                return self.random.choice(options)

        return self.pos  # if boxed in, stay put this tick


# ======= FORMATION UPDATE PER TICK ======= #

    def step(self, delta=0):
        '''Define the agent's behavior for a single clock step (normal formation movement).'''
        if self.type == 'enemy':
            return  # enemy moves in enemy_turn() instead

        new_position = self.step_new_pos(self.model.alpha, self.model.beta, self.model.gamma, delta)

        self.model.grid.move_agent(self, new_position)
        self.position = new_position
        agent_pos[self.id] = new_position  # live update, so members moving after me see where I went
        self.last_action = 'move'


class GridModel(mesa.Model):
    '''The grid model for modeling formation and enemy movements / battle.'''
    def __init__(self, width=60, height=60, alpha=ALPHA, beta=BETA, gamma=GAMMA, delta=DELTA, center=CENTER, strategy=STRATEGY,
                 close_in_override=CLOSE_IN_OVERRIDE, mode=MODE, baseline_collisions=BASELINE_COLLISIONS, enemy_blocks_small=ENEMY_BLOCKS_SMALL,
                 full_speed=FULL_SPEED, max_ticks=MAX_TICKS, verbose=False, seed=None):
        # Mesa 3.0 explicitly requires seed initializing the base class
        super().__init__(seed=seed)
        # self.agents = agents  # Mesa already owns model.agents (read-only), so the list lives in agent_list and don't need this
        self.steps = 0  # global step counter
        self.alpha, self.beta, self.gamma, self.delta = alpha, beta, gamma, delta
        self.center = center
        self.close_in_override = close_in_override
        self.mode = mode  # 'formation' or 'baseline'
        self.baseline_collisions = baseline_collisions
        self.enemy_blocks_small = enemy_blocks_small
        self.full_speed = full_speed
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
            # agent = CultivatorAgent(self, health=QZ_HEALTH, power=QZ_POWER, strike_time=QZ_STRIKE, recovery_time=QZ_RECOVERY, speed=QZ_SPEED, attack_range=QZ_ATT_RANGE, max_defense=QZ_MAX_DEF, type='formation')  # QZ_WINDUP wasn't passed (default 1 happened to match)
            # agent = CultivatorAgent(self, health=QZ_HEALTH, power=QZ_POWER, windup_time=QZ_WINDUP, strike_time=QZ_STRIKE, recovery_time=QZ_RECOVERY, speed=QZ_SPEED, attack_range=QZ_ATT_RANGE, max_defense=QZ_MAX_DEF, type='formation')
            # agent = CultivatorAgent(self, health=QZ_HEALTH, power=QZ_POWER, windup_time=QZ_WINDUP, strike_time=QZ_STRIKE, recovery_time=QZ_RECOVERY, speed=QZ_SPEED, attack_range=QZ_ATT_RANGE, max_defense=QZ_MAX_DEF, hit_chance=QZ_HIT, type='formation')
            agent = CultivatorAgent(self, health=QZ_HEALTH, power=QZ_POWER, windup_time=QZ_WINDUP, strike_time=QZ_STRIKE, recovery_time=QZ_RECOVERY, speed=QZ_SPEED, attack_range=QZ_ATT_RANGE, max_defense=QZ_MAX_DEF, hit_chance=QZ_HIT, chain_hit_chance=QZ_CHAIN_HIT, type='formation')
            agent.set_id(i + 1)  # id = 1-7
            agent.initialize_position()  # sets position based on id
            self.grid.place_agent(agent, agent.get_pos())
            agent_list.append(agent)

        # Create and place the enemy cultivator
        # self, model, health, power, windup_time, strike_time, recovery_time, speed, attack_range, type
        # enemy_agent = CultivatorAgent(self, health=E_HEALTH, power=E_POWER, strike_time=E_STRIKE, recovery_time=E_RECOVERY, speed=E_SPEED, attack_range=E_ATT_RANGE, max_defense=E_MAX_DEF, type='enemy', strategy=strategy)  # E_WINDUP wasn't passed, so the enemy had windup 1 instead of 0
        # enemy_agent = CultivatorAgent(self, health=E_HEALTH, power=E_POWER, windup_time=E_WINDUP, strike_time=E_STRIKE, recovery_time=E_RECOVERY, speed=E_SPEED, attack_range=E_ATT_RANGE, max_defense=E_MAX_DEF, type='enemy', strategy=strategy)
        enemy_agent = CultivatorAgent(self, health=E_HEALTH, power=E_POWER, windup_time=E_WINDUP, strike_time=E_STRIKE, recovery_time=E_RECOVERY, speed=E_SPEED, attack_range=E_ATT_RANGE, max_defense=E_MAX_DEF, hit_chance=E_HIT, type='enemy', strategy=strategy)
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
                                                                 'Enemy health': lambda m: m.enemy().get_health(), 'Formation health': lambda m: sum(a.get_health() for a in m.members()),
                                                                 'Largest gap (deg)': lambda m: m.largest_gap()})
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

    def largest_gap(self):
        '''Biggest empty angle around the enemy (deg): 360/7 = 51 = perfectly encircled by 7, 360 = no encirclement'''
        e = self.enemy().get_pos()
        a = sorted(math.atan2(m.get_pos()[1] - e[1], m.get_pos()[0] - e[0]) for m in self.members() if m.is_alive())

        if len(a) < 2:
            return 360.0

        gaps = [a[i + 1] - a[i] for i in range(len(a) - 1)] + [a[0] + 2 * math.pi - a[-1]]
        return math.degrees(max(gaps))

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

        # defenses from last turn are over
        for m in alive:
            m.end_stance()

        # windup members go first, so a strike that lands frees its supporters this same turn
        free = []
        for m in sorted(alive, key=lambda m: m.state != 'windup'):  # sorts list so that members currently winding up go first
            if m.is_alive() and not m.begin_turn():  # begin_turn() also lands any strikes that finish winding up
                free.append(m)  # free = can choose an action this turn

        if not enemy.is_alive():  # a strike that just landed killed it
            return

        acted = set()    # members who've already used their turn
        responders = set()  # members who counterattack: head/tail when the middle is attacked, or the two around an attacked head/tail member
        split = set()    # responders who each strike on their own instead of merging into one chain

        # who is the enemy going for? (its target, if it can hit them on its next turn)
        attacked = None
        if enemy.target is not None and enemy.target.is_alive() and enemy.can_hit(enemy.target):
            attacked = enemy.target

        # 1. attacked member reacts first (escape overrides all other movement)
        if attacked is not None and attacked in free:

            if attacked.get_id() in MIDDLE_IDS:  # middle: escape unless cornered; head + tail close in to hit the enemy
                responders = HEAD_IDS | TAIL_IDS  # union of sets

                if attacked.escape(enemy):
                    self.count('formation', 'middle escape')
                else:
                    attacked.brace()
                    self.count('formation', 'middle cornered -> defend')

            else:  # head/tail: step back out of the enemy's range, and the two members around it counterattack

                around = sorted([m for m in free if m is not attacked], key=lambda m: chebyshev(m.get_pos(), attacked.get_pos()))[:2]  # the two closest free members
                responders = {m.get_id() for m in around}  # they go first in the attacks below, and close in if out of range
                split = set(responders)  # the two each strike, so don't fold one into the other's chain

                if attacked.escape(enemy):
                    self.count('formation', 'head/tail escape')
                else:
                    attacked.brace()  # cornered: defend alone
                    self.count('formation', 'head/tail cornered -> defend')

            acted.add(attacked)  # attacked member used its turn either way

        # 2. attacks: anyone free in range of the enemy attacks with their chain's power (counter-attackers first)
        hitters = [m for m in free if m not in acted and m.can_hit(enemy)]
        hitters.sort(key=lambda m: m.get_id() not in responders)  # False sorts before True, so responders first

        for m in hitters:
            if not enemy.is_alive():  # an instant strike (windup 0) can kill it mid-turn
                return
            if m in acted:  # already lending power to an earlier attacker's chain
                continue

            # chain attacks
            pool = [x for x in free if x not in acted]  # everyone free who could link to me
            pool = [x for x in pool if x is m or x.get_id() not in split]  # exclude splitters
            chain = m.chain(pool)

            m.attack(enemy, chain[1:])  # self is always first in chain list
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

    def baseline_turn(self):
        '''Baseline's turn: same 7 members, no formation'''
        enemy = self.enemy()
        alive = [m for m in self.members() if m.is_alive()]

        for m in alive:
            m.end_stance()  # defenses from last turn are over

        free = []
        for m in sorted(alive, key=lambda m: m.state != 'windup'):  # windups first, same as the formation
            if m.is_alive() and not m.begin_turn():  # if member is alive and not busy (begin_turn)
                free.append(m)

        for m in sorted(free, key=lambda m: m.get_id()):  # no coordination: each member just reacts to its own situation
            if not enemy.is_alive():  # someone's strike killed it
                return

            if enemy.target is m and enemy.can_hit(m):  # currently being attacked, get out of range, if can't then defend
                if m.escape(enemy):
                    self.count('baseline', 'escape')
                else:
                    m.brace()  # alone, no chain
                    self.count('baseline', 'cornered -> defend')

            elif m.can_hit(enemy):  # in range: attack alone (no chain, nobody passes power)
                m.attack(enemy)
                self.count('baseline', 'attack')

            else:  # walk straight at the enemy (no shape, rotation, or close-in)
                m.approach(enemy, stack=not self.baseline_collisions)
                self.count('baseline', 'move')

    def step(self):
        '''Advance the simulation by one round: formation turn, then enemy turn.'''
        update_pos_list(agent_list)

        # Formation member logic
        if self.mode == 'formation':
            self.formation_turn()
        else:
            self.baseline_turn()

        # Enemy logic
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

    # formation vs baseline, same enemy, same seeds
    SEEDS = range(10)
    for strategy in (None, 'weakest', 'eye'):
        for mode in ('formation', 'baseline'):
            results = {'formation': 0, 'enemy': 0, 'timeout': 0}
            scores = []
            for seed in SEEDS:
                sim_model = GridModel(strategy=strategy, mode=mode, seed=seed)

                while sim_model.running:
                    sim_model.step()

                results[sim_model.winner] += 1
                scores.append(sim_model.get_score())

            print(f'strategy={strategy}, {mode}: formation wins {results["formation"]}, enemy wins {results["enemy"]}, timeouts {results["timeout"]}, avg score {sum(scores) / len(scores):.2f}')