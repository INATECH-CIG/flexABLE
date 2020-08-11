 # -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 16:06:57 2020

@author: intgridnb-02
"""
from auxFunc import initializer
from bid import Bid
import matplotlib.pyplot as plt
import numpy as np


class Storage():
    
    @initializer
    def __init__(self,agent=None,
                name = 'Storage_1',
                technology = 'PSPP',
                maxPower_charge = 100,
                maxPower_discharge = 100,
                efficiency_charge = 0.8,
                efficiency_discharge = 0.9,              
                minSOC = 0,
                maxSOC = 1000,
                variableCosts_charge = 0.28,
                variableCosts_discharge = 0.28,
                natural_inflow = 1.8, # [MWh/qh]
                company = 'UNIPER',
                world = None, **kwargs):

        # bids status parameters
        self.dictSOC = {n:0 for n in self.world.snapshots}
        self.dictSOC[0] = self.maxSOC * 0.5 #we start at 50% of storage capacity
        self.dictCapacity = {n:0 for n in self.world.snapshots}       
        self.confQtyCRM_neg = {n:0 for n in self.world.snapshots}
        self.confQtyCRM_pos = {n:0 for n in self.world.snapshots}
        self.dictEnergyCost = {n:0 for n in self.world.snapshots}
        self.dictEnergyCost[0] = -self.world.dictPFC[0] * self.dictSOC[0]

        
        # performance parameter for ML
        self.performance = 0
        
        # Unit status parameters
        self.marketSuccess = [0]
        self.currentCapacity = 0
        self.Bids = {"EOM":{t:0 for t in self.world.snapshots},
                     "posCRMDemand":{t:0 for t in self.world.snapshots},
                     "negCRMDemand":{t:0 for t in self.world.snapshots}}
        self.sentBids = []
        self.foresight = int(6/self.world.dt)

    
        
    def step(self):
        # Calculate the sum of confirmed bids

        self.dictCapacity[self.world.currstep] = 0
            
        for bid in self.sentBids:
            if 'supplyEOM' in bid.ID in bid.ID:
                self.dictCapacity[self.world.currstep] += bid.confirmedAmount
            if 'demandEOM' in bid.ID:
                self.dictCapacity[self.world.currstep] -= bid.confirmedAmount
               
        
        self.sentBids=[]
        self.dictCapacity[self.world.currstep] += self.confQtyCRM_pos[self.world.currstep]
        self.dictCapacity[self.world.currstep] -= self.confQtyCRM_neg[self.world.currstep]
                
        if self.world.currstep < len(self.world.snapshots) - 1:
            if self.dictCapacity[self.world.currstep] >= 0:
                self.dictSOC[self.world.currstep + 1] = self.dictSOC[self.world.currstep] - (self.dictCapacity[self.world.currstep] / self.efficiency_discharge * self.world.dt)
                self.dictEnergyCost[self.world.currstep + 1] = self.dictEnergyCost[self.world.currstep] + self.dictCapacity[self.world.currstep] * self.world.dictPFC[self.world.currstep] * self.world.dt    
            else:
                self.dictSOC[self.world.currstep + 1] = self.dictSOC[self.world.currstep] - (self.dictCapacity[self.world.currstep] * self.efficiency_charge * self.world.dt)
                self.dictEnergyCost[self.world.currstep + 1] = self.dictEnergyCost[self.world.currstep] - self.dictCapacity[self.world.currstep] * self.world.dictPFC[self.world.currstep] * self.world.dt    

            self.dictSOC[self.world.currstep + 1] = max(self.dictSOC[self.world.currstep + 1], 0)
        else:
            if self.dictCapacity[self.world.currstep] >= 0:
                self.dictSOC[0] -= self.dictCapacity[self.world.currstep] / self.efficiency_discharge * self.world.dt
            else:
                self.dictSOC[0] += -self.dictCapacity[self.world.currstep] * self.efficiency_charge * self.world.dt
        
        # Calculates market success
        if self.dictCapacity[self.world.currstep] > 0:
            self.marketSuccess[-1] += 1
        else:
            self.marketSuccess.append(0)
        
        

    def feedback(self, bid):
        if bid.status == "Confirmed":
            if 'CRMPosDem' in bid.ID:
                self.confQtyCRM_pos[self.world.currstep] = bid.confirmedAmount
            if 'CRMNegDem' in bid.ID:
                self.confQtyCRM_neg[self.world.currstep] = bid.confirmedAmount
            self.performance+=1
        elif bid.status =="PartiallyConfirmed":
            if 'CRMPosDem' in bid.ID:
                self.confQtyCRM_pos[self.world.currstep] = bid.confirmedAmount
            if 'CRMNegDem' in bid.ID:
                self.confQtyCRM_neg[self.world.currstep] = bid.confirmedAmount
            self.performance+=0.5
        else:
            self.performance-=2
            
        self.sentBids.append(bid)


    def requestBid(self, t, market="EOM"):
        bids = []
        
        if market == "EOM":
            bids.extend(self.calculateBidEOM(t))
            self.Bids[market][t] = bids
            
        elif market == "posCRMDemand": 
            bids.extend(self.calculatingBidsSTO_CRM_pos(t))
            self.Bids[market][t] = bids

        elif market == "negCRMDemand":
            bids.extend(self.calculatingBidsSTO_CRM_neg(t))
            self.Bids[market][t] = bids
            
        # self.Bids[market][t] = bids
        return bids
      



    def calculateBidEOM(self, t, passedSOC = None):
        '''
        This is currently hard coded, but should be removed into input files
        '''
        
        SOC = self.dictSOC[t] if passedSOC == None else passedSOC
        bidsEOM = []
        
        
        if t >= len(self.world.snapshots):
            t -= len(self.world.snapshots)
            
        if t-self.foresight < 0:
            averagePrice = np.mean(self.world.dictPFC[t-self.foresight:] + self.world.dictPFC[0:t+self.foresight])
        elif t+self.foresight > len(self.world.snapshots):
            averagePrice = np.mean(self.world.dictPFC[t-self.foresight:] + self.world.dictPFC[:t+self.foresight-len(self.world.snapshots)])
        else:
            averagePrice = np.mean(self.world.dictPFC[t-self.foresight:t+self.foresight])
            
            
        if self.world.dictPFC[t] >= 1.1 * averagePrice:
            bidQuantity_supply = min(max((SOC - self.minSOC - self.confQtyCRM_pos[t] * self.world.dt)
                                         * self.efficiency_discharge / self.world.dt,
                                         0), self.maxPower_discharge)
            
            bidPrice_supply = averagePrice
            
            if bidQuantity_supply >= self.world.minBidEOM:
                bidsEOM.append(Bid(issuer = self,
                                   ID = "{}_supplyEOM".format(self.name),
                                   price = bidPrice_supply,
                                   amount = bidQuantity_supply,
                                   status = "Sent",
                                   bidType = "Supply"))
            
        elif self.world.dictPFC[t] <= 0.9 * averagePrice:

            bidQuantity_demand = min(max((self.maxSOC - SOC - 
                                         self.confQtyCRM_neg[t] * self.world.dt) / self.efficiency_charge / self.world.dt, 0),
                                     self.maxPower_charge)
            
            bidPrice_demand = averagePrice 
            
            if bidQuantity_demand >= self.world.minBidEOM:
                bidsEOM.append(Bid(issuer = self,
                                   ID = "{}_demandEOM".format(self.name),
                                   price = bidPrice_demand,
                                   amount = bidQuantity_demand,
                                   status = "Sent",
                                   bidType = "Demand"))

        return bidsEOM


    def calculatingBidPricesSTO_CRM(self, t):
        fl = int(4 / self.world.dt)
        theoreticalSOC = self.dictSOC[t]
        theoreticalRevenue = []
        
        for tick in range(t, t + fl):
            BidSTO_EOM = self.calculateBidEOM(tick, theoreticalSOC)
            if len(BidSTO_EOM) != 0:
                BidSTO_EOM = BidSTO_EOM[0]
                if BidSTO_EOM.bidType == 'Supply':
                    theoreticalSOC -= BidSTO_EOM.amount / self.efficiency_discharge * self.world.dt
                    theoreticalRevenue.append(self.world.dictPFC[t] * BidSTO_EOM.amount * self.world.dt)
                elif BidSTO_EOM.bidType == 'Demand':
                    theoreticalSOC += BidSTO_EOM.amount * self.efficiency_charge * self.world.dt
                    theoreticalRevenue.append(- self.world.dictPFC[t] * BidSTO_EOM.amount * self.world.dt)
            else:
                continue
        
        capacityPrice = abs(sum(theoreticalRevenue))
        energyPrice = -self.dictEnergyCost[self.world.currstep] / self.dictSOC[t]
        return capacityPrice, energyPrice


    
    def calculatingBidsSTO_CRM_pos(self, t):
        bidsCRM = []
        
        availablePower_BP_pos = min(max((self.dictSOC[t] - self.minSOC) * self.efficiency_discharge / self.world.dt, 0),
                                    self.maxPower_discharge)
        
        if availablePower_BP_pos >= self.world.minBidCRM:
            
            bidQuantityBPM_pos = availablePower_BP_pos
            capacityPrice, energyPrice = self.calculatingBidPricesSTO_CRM(t)
            
            bidsCRM.append(Bid(issuer = self,
                               ID = "{}_CRMPosDem".format(self.name),
                               price = capacityPrice,
                               amount = bidQuantityBPM_pos,
                               energyPrice = energyPrice,
                               status = "Sent",
                               bidType = "Supply"))

        else:
            bidsCRM.append(Bid(issuer=self,
                               ID="{}_CRMPosDem".format(self.name),
                               price = 0,
                               amount = 0,
                               energyPrice = 0,
                               status = "Sent",
                               bidType = "Supply"))
            

        return bidsCRM
    

    def calculatingBidsSTO_CRM_neg(self, t):
        bidsCRM = []
        
        availablePower_BP_neg = min(max((self.maxSOC - abs(self.dictSOC[t])) / self.efficiency_charge / self.world.dt, 0),
                                    self.maxPower_charge)
        
        if availablePower_BP_neg >= self.world.minBidCRM:
            
            bidQtyCRM_neg = availablePower_BP_neg
            #self.calculatingBidPricesSTO_CRM(t)


            bidsCRM.append(Bid(issuer = self,
                               ID = "{}_CRMNegDem".format(self.name),
                               price = 0,
                               amount = bidQtyCRM_neg,
                               energyPrice = 0,
                               status = "Sent",
                               bidType = "Supply"))

        else:
            bidsCRM.append(Bid(issuer = self,
                               ID = "{}_CRMNegDem".format(self.name),
                               price = 0,
                               amount = 0,
                               energyPrice = 0,
                               status = "Sent",
                               bidType = "Supply"))
            
        
        return bidsCRM

    
    
    def getPart_PFC(self, t, foresight):
        listPFC = []
        lengthPFC = len(self.world.dictPFC)
    
        if (t + foresight) > lengthPFC:
            overhang = (t + foresight) - lengthPFC
            for tick in range(t, lengthPFC):  # verbleibende Marktpreise in der PFC
                listPFC.append([int(tick), float(round(self.world.dictPFC[tick], 2))])
            for tick in range(0, overhang):  # Auffüllen mit Preisen vom Anfang der PFC
                listPFC.append([int(lengthPFC + tick), float(round(self.world.dictPFC[tick], 2))])
        elif t < 0:
            for tick in range(t, 0):
                listPFC.append([int(tick), float(round(self.world.dictPFC[len(self.world.dictPFC)+tick], 2))])
            for tick in range(0, int(t + foresight)):
                listPFC.append([int(tick), float(round(self.world.dictPFC[tick], 2))])
        else:
            for tick in range(t, int(t + foresight)):
                listPFC.append([int(tick), float(round(self.world.dictPFC[tick], 2))])
    
        return listPFC
    
    
    def plotResults(self):      
        plt.figure()
        plt.plot(range(len(self.world.snapshots)), list(self.dictSOC.values()))
        plt.ylabel('SOC [MWh]')
        plt.title(self.name)
        plt.show()
        
        plt.figure()
        plt.step(range(len(self.world.snapshots)), list(self.dictCapacity.values()), label='Total Capacity')
        plt.step(range(len(self.world.snapshots)), [-_ for _ in list(self.confQtyCRM_neg.values())], label='Negative CRM')
        plt.step(range(len(self.world.snapshots)), list(self.confQtyCRM_pos.values()), label='Positive CRM')
        plt.ylabel('Power [MW]')
        plt.title(self.name)
        plt.legend()
        plt.show()
        
        