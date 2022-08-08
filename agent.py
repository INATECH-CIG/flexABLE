# -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 15:58:21 2020

@author: intgridnb-02
"""
from powerplant import Powerplant
import vrepowerplants
import storage
from SteelPlant import SteelPlant

class Agent():
    """
    The agent class is intented to represent a power plant or storage operator with at least one unit.
    This class allows to add different units to the agent, to request bids from each of the units 
    and to submit collected bids to corresponding markets.
    """

    def __init__(self, name, snapshots, world = None):
        self.name = name
        self.powerplants = {}
        self.storages = {}
        self.demand_units = {}
        self.world = world
        
        
    def addPowerplant(self, name, availability = None, **kwargs):
        self.powerplants[name] = Powerplant(name = name, 
                                                       world = self.world,
                                                       maxAvailability = availability, 
                                                       **kwargs)
        
        self.world.powerplants.append(self.powerplants[name])
        
        
    def addVREPowerplant(self, name, **kwargs):
        self.powerplants[name] = vrepowerplants.VREPowerplant(name = name, 
                                                              world = self.world, 
                                                              **kwargs)
        
        self.world.powerplants.append(self.powerplants[name])
    
    
    def addStorage(self, name, **kwargs):
        self.storages[name] = storage.Storage(name = name, 
                                              world=self.world, 
                                              **kwargs)
        
        self.world.storages.append(self.storages[name])

    def addDemand(self, name, **kwargs):
        self.demand_units[name] = SteelPlant(name = name, 
                                              world=self.world, 
                                              **kwargs)
        
        self.world.demand_units.append(self.demand_units[name])

        
        
    def calculateBid(self, t, market = "EOM"):
        bids = []
        
        for unit in self.powerplants.values():
            try:
                if t in unit.Availability:
                    continue
            except AttributeError:
                pass
            
            bids.extend(unit.requestBid(t, market))
            
        for unit in self.storages.values():
            bids.extend(unit.requestBid(t, market))
            
        return bids
    
    
    def requestBid(self, t, market = "EOM"):
        return self.calculateBid(t, market)
    
    