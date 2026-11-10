import mesa

class WalkAgent(mesa.Agent):
    """An agent that wanders around a grid environment."""
    def __init__(self, model):
        # Mesa 3.0 automatically assigns a unique_id if not provided
        super().__init__(model)
        
    def step(self):
        """Define the agent's behavior for a single clock step."""
        # 1. Get neighboring coordinates (Moore neighborhood: includes diagonals)
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
    """A baseline model managing a grid and a collection of wandering agents."""
    def __init__(self, width=10, height=10, num_agents=20, seed=None):
        # Mesa 3.0 explicitly requires seed initializing the base class
        super().__init__(seed=seed)
        
        self.num_agents = num_agents
        
        # Initialize a MultiGrid (allows multiple agents per cell)
        # Toroidal=True means the grid wraps around the edges like a donut
        self.grid = mesa.space.MultiGrid(width, height, torus=True)
        
        # Create and place agents on random grid coordinates
        for _ in range(self.num_agents):
            agent = WalkAgent(self)
            
            # Choose a random (x, y) coordinate
            x = self.random.randrange(self.grid.width)
            y = self.random.randrange(self.grid.height)
            
            self.grid.place_agent(agent, (x, y))

    def step(self):
        """Advance the simulation by one step."""
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
