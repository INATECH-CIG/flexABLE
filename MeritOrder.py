#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jun  2 09:09:16 2020

@author: intgridnb-02
"""
from tqdm import tqdm

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


if __name__ == "__main__":
    import pandas as pd
    scenario = 2019
    startingPoint=0
    length=35040
    
    snapshots = list(range(startingPoint,length))
    demand = pd.read_csv('input/{}/IED_DE.csv'.format(scenario),
                         index_col=0,
                         nrows=len(snapshots)+startingPoint,
                         encoding="Latin-1")
    powerplantsList = pd.read_csv('input/{}/FPP_DE.csv'.format(scenario),
                          index_col=0,
                          encoding="Latin-1")
    vrepowerplantFeedIn =pd.read_csv('input/{}/FES_DE.csv'.format(scenario),
                                     index_col=0,
                                     nrows=len(snapshots)+startingPoint,
                                     encoding="Latin-1")
    fuelData = pd.read_csv('input/{}/Fuel.csv'.format(scenario),
                           nrows=len(snapshots)+startingPoint,
                           index_col=0)
    fuelData['co2'] = 20
    fuelData.drop(fuelData.index[0:startingPoint],inplace=True)
    fuelData.reset_index(drop=True,inplace=True)
    fuelPrices=dict(fuelData)
    emissionData = pd.read_csv('input/{}/EmissionFactors.csv'.format(scenario),
                               index_col=0)
    emissionFactors = dict(emissionData['emissions'])
    example = MeritOrder(demand, powerplantsList, vrepowerplantFeedIn, fuelPrices,emissionFactors,snapshots)
    result = example.PFC()
    pd.DataFrame(result).to_csv('MeritOrder2019_20.csv')
