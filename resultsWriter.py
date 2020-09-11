# -*- coding: utf-8 -*-
"""
Created on Thu Sep 10 17:48:29 2020

@author: INATECH-XX
"""
from influxdb import InfluxDBClient
import pandas as pd
import numpy as np

class ResultsWriter():
    
    def __init__(self, databaseName, simulationID, startingDate='2018-01-01T00:15:00', world=None):
        self.databaseName = databaseName
        self.simulationID = simulationID
        self.startingDate = startingDate
        self.world=world
        self.timeStamps = pd.date_range(self.startingDate, periods=len(self.world.snapshots), freq='15T')
        # Creating connection and Database to save results
        self.client = InfluxDBClient(host='localhost', port=8086)
        self.client.create_database(databaseName)
        self.client.switch_database(databaseName)
        
    def writeMarketResult(self,MarketResult):
        json_body = [
    {
        "measurement": "PFC",
        "tags": {
            "user": "EOM",
            "simulationID":"{}".format(self.world.simulationID),
        },
        "time": "{}".format(self.timeStamps[MarketResult.timestamp]),
        "fields": {
            "Price": MarketResult.marketClearingPrice
        }
    }]
        self.client.write_points(json_body)