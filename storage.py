 # -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 16:06:57 2020

@author: intgridnb-02
"""
from auxFunc import initializer
from bid import Bid
import matplotlib.pyplot as plt


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
        self.dictEnergyCost[0] = self.world.dictPFC[0] * self.dictSOC[0]

        
        # performance parameter for ML
        self.performance = 0
        
        # Unit status parameters
        self.marketSuccess = [0]
        self.currentCapacity = 0
        self.Bids = {n:0 for n in self.world.snapshots}
        self.sentBids = []
    
        
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
        
        #check it again for crm prices
        self.dictEnergyCost[self.world.currstep] = -min(self.dictCapacity[self.world.currstep], 0) * self.world.dictPFC[self.world.currstep] * self.world.dt    
        
        if self.world.currstep < len(self.world.snapshots) - 1:
            if self.dictCapacity[self.world.currstep] >= 0:
                self.dictSOC[self.world.currstep + 1] = self.dictSOC[self.world.currstep] - (self.dictCapacity[self.world.currstep] / self.efficiency_discharge * self.world.dt)
            else:
                self.dictSOC[self.world.currstep + 1] = self.dictSOC[self.world.currstep] - (self.dictCapacity[self.world.currstep] * self.efficiency_charge * self.world.dt)
        else:
            if self.dictCapacity[self.world.currstep] >= 0:
                self.dictSOC[0] -= self.dictCapacity[self.world.currstep] / self.efficiency_discharge * self.world.dt
            else:
                self.dictSOC[0] += -self.dictCapacity[self.world.currstep] * self.efficiency_charge * self.world.dt
        
        if self.dictSOC[self.world.currstep] < 0:
            print('STOP!!!')
        
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
            
        elif market == "posCRMDemand": 
            bids.extend(self.calculatingBidsSTO_CRM_pos(t))

        elif market == "negCRMDemand":
            bids.extend(self.calculatingBidsSTO_CRM_neg(t))
            
        self.Bids[t] = bids
        return bids
      

    def marginalCostsFPP(self, t):
   
        
        marginalCosts = sum(self.dictEnergyCost.values()) + self.variableCosts_discharge
    
        
        return marginalCosts



    def calculateBidEOM(self, t):
        '''
        This is currently hard coded, but should be removed into input files
        '''
        bidsEOM = []
        
        bidQuantity_supply, bidPrice_supply, bidQuantity_demand, bidPrice_demand = 0,0,0,0
        
        
        bidQuantity_supply = min(max((self.dictSOC[t] - self.minSOC - self.confQtyCRM_pos[t] * self.world.dt) 
                                     * self.efficiency_discharge / self.world.dt,
                                     0), self.maxPower_discharge)
        
        if bidQuantity_supply >= self.world.minBidEOM:
            bidPrice_supply = -499.
        else:
            bidQuantity_supply = 0.0
            bidPrice_supply = 0.0
        
        if bidQuantity_supply != 0:
            bidsEOM.append(Bid(issuer = self,
                               ID = "Bu{}t{}_supplyEOM".format(self.name,t),
                               price = bidPrice_supply,
                               amount = bidQuantity_supply,
                               status = "Sent",
                               bidType = "Supply"))
        
        bidQuantity_demand = min(max((self.maxSOC - self.dictSOC[t] - 
                                     self.confQtyCRM_neg[t] * self.world.dt) / self.efficiency_charge / self.world.dt, 0),
                                 self.maxPower_charge)
        
        if bidQuantity_demand >= self.world.minBidEOM:
            bidPrice_demand = 2000.
        else:
            bidQuantity_demand = 0.0
            bidPrice_demand = 0.0
            

                
        if bidQuantity_demand !=0:
            bidsEOM.append(Bid(issuer = self,
                               ID = "Bu{}t{}_demandEOM".format(self.name,t),
                               price = bidPrice_demand,
                               amount = bidQuantity_demand,
                               status = "Sent",
                               bidType = "Demand"))

        return bidsEOM



    def calculatingBidsSTO_CRM_pos(self, t):
        bidsCRM = []
    
        availablePower_BP_pos = min(max((self.dictSOC[t] - self.minSOC) * self.efficiency_discharge / self.world.dt, 0),
                                    self.maxPower_discharge)
        
        specificRevenueEOM_dtau = self.specificRevenueEOM(t, 16, self.marginalCostsFPP(t), 'all')

        if availablePower_BP_pos >= self.world.minBidCRM and specificRevenueEOM_dtau >= 0:
            
            bidQuantityBPM_pos = availablePower_BP_pos
            capacityPrice = specificRevenueEOM_dtau * bidQuantityBPM_pos
            energyPrice = self.marginalCostsFPP(t)

            bidsCRM.append(Bid(issuer = self,
                               ID = "Bu{}t{}_CRMPosDem".format(self.name,t),
                               price = capacityPrice,
                               amount = bidQuantityBPM_pos,
                               energyPrice = energyPrice,
                               status = "Sent",
                               bidType = "Supply"))

        else:
            bidsCRM.append(Bid(issuer=self,
                               ID="Bu{}t{}_CRMPosDem".format(self.name,t),
                               price = 0,
                               amount = 0,
                               energyPrice = 0,
                               status = "Sent",
                               bidType = "Supply"))
            
    
        return bidsCRM
    

    def calculatingBidsSTO_CRM_neg(self, t):
        bidsCRM = []
        
        availablePower_BP_neg = min(max((self.maxSOC - self.dictSOC[t]) / self.efficiency_charge / self.world.dt, 0),
                                    self.maxPower_charge)
        
        specificRevenueEOM_dtau = self.specificRevenueEOM(t, 16, self.marginalCostsFPP(t), 'all')

        if availablePower_BP_neg >= self.world.minBidCRM:
            
            bidQtyCRM_neg = availablePower_BP_neg
            capacityPrice = abs(specificRevenueEOM_dtau * bidQtyCRM_neg)
            energyPrice = - self.marginalCostsFPP(t)

            bidsCRM.append(Bid(issuer = self,
                               ID = "Bu{}t{}_CRMNegDem".format(self.name,t),
                               price = capacityPrice,
                               amount = bidQtyCRM_neg,
                               energyPrice = energyPrice,
                               status = "Sent",
                               bidType = "Supply"))

        else:
            bidsCRM.append(Bid(issuer = self,
                               ID = "Bu{}t{}_CRMNegDem".format(self.name,t),
                               price = 0,
                               amount = 0,
                               energyPrice = 0,
                               status = "Sent",
                               bidType = "Supply"))
            
    
        return bidsCRM


    def specificRevenueEOM(self,t, foresight, marginalCosts, horizon):
        listPFC = self.getPart_PFC(t, foresight)
    
        if horizon == 'positive':
            specificRevenue_sum = round(sum([(marketPrice - marginalCosts) * self.world.dt for position, [tick, marketPrice]
                                             in enumerate(listPFC) if marginalCosts < marketPrice]), 2)
        elif horizon == 'negative':
            specificRevenue_sum = round(sum([(marketPrice - marginalCosts) * self.world.dt for position, [tick, marketPrice]
                                             in enumerate(listPFC) if marginalCosts > marketPrice]), 2)
        else:
            specificRevenue_sum = round(sum([(marketPrice - marginalCosts) * self.world.dt for position, [tick, marketPrice]
                                             in enumerate(listPFC)]), 2)
    
        return specificRevenue_sum
    
    
    def getPart_PFC(self, t, foresight):
        listPFC = []
        lengthPFC = len(self.world.dictPFC)
    
        if (t + foresight) > lengthPFC:
            overhang = (t + foresight) - lengthPFC
            for tick in range(t, lengthPFC):  # verbleibende Marktpreise in der PFC
                listPFC.append([int(tick), float(round(self.world.dictPFC[tick], 2))])
            for tick in range(0, overhang):  # Auffüllen mit Preisen vom Anfang der PFC
                listPFC.append([int(lengthPFC + tick), float(round(self.world.dictPFC[tick], 2))])
        else:
            for tick in range(t, int(t + foresight)):
                listPFC.append([int(tick), float(round(self.world.dictPFC[tick], 2))])
    
        return listPFC
    
    
    def plotResults(self):
        plt.figure()
        plt.plot(range(len(self.world.snapshots)), list(self.dictCapacity.values()))
        plt.ylabel('Power [MW]')
        plt.title(self.name)
        plt.show()
        
        plt.figure()
        plt.plot(range(len(self.world.snapshots)), list(self.dictSOC.values()))
        plt.ylabel('SOC [MWh]')
        plt.title(self.name)
        plt.show()
        
        