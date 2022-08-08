# -*- coding: utf-8 -*-
"""
Created on Thu Sep 10 17:48:29 2020

@author: INATECH-XX
"""
from influxdb import InfluxDBClient
import pandas as pd
from influxdb import DataFrameClient

class ResultsWriter():
    
    def __init__(self, databaseName, simulationID, startingDate='2018-01-01T00:00:00', host='localhost', port=8086, user='root', password='root', world=None):
        self.user = user
        self.password = password
        self.databaseName = databaseName
        self.simulationID = simulationID
        self.startingDate = startingDate
        self.world=world
        if not(world is None):
            self.timeStamps = pd.date_range(self.startingDate, periods=len(self.world.snapshots), freq='15T')

        # Creating connection and Database to save results
        self.client = InfluxDBClient(host=host, port=port)
        self.client.create_database(databaseName)
        self.client.switch_database(databaseName)
        
        self.dfClient = DataFrameClient(host=host, port=port, username=self.user, password=self.password, database=self.databaseName)
        self.dfClient.switch_database(self.databaseName)
        
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
            "Price": float(MarketResult.marketClearingPrice)
        }
    }]
        self.client.write_points(json_body)
        
    def writeGeneratorsPower(self,generators_P,t):
        df = generators_P.copy()
        df.set_index(pd.date_range(start=self.timeStamps[t], periods=1),inplace=True)
        
        self.dfClient.write_points(df, 'reDispatch', protocol='line', tags= {"simulationID":"{}".format(self.world.simulationID)})
        

        
    def writeBids(self, powerplant,t):
        for bid in powerplant.sentBids:
            json_body = [
        {
            "measurement": "Bids",
            "tags": {
                "user": "{}".format(powerplant.name),
                "Technology":"{}".format(powerplant.technology),
                "simulationID":"{}".format(self.world.simulationID),
                "bidID":"{}".format(bid.ID.split('_')[1])
            },
            "time": "{}".format(self.timeStamps[t]),
            "fields": {
                "Amount": float(bid.amount),
                "Confirmed Amount": float(bid.confirmedAmount),
                "Price": float(bid.price)
            }
        }]
            self.client.write_points(json_body)


    def writeBid(self, powerplant,t,bid):
        json_body = [
    {
        "measurement": "Bid",
        "tags": {
            "user": "{}".format(powerplant.name),
            "Technology":"{}".format(powerplant.technology),
            "simulationID":"{}".format(self.world.simulationID),
            "bidID":"{}".format(bid.ID.split('_')[1])
        },
        "time": "{}".format(self.timeStamps[t]),
        "fields": {
            "Amount": float(bid.amount),
            "Confirmed Amount": float(bid.confirmedAmount),
            "Price": float(bid.price)
        }
    }]
        self.client.write_points(json_body)
            
        
    def writeDataFrame(self,df, measurementName, tags={'simulationID':'Historic_Data'}):
        self.dfClient.write_points(df,
                                   measurementName,
                                   tags=tags,
                                   protocol='line')

    