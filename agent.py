# -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 15:58:21 2020

@author: intgridnb-02
"""
import torch as th
import numpy as np

from powerplant import Powerplant
from vrepowerplants import VREPowerplant
from storage import Storage
from optstorage import OptStorage
from rlpowerplant import RLPowerplant
from rlstorage import RLStorage
from SteelPlant import SteelPlant
from bid import Bid

#%%

class Agent():
    """
    The agent class is intented to represent a power plant or storage operator with at least one unit.
    This class allows to add different units to the agent, to request bids from each of the units 
    and to submit collected bids to corresponding markets.
    """

    def __init__(self, name, world = None):
        self.world = world
        self.name = name

        self.conv_powerplants = {}
        self.vre_powerplants = {}
        self.rl_powerplants = {}
        self.storages = {}
        self.rl_storages = {}
        self.dsm_units = {}
        self.rl_agent = False


    def initialize(self, t = 0):
        if self.rl_agent:
            self.create_obs(t)

        for unit in self.conv_powerplants.values():
            unit.reset()
        
        for unit in self.storages.values():
            unit.reset()

        for unit in self.rl_powerplants.values():
            unit.reset()

        for unit in self.rl_storages.values():
            unit.reset()

        for unit in self.dsm_units.values():
            unit.reset()
             
    def add_conv_powerplant(self, name, availability = None, **kwargs):
        self.conv_powerplants[name] = Powerplant(name=name,
                                                 agent=self,
                                                 world=self.world,
                                                 maxAvailability=availability,
                                                 **kwargs)

        self.world.powerplants.append(self.conv_powerplants[name])
        
    
    def add_rl_powerplant(self, name, availability = None, **kwargs):
        if len(self.rl_powerplants) == 0:
            self.rl_agent = True

        self.rl_powerplants[name] = RLPowerplant(name=name,
                                                 agent=self,
                                                 world=self.world,
                                                 maxAvailability=availability,
                                                 **kwargs)

        
        self.world.rl_powerplants.append(self.rl_powerplants[name])
        
        
    def add_vre_powerplant(self, name, **kwargs):
        self.vre_powerplants[name] = VREPowerplant(name=name,
                                                   agent=self,
                                                   world=self.world,
                                                   **kwargs)

        self.world.vre_powerplants.append(self.vre_powerplants[name])
    
    
    def add_storage(self, name, opt_storages, **kwargs):
        if opt_storages:
            self.storages[name] = OptStorage(name=name,
                                            agent=self,
                                            world=self.world,
                                            **kwargs)
        else:  
            self.storages[name] = Storage(name=name,
                                        agent=self,
                                        world=self.world,
                                        **kwargs)

        self.world.storages.append(self.storages[name])


    def add_rl_storage(self, name, availability = None, **kwargs):
        if len(self.rl_storages) == 0:
            self.rl_agent = True

        self.rl_storages[name] = RLStorage(name=name,
                                           agent=self,
                                           world=self.world,
                                           maxAvailability=availability,
                                           **kwargs)

        
        self.world.rl_storages.append(self.rl_storages[name])

    def add_dsm_unit(self, name, **kwargs):
        self.dsm_units[name] = SteelPlant(name=name,
                                                   agent=self,
                                                   world=self.world,
                                                   **kwargs)

        self.world.dsm_units.append(self.dsm_units[name])
        
    def calculate_conv_bids(self, t, market = "EOM"):
        for unit in self.conv_powerplants.values():
            try:
                if t in unit.Availability:
                    continue
            except AttributeError:
                pass
            
            self.bids.extend(unit.formulate_bids(t, market))

        for unit in self.vre_powerplants.values():
            self.bids.extend(unit.formulate_bids(t, market))

        for unit in self.storages.values():
            self.bids.extend(unit.formulate_bids(t, market))

        for unit in self.dsm_units.values():
            self.bids.extend(unit.formulate_bids(t, market))

    def calculate_rl_bids(self):
        actions = th.zeros(size=(len(self.rl_powerplants)+len(self.rl_storages),self.world.act_dim),
                           device=self.world.device)

        for i, unit in enumerate((self.rl_powerplants|self.rl_storages).values()):
            actions[i, :] = unit.formulate_bids()
        
        actions = actions.clamp(-1, 1)
        actions = actions.squeeze().cpu().numpy()
        actions = actions.reshape(len(self.rl_powerplants)+len(self.rl_storages),-1)
        
        if np.isnan(actions).any():
            raise ValueError('A NaN actions happened.')
        
        for i, unit in enumerate((self.rl_powerplants|self.rl_storages).values()):
            if unit.technology in ['PSPP', 'Storage', 'BES']:
                bid_price = actions[i, 0]*100

                bid_direction = 'sell' if actions[i, 1]>=0 else 'buy'

                bid_quantity_supply = min(max((unit.soc[self.world.currstep] - unit.min_soc)*unit.efficiency_dis/self.world.dt, 0),
                                          unit.max_power_dis)

                bid_quantity_demand = min(max((unit.max_soc - unit.soc[self.world.currstep])/unit.efficiency_ch/self.world.dt, 0),
                                          unit.max_power_ch)

                if bid_quantity_supply >= self.world.minBidEOM and bid_direction == 'sell':
                    self.bids.append(Bid(issuer=unit,
                                         ID="{}_supplyEOM".format(self.name),
                                         price=bid_price,
                                         amount=bid_quantity_supply,
                                         status="Sent",
                                         bidType="Supply",
                                         node=unit.node))

                if bid_quantity_demand >= self.world.minBidEOM and bid_direction == 'buy':
                    self.bids.append(Bid(issuer=unit,
                                         ID="{}_demandEOM".format(self.name),
                                         price=bid_price,
                                         amount=bid_quantity_demand,
                                         status="Sent",
                                         bidType="Demand",
                                         node=unit.node))

            else:
                # bid_price_mr = unit.marginal_cost[self.world.currstep] + actions[i, :].min()*100
                # bid_price_flex = unit.marginal_cost[self.world.currstep] + actions[i, :].max()*100
            
                bid_price_mr = actions[i, :].min()*100
                bid_price_flex = actions[i, :].max()*100
                bid_quantity_mr, bid_quantity_flex = unit.minPower, unit.maxPower - unit.minPower
                
                self.bids.append(Bid(issuer = unit,
                                ID = "{}_mrEOM".format(unit.name),
                                price = bid_price_mr,
                                amount = bid_quantity_mr,
                                status = "Sent",
                                bidType = "Supply",
                                node = unit.node))
                
                self.bids.append(Bid(issuer = unit,
                                ID = "{}_flexEOM".format(unit.name),
                                price = bid_price_flex,
                                amount = bid_quantity_flex,
                                status = "Sent",
                                bidType = "Supply",
                                node = unit.node))

    
    def request_bids(self, t, market = "EOM"):
        self.bids = []
        self.calculate_conv_bids(t, market)
        if self.rl_agent:
            self.calculate_rl_bids()

        return self.bids


    def step(self):
        if self.rl_agent:
            self.create_obs(self.world.currstep+1)

        for powerplant in self.conv_powerplants.values():
            powerplant.step()

        for powerplant in self.rl_powerplants.values():
            powerplant.step()

        for powerplant in self.vre_powerplants.values():
            powerplant.step()

        for storage in self.storages.values():
            storage.step()

        for storage in self.rl_storages.values():
            storage.step()
        
        for unit in self.dsm_units.values():
            unit.step()

    def check_availability(self):
        for pp in self.conv_powerplants.values():
            pp.check_availability(self.world.currstep)

        for pp in self.vre_powerplants.values():
            pp.check_availability(self.world.currstep)


    def create_obs(self, t):
        obs = []
        forecast_len = 30
        
        #get the demand and forecasted demand
        if t < forecast_len:
            obs.extend(self.world.scaled_res_load[-forecast_len+t:])
            obs.extend(self.world.scaled_res_load_forecast[:t+forecast_len])
            
        elif t >= forecast_len and t < len(self.world.snapshots)-forecast_len:
            obs.extend(self.world.scaled_res_load[t-forecast_len:t])
            obs.extend(self.world.scaled_res_load_forecast[t:t+forecast_len])
            
        else:
            obs.extend(self.world.scaled_res_load[t-forecast_len:])
            obs.extend(self.world.scaled_res_load_forecast[:forecast_len*2-len(obs)])
        
        
        #get the previous price and price forecast
        if t < forecast_len:
            obs.extend(self.world.scaled_mcp[-forecast_len+t:])
            obs.extend(self.world.scaled_pfc[:t+forecast_len])
            
        elif t >= forecast_len and t < len(self.world.snapshots)-forecast_len:
            obs.extend(self.world.scaled_mcp[t-forecast_len:t])
            obs.extend(self.world.scaled_pfc[t:t+forecast_len])
            
        else:
            obs.extend(self.world.scaled_mcp[t-forecast_len:])
            obs.extend(self.world.scaled_pfc[:forecast_len*4-len(obs)])
            
        self.obs = obs

            