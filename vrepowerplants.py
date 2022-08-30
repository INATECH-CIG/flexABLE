# -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 17:04:23 2020

@author: intgridnb-02
"""
from misc import initializer
from bid import Bid

class VREPowerplant():
    
    @initializer
    def __init__(self,
                 agent = None,
                 name = 'KKW ISAR 2',
                 technology = 'Renewable',
                 maxPower = 1500,
                 minPower = 0,
                 variableCosts = 10.3,
                 heatExtraction=False,
                 maxExtraction=0,
                 heatingDistrict='BW',
                 company = 'UNIPER',
                 year = 1988,
                 node = 'Bus_DE',
                 world = None,
                 FeedInTimeseries = 0):
        
        # bids status parameters
        self.dictFeedIn = {n:m for n,m in zip(self.world.snapshots,FeedInTimeseries)}
        
        self.total_capacity = [0. for _ in self.world.snapshots]
        self.total_capacity[self.world.snapshots[0]] = self.maxPower
        self.total_capacity[-1] = self.maxPower

        self.bids_mr = {n:(0,0) for n in self.world.snapshots}
        self.bids_flex = {n:(0,0) for n in self.world.snapshots}

        self.rewards = [0. for _ in self.world.snapshots]
        self.regrets = [0. for _ in self.world.snapshots]
        self.profits = [0. for _ in self.world.snapshots]

        # Unit status parameters
        self.sentBids=[]
        
        
    def step(self):
        self.total_capacity[self.world.currstep] = 0
        
        for bid in self.sentBids:
            self.total_capacity[self.world.currstep] += bid.confirmedAmount
            if 'mrEOM' in bid.ID:
                self.bids_mr[self.world.currstep] = (bid.confirmedAmount, bid.price) 
            else:
                self.bids_flex[self.world.currstep] = (bid.confirmedAmount, bid.price)
                
        self.sentBids=[]
        
        
    def feedback(self, bid):
        self.sentBids.append(bid)
        
        
    def formulate_bids(self, t, market):
        bids=[]
        bidQuantity_mr, bidPrice_mr = self.calculate_bids_EOM(t)
        
        if market=="EOM":
            if bidQuantity_mr != 0:
                bids.append(Bid(issuer = self,
                                ID = "{}_mrEOM".format(self.name),
                                price = bidPrice_mr,
                                amount = bidQuantity_mr,
                                status = "Sent",
                                bidType = "Supply",
                                node = self.node))

        return bids
    
    
    def calculate_bids_EOM(self, t):
        marginalCost = -90 if 'Biomass' in self.name else 0
        
        return self.dictFeedIn[t], marginalCost
    
    
    def check_availability(self, t):
        pass

