# -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 15:58:21 2020

@author: intgridnb-02
"""
from . import powerplant
from . import vrepowerplants
from . import storage
from .bid import Bid

class Agent():
    
    def __init__(self, name, snapshots, world=None):
        self.name = name
        self.powerplants = {}
        self.storages = {}
        
        #self.bids = {t:{} for t in snapshots}
        self.world = world
        
    def addPowerplant(self, name, availability=None,**kwargs):
        self.powerplants[name] = powerplant.Powerplant(name=name, world=self.world, maxAvailability=availability, **kwargs)
        self.world.powerplants.append(self.powerplants[name])
        
    def addVREPowerplant(self, name,**kwargs):
        self.powerplants[name] = vrepowerplants.VREPowerplant(name=name, world=self.world, **kwargs)
        self.world.powerplants.append(self.powerplants[name])
    
    def addStorage(self, name,**kwargs):
        self.storages[name] = storage.Storage(name=name, world=self.world, **kwargs)
        self.world.storages.append(self.storages[name])
        
    def calculateBid(self,t, market="EOM"):
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
    
    def requestBid(self,t, market="EOM"):
        return self.calculateBid(t, market)