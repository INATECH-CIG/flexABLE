# -*- coding: utf-8 -*-
"""
Created on Wed Mar 31 15:17:46 2021

@author: intgridnb-02
"""

import pandas as pd
from random import random, randint 
inputList = pd.read_csv('input_List.csv', index_col=0)

fuel = list(inputList.Fuel.unique())
technologies = list(inputList.Technology.unique())

fuel = ['Natural gas', 'Hard coal', 'Lignite', 'Oil(light)', 'Nuclear', 'Oil(heavy)']
data = inputList[inputList['Fuel'].isin(fuel)].copy()

data = data[data['Capacity'] > 1.0]

data.Fuel.replace('Lignite', 'lignite', inplace=True)
data.Fuel.replace('Hard coal', 'hard coal', inplace=True)
data.Fuel.replace('Natural gas', 'natural gas', inplace=True)
data.Fuel.replace('Nuclear', 'uranium', inplace=True)
data.Fuel.replace('Oil(light)', 'oil', inplace=True)
data.Fuel.replace('Oil(heavy)', 'oil', inplace=True)

#data.Technology.replace('Combined cycle', 'combined cycle gas turbine', inplace=True)
def set_Technology(row):
    if row.Fuel == 'uranium': 
        return 'nuclear'
    elif row.Fuel == 'hard coal':
        return 'hard coal'
    elif row.Fuel == 'lignite':
        return 'lignite'
    elif row.Fuel == 'oil':
        return 'oil'
    elif row.Fuel =='natural gas':
        if row.Technology == 'Combined cycle':
            return 'combined cycle gas turbine'
        else:
            return 'open cycle gas turbine'
def set_Minimum_Power(row):
    minimumLoad = {'nuclear':0.4,
                   'lignite':0.5,
                   'hard coal':0.4,
                   'combined cycle gas turbine':0.4,
                   'open cycle gas turbine':0.25,
                   'oil':0.25,
                   }
    minimumPower = max(row.maxPower * minimumLoad[row.technology],1)
    return minimumPower

def set_Ramp_Power(row):
    rampingPower = {'nuclear':0.6,
                   'lignite':0.5,
                   'hard coal':0.7,
                   'combined cycle gas turbine':0.85,
                   'open cycle gas turbine':1,
                   'oil':1,
                   }
    return row.maxPower * rampingPower[row.technology]

def set_VariableCost(row):
    VariableCost = {'nuclear':6,
                   'lignite':7,
                   'hard coal':1.3,
                   'combined cycle gas turbine':4,
                   'open cycle gas turbine':3,
                   'oil':3,
                   }
    return VariableCost[row.technology]

def set_hotStartCost(row):
    hotStartCost = {'nuclear':140,
                   'lignite':30.4 if row.maxPower >= 300  else 45.1,
                   'hard coal':30.5 if row.maxPower >= 300  else 45.1,
                   'combined cycle gas turbine':randint(23,24),
                   'open cycle gas turbine':19.5 if data.Technology[row.name] == 'Steam turbine'  else 16.5,
                   'oil':20.7,
                   }
    return hotStartCost[row.technology]

def set_warmStartCost(row):
    warmStartCost = {'nuclear':140,
                   'lignite':47.5 if row.maxPower >= 300  else 73.9,
                   'hard coal':47.5 if row.maxPower >= 300  else 73.9,
                   'combined cycle gas turbine':34.2,
                   'open cycle gas turbine':34.5 if data.Technology[row.name] == 'Steam turbine'  else 21,
                   'oil':35.8,
                   }
    return warmStartCost[row.technology]

def set_coldStartCost(row):
    coldStartCost = {'nuclear':140,
                   'lignite':69.3 if row.maxPower >= 300  else 73.2,
                   'hard coal':69.3 if row.maxPower >= 300  else 73.2,
                   'combined cycle gas turbine':46.7,
                   'open cycle gas turbine':43.5 if data.Technology[row.name] == 'Steam turbine'  else 28.5,
                   'oil':45.1,
                   }
    return coldStartCost[row.technology]

def set_minOperation(row):
    minOperation = {'nuclear':72,
                   'lignite':10,
                   'hard coal':7,
                   'combined cycle gas turbine':5,
                   'open cycle gas turbine':0,
                   'oil':0,
                   }
    return minOperation[row.technology]

def set_minDowntime(row):
    minDowntime = {'nuclear':10,
                   'lignite':7,
                   'hard coal':6,
                   'combined cycle gas turbine':6,
                   'open cycle gas turbine':0,
                   'oil':0,
                   }
    return minDowntime[row.technology]

def set_heatExtraction(row):
    if pd.isna(data['Max. heat '][row.name]):
        return 'no'
    else:
        return 'yes'


def set_maxExtraction(row):
    if pd.isna(data['Max. heat '][row.name]):
        return 0
    else:
        return data['Max. heat '][row.name]

def set_heatingDistrict(row):
    if pd.isna(data['Max. heat '][row.name]):
        return 'N/A'
    else:
        return data['CHP network'][row.name]

outputList = pd.DataFrame()
outputList['technology']= data.apply(set_Technology, axis=1)
outputList['fuel']= data['Fuel']
outputList['node'] = data['Node'].copy()
outputList['maxPower'] = data['Capacity']
outputList['minPower'] = outputList.apply(set_Minimum_Power,axis=1)
outputList['efficiency'] = data.Efficiency
outputList['emission'] = data.Emission
outputList['rampUp'] = outputList.apply(set_Ramp_Power,axis=1)
outputList['rampDown'] = outputList.apply(set_Ramp_Power,axis=1)
outputList['variableCosts'] = outputList.apply(set_VariableCost,axis=1)
outputList['hotStartCosts'] = outputList.apply(set_hotStartCost,axis=1)
outputList['warmStartCosts'] = outputList.apply(set_warmStartCost,axis=1)
outputList['coldStartCosts'] = outputList.apply(set_coldStartCost,axis=1)
outputList['minOperatingTime'] =outputList.apply(set_minOperation,axis=1)
outputList['minDowntime'] = outputList.apply(set_minDowntime,axis=1)
outputList['heatExtraction'] = outputList.apply(set_heatExtraction,axis=1)
outputList['maxExtraction'] = outputList.apply(set_maxExtraction,axis=1)
outputList['heatingDistrict'] = outputList.apply(set_heatingDistrict,axis=1)
outputList['company'] = data.Name
outputList['year'] = data.Commissioning

outputList.to_csv('FPP_DE.csv')