# -*- coding: utf-8 -*-
"""
Created on Thu Jun  4 14:05:15 2020

@author: intgridnb-02
"""
import pypsa

class NetworkOperator():
    '''
    This class represents a network operator responsible to insure the feasibility
    of solutions respecting network constraints, and performs re-dispatch measures
    if required
    '''
    def __init__(self, importCSV=True, world=None):
        self.world = world
        #network = pypsa.Network()
        #network.set_snapshots(self.world.snapshots)
                
        # Adding buses to the network
        
        # To get the economical dispatch this could be done
    def checkFeasibility():
        pass
        #{_.name:_.dictCapacity[example.currstep-1] for _ in self.world.powerplants }
    
    def step(self):
        #self.world.powerplants[0].currentStatus=0
        return 0
        for powerplant in self.world.powerplants:
            powerplant.currentStatus = 0