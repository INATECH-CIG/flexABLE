# -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 15:58:21 2020

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
        
    def calculateBid(self,t, market="EOM"):
        bids = []
        for unit in self.powerplants.values():
            bids.extend(unit.requestBid(t, market))
        return bids
    
    def requestBid(self,t, market="EOM"):
        self.bids[t]= self.calculateBid(t, market)
        return self.bids[t]