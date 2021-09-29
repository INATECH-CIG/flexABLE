#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Apr 13 13:12:21 2021

@author: flexable
"""

from flexABLE.flexABLE import World
import pandas as pd

scenarios = [(2016,120)]#,(2017,365),(2018,365),(2019,365)]

importStorages = True
importCRM = True
importDHM = True
importCBT = True
checkAvailability = True
meritOrder = True

writeResultsToDB = False


for year, days in scenarios:
    startingPoint = 0
    snapLength = 96*days    
    timeStamps = pd.date_range('{}-01-01T00:00:00'.format(year), '{}-01-01T00:00:00'.format(year+1), freq = '15T')
    
    example = World(snapLength,
                    simulationID = 'example',
                    startingDate = timeStamps[startingPoint],
                    writeResultsToDB = writeResultsToDB)

    
    example.loadScenario(scenario = '{}'.format(year),
                         checkAvailability = checkAvailability,
                         importStorages = importStorages,
                         importCRM = importCRM,
                         importCBT = importCBT,
                         meritOrder = meritOrder)
    
    
    example.runSimulation()