# -*- coding: utf-8 -*-
"""
Created on Mon Apr  6 16:05:06 2020

@author: intgridnb-02
"""
import powerplant
import vrepowerplants
from bid import Bid

class Agent():
    
    def __init__(self, name, snapshots, world=None):
        self.name = name
        self.powerplants = {}
        
        self.bids = {t:{} for t in snapshots}
        self.world = world
        
    def addPowerplant(self, name,**kwargs):
        self.powerplants[name] = powerplant.Powerplant(name=name, world=self.world, **kwargs)
        self.world.powerplants.append(self.powerplants[name])
        
    def addVREPowerplant(self, name,**kwargs):
        self.powerplants[name] = vrepowerplants.VREPowerplant(name=name, world=self.world, **kwargs)
        self.world.powerplants.append(self.powerplants[name])
        
    def calculateBid(self,t):
        bids = []
        for unit in self.powerplants.values():
            bids.extend(unit.requestBid(t))
        return bids
    
    def requestBid(self,t):
        self.bids[t]= self.calculateBid(t)
        return self.bids[t]