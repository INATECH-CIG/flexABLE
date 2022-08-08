#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jun  2 09:09:16 2020

@author: intgridnb-02
"""

class MeritOrder():
    def __init__(self, demand, powerplantsList, vrepowerplantFeedIn, fuelPrices, emissionFactors, snapshots):

        self.snapshots = snapshots

        self.demand = list(demand.values)
        
        self.powerplants = powerplantsList
        self.renewableSupply = vrepowerplantFeedIn
        
        self.fuelPrices = fuelPrices
        self.emissionFactors = emissionFactors
        self.co2price = fuelPrices['co2']
        
        
    # =============================================================================
    # Marginal Cost
    # =============================================================================
    def marginalCost(self, powerplant, t):

        fuelPrice = self.fuelPrices[powerplant.fuel][t]
        co2price = self.co2price[t]
        emissionFactor = self.emissionFactors[powerplant.fuel]
        
        marginalCosts = (fuelPrice / powerplant.efficiency) + (co2price * (emissionFactor / powerplant.efficiency)) + powerplant.variableCosts
        
        return marginalCosts
    
    
    def meritOrder(self, demand, renewableSupply, t):
        
        powerplants = self.powerplants
        powerplants['marginalCost'] = 0.
        powerplants['marginalCost'] = powerplants.apply(self.marginalCost, axis = 1, t = t)
        
        powerplants.sort_values('marginalCost', inplace=True)
                
        contractedSupply = renewableSupply
        mcp = 0
        
        if sum(powerplants.maxPower) < demand:
            # print('Contracted energy was not enough!')
            mcp = 1000
        elif renewableSupply >= demand:
            mcp = -500
        else:
            for i, power in enumerate(powerplants.maxPower):
                if contractedSupply >= demand:
                    mcp = powerplants['marginalCost'].iat[i]
                    break
                
                if contractedSupply < demand:
                    contractedSupply += power 
                    
        return mcp
    
    
    def PFC(self):
        pfc = []
        
        for t in range(len(self.snapshots)):
            pfc.append(self.meritOrder(self.demand[t], sum(self.renewableSupply.iloc[t]), t))
            
        return pfc
