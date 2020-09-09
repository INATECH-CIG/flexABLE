# -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 17:04:23 2020

@author: intgridnb-02
"""
from auxFunc import initializer
from bid import Bid
import random
import pandas

class VREPowerplant():
    
    @initializer
    def __init__(self,agent=None,
                name='KKW ISAR 2',
                technology='nuclear',
                fuel='uranium',
                maxPower=1500,
                minPower=0,
                efficiency=0.3,
                rampUp=0,
                rampDown=0,
                variableCosts=10.3,
                hotStartCosts=140,
                warmStartCosts=140,
                coldStartCosts=140,
                minOperatingTime=72,
                minDowntime=10,
                heatExtraction=False,
                maxExtraction=0,
                heatingDistrict='BW',
                company='UNIPER',
                year=1988,
                node='Bus_DE',
                world=None,
                FeedInTimeseries=0):

        # bids status parameters
        self.dictFeedIn = {n:m for n,m in zip(self.world.snapshots,FeedInTimeseries)}
        self.dictCapacity = {n:None for n in self.world.snapshots}
        self.dictCapacity[self.world.snapshots[0]] = self.maxPower
        self.dictCapacity[-1] = self.maxPower
        self.confQtyCRM_neg = {n:0 for n in self.world.snapshots}
        self.confQtyCRM_pos = {n:0 for n in self.world.snapshots}
        self.confQtyDHM_steam = {n:0 for n in self.world.snapshots}
        self.powerLoss_CHP = {n:0 for n in self.world.snapshots}
        
        # performance parameter for ML
        self.performance = 0
        # Unit status parameters
        self.marketSuccess = [0]
        self.currentDowntime = 0 # Keeps track of the powerplant if it reached the minimum shutdown time
        self.currentStatus = 1 # 0 means the power plant is currently off, 1 means it is on
        self.averageDownTime = 0 # average downtime during the simulation
        self.currentCapacity = 0
        self.sentBids=[]
        
    def step(self):
        self.dictCapacity[self.world.currstep] = 0
        for bid in self.sentBids:
            self.dictCapacity[self.world.currstep] += bid.confirmedAmount
        self.sentBids=[]

    def feedback(self, bid):
        if bid.status == "Confirmed": 
            self.performance+=1
        elif bid.status =="PartiallyConfirmed":
            self.performance+=0.5
        else:
            self.performance-=2
            
        self.sentBids.append(bid)
        
    def requestBid(self, t, market):
        bids=[]
        bidQuantity_mr, bidPrice_mr = self.calculateBidEOM(t)
        if market=="EOM":
            if bidQuantity_mr != 0:
                bids.append(Bid(issuer = self,
                                ID = "{}".format(self.name,t),
                                price = bidPrice_mr,
                                amount = bidQuantity_mr,
                                status = "Sent",
                                bidType = "Supply",
                                node = self.node,
                                redispatch_price=-100))

        return bids
    
    def calculateBidEOM(self, t):
        return self.dictFeedIn[t],-500