# -*- coding: utf-8 -*-
"""
Created on Thu Sep 10 17:48:29 2020

@author: INATECH-XX
"""
from influxdb import InfluxDBClient
import pandas as pd
import json
from influxdb import DataFrameClient

class ResultsWriter():
    
    def __init__(self, databaseName, simulationID, startingDate='2018-01-01T00:00:00', world=None):
        self.user = 'root'
        self.password = 'root'
        self.databaseName = databaseName
        self.simulationID = simulationID
        self.startingDate = startingDate
        self.world=world
        if not(world is None):
            self.timeStamps = pd.date_range(self.startingDate, periods=len(self.world.snapshots), freq='15T')

        # self.MarketResults = []
        # Creating connection and Database to save results
        self.client = InfluxDBClient(host='10.5.139.84', port=8086)
        self.client.create_database(databaseName)
        self.client.switch_database(databaseName)
        
        self.dfClient = DataFrameClient(host='10.5.139.84', port=8086, username=self.user, password=self.password, database=self.databaseName)
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
        

    def writeCapacity(self,powerplant,t, writeBidsInDB=False):
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
        # self.client.write_points(json_body)

    def writeDataFrame(self,df, measurementName, tags={'simulationID':'Historic_Data'}):
        self.dfClient.write_points(df,
                                   measurementName,
                                   tags=tags,
                                   protocol='line')

if __name__=='__main__':
    with open('year_2020.json', 'r') as myfile:
        data=myfile.read()

    # parse file
    obj = json.loads(data)
    
    data = pd.DataFrame()
    required=['Day Ahead Auction', 'Intraday Continuous Index Price',
            'Intraday Continuous Average Price', 'Intraday Continuous Low Price',
            'Intraday Continuous High Price', 'Intraday Continuous ID3-Price']
    for _ in obj:
        if _['key'][0]['en'] in required:
            tempData = pd.DataFrame(_['values'])
            tempData[0] = tempData[0].astype('datetime64[ms]')
            tempData.set_index(0, inplace=True, drop=True)
            data[_['key'][0]['en']]=tempData[1]

    resultsWriter = ResultsWriter(databaseName='flexABLE', simulationID='paper_v1')
    resultsWriter.writeDataFrame(data, 'PFC', )
    