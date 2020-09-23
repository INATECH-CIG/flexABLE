# -*- coding: utf-8 -*-
"""
Created on Thu Sep 10 17:48:29 2020

@author: INATECH-XX
"""
from influxdb import InfluxDBClient
import pandas as pd

from influxdb import DataFrameClient

class ResultsWriter():
    
    def __init__(self, databaseName, simulationID, startingDate='2018-01-01T00:00:00', world=None):
        self.user = 'root'
        self.password = 'root'
        self.databaseName = databaseName
        self.simulationID = simulationID
        self.startingDate = startingDate
        self.world=world
        self.timeStamps = pd.date_range(self.startingDate, periods=len(self.world.snapshots), freq='15T')
        # Creating connection and Database to save results
        self.client = InfluxDBClient(host='localhost', port=8086)
        self.client.create_database(databaseName)
        self.client.switch_database(databaseName)
        
        self.dfClient = DataFrameClient(host='localhost', port=8086, username=self.user, password=self.password, database=self.databaseName)
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
            "Price": MarketResult.marketClearingPrice
        }
    }]
        self.client.write_points(json_body)
        
    def writeGeneratorsPower(self,generators_P,t):
        df = generators_P.copy()
        df.set_index(pd.date_range(start=self.timeStamps[t], periods=1),inplace=True)
        
        self.dfClient.write_points(df, 'reDispatch', protocol='line', tags= {"simulationID":"{}".format(self.world.simulationID)})
        
    def writeRedispatchPower(self,generators_P,t):
        df = generators_P.copy()
        df = df.groupby(self.world.network.generators.carrier, axis=1).sum()
        df.set_index(pd.date_range(start=self.timeStamps[t], periods=1),inplace=True)
        if 'PSPP_charge_neg' in df.columns:
            df['PSPP_charge_neg'] = -df['PSPP_charge_neg']
            df['PSPP_charge_pos'] = -df['PSPP_charge_pos']
        self.dfClient.write_points(df.loc[:, df.columns.str.contains('pos')],
                                   'reDispatch_Tech_pos',
                                   protocol='line',
                                   tags= {"simulationID":"{}".format(self.world.simulationID)})
        self.dfClient.write_points(df.loc[:, df.columns.str.contains('neg')],
                                   'reDispatch_Tech_neg',
                                   protocol='line',
                                   tags= {"simulationID":"{}".format(self.world.simulationID)})

    def writeCapacity(self,powerplant,t):
        json_body = [
    {
        "measurement": "Power",
        "tags": {
            "user": "{}".format(powerplant.name),
            "Technology":"{}".format(powerplant.technology),
            "simulationID":"{}".format(self.world.simulationID),
        },
        "time": "{}".format(self.timeStamps[t]),
        "fields": {
            "Power": float(powerplant.dictCapacity[t])
        }
    }]
        self.client.write_points(json_body)
        
    def writeNodalPower(self,network,t):
        df = pd.DataFrame(network.buses_t.p.T).copy()
        df.columns=['Power']
        df[['x','y']] = network.buses[['x','y']].copy()
        def jsonBuild(row):
            json_body = [
        {
            "measurement": "Nodal_Power",
            "tags": {
                "node": "{}".format(row.name),
                "simulationID":"{}".format(self.world.simulationID),
            },
            "time": "{}".format(self.timeStamps[t]),
            "fields": {
                "Power": float(row.Power),
                "x":"{}".format(row.x),
                "y":"{}".format(row.y)
            }
        }]
            self.client.write_points(json_body)
        df.apply(jsonBuild,axis=1)

