# -*- coding: utf-8 -*-
"""
Created on Thu Sep 10 17:48:29 2020

@author: INATECH-XX
"""

from datetime import datetime
import pandas as pd
import os


class ResultsWriter():
    
    def __init__(self,
                 database_name,
                 simulation_id,
                 write_to_db,
                 starting_date='2018-01-01T00:00:00',
                 host='10.5.139.92',
                 port=8086,
                 user='root',
                 password='root',
                 world=None):

        self.user = user
        self.password = password
        self.database_name = database_name
        self.simulation_id = simulation_id
        self.starting_date = starting_date
        self.world = world
        
        if not(world is None):
            self.timeStamps = pd.date_range(
                self.starting_date, periods=len(self.world.snapshots), freq='15T')

        if write_to_db:
            from influxdb import InfluxDBClient
            from influxdb import DataFrameClient

            # Creating connection and Database to save results
            self.client = InfluxDBClient(host=host, port=port)
            self.client.create_database(database_name)
            self.client.switch_database(database_name)

            self.dfClient = DataFrameClient(
                host=host, port=port, username=self.user, password=self.password, database=self.database_name)
            self.dfClient.switch_database(self.database_name)

    def writeMarketResult(self, MarketResult):
        json_body = [
            {
                "measurement": "PFC",
                "tags": {
                    "user": "EOM",
                    "simulation_id": "{}".format(self.world.simulation_id),
                },
                "time": "{}".format(self.timeStamps[MarketResult.timestamp]),
                "fields": {
                    "Price": float(MarketResult.marketClearingPrice)
                }
            }]
        self.client.write_points(json_body)

    def writeGeneratorsPower(self, generators_P, t):
        df = generators_P.copy()
        df.set_index(pd.date_range(
            start=self.timeStamps[t], periods=1), inplace=True)

        self.dfClient.write_points(df, 'reDispatch', protocol='line', tags={
                                   "simulation_id": "{}".format(self.world.simulation_id)})

    def writeBids(self, powerplant, t):
        for bid in powerplant.sentBids:
            json_body = [
                {
                    "measurement": "Bids",
                    "tags": {
                        "user": "{}".format(powerplant.name),
                        "Technology": "{}".format(powerplant.technology),
                        "simulation_id": "{}".format(self.world.simulation_id),
                        "bidID": "{}".format(bid.ID.split('_')[1])
                    },
                    "time": "{}".format(self.timeStamps[t]),
                    "fields": {
                        "Amount": float(bid.amount),
                        "Confirmed Amount": float(bid.confirmedAmount),
                        "Price": float(bid.price)
                    }
                }]
            self.client.write_points(json_body)

    def writeBid(self, powerplant, t, bid):
        json_body = [
            {
                "measurement": "Bid",
                "tags": {
                    "user": "{}".format(powerplant.name),
                    "Technology": "{}".format(powerplant.technology),
                    "simulation_id": "{}".format(self.world.simulation_id),
                    "bidID": "{}".format(bid.ID.split('_')[1])
                },
                "time": "{}".format(self.timeStamps[t]),
                "fields": {
                    "Amount": float(bid.amount),
                    "Confirmed Amount": float(bid.confirmedAmount),
                    "Price": float(bid.price)
                }
            }]
        self.client.write_points(json_body)


    def writeDataFrame(self, df, measurementName, tags={'simulationID': 'Historic_Data'}):
        self.dfClient.write_points(df,
                                   measurementName,
                                   tags=tags,
                                   protocol='line')


    def save_results_to_DB(self):
        start = datetime.now()
        self.world.logger.info('Writing Capacities and Prices to Server - This may take couple of minutes.')

        index = pd.date_range(self.world.starting_date, periods=len(self.world.snapshots), freq=str(60*self.world.dt)+'T')

        # writing Merit Order Price
        tempDF = pd.DataFrame(self.world.pfc, index=index, columns=['Merit order']).astype('float32')
        self.writeDataFrame(tempDF, 'Prices', tags={'simulationID': self.world.simulation_id, "user": "EOM"})

        # writing EOM market prices
        tempDF = pd.DataFrame(self.world.mcp, index=index, columns=['Simulation']).astype('float32')
        self.writeDataFrame(tempDF, 'Prices', tags={'simulationID': self.world.simulation_id, "user": "EOM"})

        # writing EOM demand
        tempDF = pd.DataFrame(self.world.markets['EOM']['EOM_DE'].demand.values(), index=index, columns=['EOM demand']).astype('float32')
        self.writeDataFrame(tempDF, 'Demand', tags={'simulationID': self.world.simulation_id, "user": "EOM"})

        # writing residual load
        tempDF = pd.DataFrame(self.world.res_load['demand'].values, index=index, columns=['Residual load']).astype('float32')
        self.writeDataFrame(tempDF, 'Demand', tags={'simulationID': self.world.simulation_id, "user": "EOM"})

        # writing residual load forecast
        tempDF = pd.DataFrame(self.world.res_load_forecast['demand'].values, index=index, columns=['Residual load forecast']).astype('float32')
        self.writeDataFrame(tempDF, 'Demand', tags={'simulationID': self.world.simulation_id, "user": "EOM"})

        # save total capacities, must-run and flex capacities and corresponding bid prices of power plants
        #self.write_pp()
        # write storage capacities
        self.write_storages()
                                      
        finished = datetime.now()
        self.world.logger.info(
            'Writing results into database finished at: {}'.format(finished))
        self.world.logger.info(
            'Saving into database time: {}'.format(finished - start))

    def save_result_to_csv(self):

        self.world.logger.info('Saving results into CSV files...')

        directory = 'output/{}/'.format(self.world.scenario)
        if not os.path.exists(directory):
            os.makedirs(directory)
            os.makedirs(directory+'/PP_capacities')
            os.makedirs(directory+'/STO_capacities')

        # writing EOM market prices as CSV
        tempDF = pd.DataFrame(self.world.mcp,
                              index=pd.date_range(self.world.starting_date, periods=len(
                                  self.world.snapshots), freq='15T'),
                              columns=['Price']).astype('float32')

        tempDF.to_csv(directory + 'EOM_Prices.csv')

        # save total capacities of power plants as CSV
        for powerplant in self.world.powerplants:
            tempDF = pd.DataFrame(powerplant.dictCapacity,
                                  index=['Power']).drop([-1], axis=1).T.set_index(pd.date_range(self.world.starting_date,
                                                                                                periods=len(
                                                                                                    self.world.snapshots),
                                                                                                freq='15T')).astype('float32')

            tempDF.to_csv(
                directory + 'PP_capacities/{}_Capacity.csv'.format(powerplant.name))

        # write storage capacities as CSV
        for powerplant in self.world.storages:
            tempDF = pd.DataFrame(powerplant.dictCapacity, index=['Power']).T.set_index(pd.date_range(self.world.starting_date,
                                                                                                      periods=len(
                                                                                                          self.world.snapshots),
                                                                                                      freq='15T')).astype('float32')

            tempDF.to_csv(
                directory + 'STO_capacities/{}_Capacity.csv'.format(powerplant.name))

        self.world.logger.info('Saving results complete')

    
    def write_pp(self):
        index = pd.date_range(self.world.starting_date, periods=len(self.world.snapshots), freq=str(60*self.world.dt)+'T')
        
        for powerplant in (self.world.rl_powerplants+self.world.powerplants+self.world.vre_powerplants):
            tempDF = pd.DataFrame(powerplant.total_capacity, index = index, columns = ['Total pp']).astype('float32')
            self.writeDataFrame(tempDF, 'Capacities',
                                tags={'simulationID': self.world.simulation_id,
                                        'UnitName': powerplant.name,
                                        'Technology': powerplant.technology})

            tempDF = pd.DataFrame(powerplant.bids_mr, index=['Capacity_MR', 'Price_MR']).T.set_index(index).astype('float32')
            self.writeDataFrame(tempDF, 'Capacities',
                                tags={'simulationID': self.world.simulation_id,
                                        'UnitName': powerplant.name,
                                        'Technology': powerplant.technology})

            tempDF = pd.DataFrame(powerplant.bids_flex, index=['Capacity_Flex', 'Price_Flex']).T.set_index(index).astype('float32')
            self.writeDataFrame(tempDF, 'Capacities',
                                tags={'simulationID': self.world.simulation_id,
                                        'UnitName': powerplant.name,
                                        'Technology': powerplant.technology})

            tempDF = pd.DataFrame(powerplant.rewards, index=index, columns=['Rewards']).astype('float32')
            self.writeDataFrame(tempDF, 'Rewards',
                                tags={'simulationID': self.world.simulation_id,
                                        'UnitName': powerplant.name,
                                        'Technology': powerplant.technology})

            tempDF = pd.DataFrame(powerplant.regrets, index=index, columns=['Regrets']).astype('float32')
            self.writeDataFrame(tempDF, 'Regrets',
                                tags={'simulationID': self.world.simulation_id,
                                      'UnitName': powerplant.name,
                                      'Technology': powerplant.technology})

           
            tempDF = pd.DataFrame(powerplant.profits, index=index, columns=['Profits']).astype('float32')
            self.writeDataFrame(tempDF, 'Profits',
                                tags={'simulationID': self.world.simulation_id,
                                        'UnitName': powerplant.name,
                                        'Technology': powerplant.technology})

    
    def write_storages(self):
        index = pd.date_range(self.world.starting_date, periods=len(self.world.snapshots), freq=str(60*self.world.dt)+'T')

        for storage in (self.world.storages+self.world.rl_storages):
            tempDF = pd.DataFrame(storage.total_capacity, index = index, columns = ['Total st']).astype('float32')
            self.writeDataFrame(tempDF.clip(upper=0), 'Capacities',
                                tags={'simulationID': self.world.simulation_id,
                                      'UnitName': storage.name,
                                      'direction': 'discharge',
                                      'Technology': storage.technology})

            self.writeDataFrame(tempDF.clip(lower=0), 'Capacities',
                                tags={'simulationID': self.world.simulation_id,
                                      'UnitName': storage.name,
                                      'direction': 'charge',
                                      'Technology': storage.technology})            
            
            tempDF = pd.DataFrame(storage.bids_supply, index=['Capacity_dis', 'Price_dis']).T.set_index(index).astype('float32')
            self.writeDataFrame(tempDF, 'Capacities',
                                tags={'simulationID': self.world.simulation_id,
                                      'UnitName': storage.name,
                                      'Technology': storage.technology})

            tempDF = pd.DataFrame(storage.bids_demand, index=['Capacity_ch', 'Price_ch']).T.set_index(index).astype('float32')
            self.writeDataFrame(tempDF, 'Capacities',
                                tags={'simulationID': self.world.simulation_id,
                                      'UnitName': storage.name,
                                      'Technology': storage.technology})

            tempDF = pd.DataFrame(storage.rewards, index=index, columns=['Rewards']).astype('float32')
            self.writeDataFrame(tempDF, 'Rewards',
                                tags={'simulationID': self.world.simulation_id,
                                      'UnitName': storage.name,
                                      'Technology': storage.technology})

            tempDF = pd.DataFrame(storage.profits, index=index, columns=['Profits']).astype('float32')
            self.writeDataFrame(tempDF, 'Profits',
                                tags={'simulationID': self.world.simulation_id,
                                      'UnitName': storage.name,
                                      'Technology': storage.technology})

            tempDF = pd.DataFrame(storage.energy_cost[:-1], index=index, columns=['Energy cost']).astype('float32')
            self.writeDataFrame(tempDF, 'Energy cost',
                                tags={'simulationID': self.world.simulation_id,
                                      'UnitName': storage.name,
                                      'Technology': storage.technology})

            tempDF = pd.DataFrame(storage.soc[:-1], index=index, columns=['SOC']).astype('float32')
            self.writeDataFrame(tempDF, 'SOC',
                                tags={'simulationID': self.world.simulation_id,
                                      'UnitName': storage.name,
                                      'Technology': storage.technology})

            if 'opt' in storage.name:
                tempDF = pd.DataFrame(storage.opt_bids_supply, index=['Capacity_dis_opt', 'Price_dis']).T.set_index(index).astype('float32')
                self.writeDataFrame(tempDF, 'Capacities',
                                    tags={'simulationID': self.world.simulation_id,
                                          'UnitName': storage.name,
                                          'Technology': storage.technology})

                tempDF = pd.DataFrame(storage.opt_bids_demand, index=['Capacity_ch_opt', 'Price_ch']).T.set_index(index).astype('float32')
                self.writeDataFrame(tempDF, 'Capacities',
                                    tags={'simulationID': self.world.simulation_id,
                                          'UnitName': storage.name,
                                          'Technology': storage.technology})

                tempDF = pd.DataFrame(storage.opt_profits, index=index, columns=['Profits_opt']).astype('float32')
                self.writeDataFrame(tempDF, 'Profits',
                                    tags={'simulationID': self.world.simulation_id,
                                          'UnitName': storage.name,
                                          'Technology': storage.technology})

                tempDF = pd.DataFrame(storage.opt_soc[:-1], index=index, columns=['SOC_opt']).astype('float32')
                self.writeDataFrame(tempDF, 'SOC',
                                    tags={'simulationID': self.world.simulation_id,
                                          'UnitName': storage.name,
                                          'Technology': storage.technology})

                                        
    def delete_simulation(self, simID):
        check = input('Are you sure you want to delete ' + simID + ' ??? Type simId to confirm: ')
        if check == simID:
            self.dfClient.delete_series(tags={'simulationID': simID})
            print(simID, 'deleted')
        else:
            print('!!! Wrong name entered !!!')

    def delete_multiple_simulations(self, simIDs):
        reply = input('Are you sure you want to delete ' + str(simIDs) + ' ???')
        if reply.lower() in ['yes', 'y']:
            for simID in simIDs:
                self.dfClient.delete_series(tags={'simulationID': simID})
                print(simID, 'deleted')
        else:
            print('!!! Ok, not deleted !!!')

    def delete_database(self, database_name):
        check = input('Are you sure you want to delete ' + database_name + ' ??? Type database name to confirm: ')
        if check == database_name:
            self.dfClient.drop_database(database_name)
            print(database_name, 'database deleted')
        else:
            print('!!! Wrong name entered !!!')

