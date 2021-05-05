#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Apr 13 13:12:21 2021

@author: flexable
"""

from flexABLE.flexABLE import World
import pandas as pd

scenarios = [(2016,366),(2017,365),(2018,365),(2019,365)]
for year, days in scenarios:
    startingPoint = 0
    snapLength = 96*days
    networkEnabled=False
    importStorages=True
    importCRM=True
    meritOrder=True
    addBackup=True
    CBTransfers=1
    CBTMainland='DE'
    timeStamps = pd.date_range('{}-01-01T00:00:00'.format(year), '{}-01-01T00:00:00'.format(year+1), freq='15T')
    example = World(snapLength, networkEnabled=networkEnabled,
                    simulationID='paper_v6', startingDate=timeStamps[startingPoint])

    
    example.loadScenario(scenario='{}'.format(year),
                         importStorages=importStorages,
                         importCRM=importCRM,
                         meritOrder=meritOrder,
                         addBackup=addBackup,
                         CBTransfers=CBTransfers,
                         CBTMainland=CBTMainland,
                         startingPoint=startingPoint,
                         line_expansion=1.5,
                         line_expansion_price=1000,
                         backupPerNode=100)

    example.runSimulation()
        