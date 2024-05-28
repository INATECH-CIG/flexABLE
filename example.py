#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Apr 13 13:12:21 2021

@author: flexable
"""
#%%
from flexABLE.flexABLE import World
import pandas as pd


scenarios = [(2016,2)]#,(2017,365),(2018,365),(2019,365)]

importStorages = False
importCRM = False
importDHM = False
importCBT = False
checkAvailability = False
meritOrder = True

writeResultsToDB = False

for year, days in scenarios:
    startingPoint = 0
    snapLength = 96*days    
    timeStamps = pd.date_range('{}-01-01T00:00:00'.format(year), '{}-01-01T00:00:00'.format(year+1), freq = '15T')

    example = World(snapLength,
                    simulationID = 'example_CRM',
                    startingDate = timeStamps[startingPoint],
                    writeResultsToDB = writeResultsToDB)

    
    example.loadScenario(scenario = '{}'.format(year),
                         checkAvailability = checkAvailability,
                         importStorages = importStorages,
                         importCRM = importCRM,
                         importCBT = importCBT,
                         meritOrder = meritOrder)

    example.addAgent(name='Testoperator')

    example.agents['Testoperator'].addSteelPlant(name='TestStahl')

    example.runSimulation()



clearingTime = [0,12,13,14,15,16,17,32,33,48]

#%%

t = 91

bids_confirmed_EOM = [r.confirmedBids for r in example.markets['EOM']['EOM_DE'].debug_results]
print(pd.DataFrame({bid.issuer.name: {'price':bid.price, 'amount':bid.confirmedAmount} for bid in bids_confirmed_EOM[t]}))

bids_rejected_EOM = [r.rejectedBids for r in example.markets['EOM']['EOM_DE'].debug_results]
print(pd.DataFrame({bid.issuer.name: {'price':bid.price, 'amount':bid.confirmedAmount} for bid in bids_rejected_EOM[t]}))


# for t in clearingTime:
#     print("------------------------------------------------------------------------")
#     print("clearingTime:" + str(t))
#     print("confirmedBids negCRMDemand:")
#     bids_confirmed = [r.confirmedBids for t, r in example.markets['CRM'].marketResults['negCRMDemand'].items()]
#     print(pd.DataFrame({bid.issuer.name: {'price':bid.price, 'amount':bid.confirmedAmount} for bid in bids_confirmed[t]}))
#     print("rejectedBids negCRMDemand:")
#     bids_rejected = [r.rejectedBids for t, r in example.markets['CRM'].marketResults['negCRMDemand'].items()]
#     print(pd.DataFrame({bid.issuer.name: {'price':bid.price, 'amount':bid.confirmedAmount} for bid in bids_rejected[t]}))
   
#     print("-----------")

#     print("confirmedBids negCRMCall:")
#     bids_confirmed = [r.confirmedBids for t, r in example.markets['CRM'].marketResults['negCRMCall'].items()]
#     print(pd.DataFrame({bid.issuer.name: {'price':bid.energyPrice, 'amount':bid.confirmedAmount} for bid in bids_confirmed[t]}))
#     print("rejectedBids negCRMCall:")
#     bids_rejected = [r.rejectedBids for t, r in example.markets['CRM'].marketResults['negCRMCall'].items()]
#     print(pd.DataFrame({bid.issuer.name: {'price':bid.energyPrice, 'amount':bid.confirmedAmount} for bid in bids_rejected[t]}))
   
#     print("-----------")

# %%
