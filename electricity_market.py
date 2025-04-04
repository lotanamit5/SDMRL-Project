import numpy as np
import gymnasium as gym
from gymnasium import spaces

from defaults import (demand_default_fn, price_default_fn, 
                      DEFAULT_BATTERY_CAPACITY, HOURS_A_YEAR, 
                      DEMAND_STD, PRICE_STD)
from utils import NormalNoiseWrapper

class ElectricityMarketEnv(gym.Env):
    """
    A reinforcement learning environment modeling an electricity market where an agent 
    manages a battery storage system to maximize profit while meeting household demand.

    ## State Space:
    - **State of Charge (SoC):** Battery charge in [0, capacity].
    - **Demand (Dt):** Periodic electricity demand with stochastic noise.
    - **Price (Pt):** Periodic market price with stochastic noise.

    ## Action Space:
    - A single continuous value in [-capacity, capacity], representing charge (positive) or discharge (negative).

    ## Reward Function:
    - **Discharge (action < 0):** First meets demand; surplus energy is sold to the grid at Pt.
    - **Charge (action > 0):** Battery is charged, incurring a cost based on (charge + demand) * Pt.

    ## Episode Termination:
    - Fixed horizon (number of timesteps).
    - An attempt to step beyond the horizon raises an error.

    ## Parameters:
    - `capacity` (float): Battery capacity.
    - `horizon` (int): Number of timesteps per episode.
    - `demand_fn`, `price_fn` (callable, optional): Functions modeling demand and price.
    - `render_mode` (str): One of ["console", "human", "debug", "none"].
    - `seed` (int, optional): Random seed for reproducibility.
    - `noisy` (bool): Whether to add noise to demand and price functions.
    """
    
    _render_modes = ["console", "debug", "none"]        
    
    def __init__(self,
                 capacity: float = DEFAULT_BATTERY_CAPACITY,
                 horizon: int = HOURS_A_YEAR-1,
                 demand_fn: callable = demand_default_fn,
                 price_fn: callable = price_default_fn,
                 render_mode: str = "none",
                 noisy=True):
        super().__init__()
        self.render_mode = render_mode
        
        assert isinstance(capacity, (int, float)), f"The capacity should be a number, got {type(capacity)}"
        assert capacity > 0, f"The capacity should be greater than 0, got {capacity}"
        assert isinstance(horizon, int), f"The horizon should be an integer, got {type(horizon)}"
        assert horizon > 0, f"The horizon should be greater than 0, got {horizon}"
        assert callable(demand_fn), f"The demand function should be callable, got {type(demand_fn)}"
        assert callable(price_fn), f"The price function should be callable, got {type(price_fn)}"
        assert render_mode in self._render_modes, f"Only {', '.join(self._render_modes)} render mode/s are supported, got {render_mode}"
        
        self._noisy = noisy
        self._capacity = capacity
        self._timestep = 0
        self._state_of_charge = 0.
        self._horizon = horizon
        
        self._demand_fn = demand_fn
        self._price_fn = price_fn
        self.demand = self._demand_fn if not self._noisy else NormalNoiseWrapper(self._demand_fn, scale=DEMAND_STD)
        self.price = self._price_fn if not self._noisy else NormalNoiseWrapper(self._price_fn, scale=PRICE_STD)
        
        self._demand_from_grid = []
        
        self.action_space = spaces.Box(low=-self._capacity, high=self._capacity, shape=(), dtype=np.float32)
        self.observation_space = spaces.Box(
            low=np.array([0., 0., 0.], dtype=np.float32), 
            high=np.array([self._capacity, np.inf, np.inf], dtype=np.float32),
            shape=(3,), dtype=np.float32
        )
        self.render()
    
    def _get_obs(self):
        return np.asarray([self._state_of_charge, 
                           self.demand(self._timestep), 
                           self.price(self._timestep)], 
                          dtype=np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._state_of_charge = 0.
        self._timestep = 0
        self._demand_from_grid = []
        self.demand = self._demand_fn if not self._noisy else NormalNoiseWrapper(self._demand_fn, scale=DEMAND_STD)
        self.price = self._price_fn if not self._noisy else NormalNoiseWrapper(self._price_fn, scale=PRICE_STD)
        self.render()
        return self._get_obs(), {}  # empty info dict

    def step(self, action: float):
        if not -self._capacity <= action <= self._capacity:
            raise ValueError(
                f"Action must be between -{self._capacity} and {self._capacity}"
            )
        if self._timestep > self._horizon:
            raise ValueError("Episode is terminated, please reset the environment")
        
        demand = self.demand(self._timestep)
        price = self.price(self._timestep)
        
        if action < 0: # discharge
            discharge = min(self._state_of_charge, -action) # can not discharge more than SoC
            self._state_of_charge -= discharge
            
            # discharge - demand > 0 -> we have leftovers to sell
            # discharge - demand < 0 -> we need to buy extra units to satisfy demand
            self._demand_from_grid.append(max(0, demand - discharge))
            reward = (discharge - demand) * price
       
        else: # charge
            charge = min(self._capacity - self._state_of_charge, action) # can not charge more than the capacity
            self._state_of_charge += charge
            
            self._demand_from_grid.append(charge + demand)
            reward = -(charge + demand) * price
        
        self.render()

        # Update the timestep to return the next observation
        self._timestep += 1
        
        return (
            self._get_obs(), # Next observations
            reward,
            False, # terminated
            self._timestep == self._horizon, # truncated
            {} # no info
        )

    def render(self):
        if self.render_mode == 'none':
            return
        elif self.render_mode == 'console':
            print(f"State of Charge: {self._state_of_charge}")
            print(f"Demand: {self.demand(self._timestep)}")
            print(f"Price: {self.price(self._timestep)}")

    def close(self):
        pass
    

if __name__ == "__main__":
    num_steps = 100
    env = ElectricityMarketEnv()
    print(env.action_space.shape)