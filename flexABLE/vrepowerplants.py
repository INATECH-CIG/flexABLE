# -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 17:04:23 2020

@author: intgridnb-02
"""
from .auxFunc import initializer
from .bid import Bid

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
        
        self.dictCapacity = {n:None for n in self.world.snapshots}
        self.dictCapacity[self.world.snapshots[0]] = self.maxPower
        self.dictCapacity[-1] = self.maxPower
        self.dictCapacityRedis = {n:0 for n in self.world.snapshots}
        self.dictCapacityMR = {n:(0,0) for n in self.world.snapshots}
        self.dictCapacityFlex = {n:(0,0) for n in self.world.snapshots}
        
        # Unit status parameters
        self.sentBids=[]
        self.sentBids_dict= {}
        
        
    def step(self):
        self.dictCapacity[self.world.currstep] = 0
        
        for bid in self.sentBids:
            self.dictCapacity[self.world.currstep] += bid.confirmedAmount
            if 'mrEOM' in bid.ID:
                self.dictCapacityMR[self.world.currstep] = (bid.confirmedAmount, bid.price)
                
            else:
                self.dictCapacityFlex[self.world.currstep] = (bid.confirmedAmount, bid.price)
                
        self.sentBids=[]
        
        
    def feedback(self, bid):
        self.sentBids.append(bid)
        
        
    def requestBid(self, t, market):
        bids=[]
        bidQuantity_mr, bidPrice_mr = self.calculateBidEOM(t)
        
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
    
    
    def calculateBidEOM(self, t):
        marginalCost = 0 if 'Biomass' in self.name else -500

        return self.dictFeedIn[t], marginalCost
    
    
    def checkAvailability(self, t):
        pass

