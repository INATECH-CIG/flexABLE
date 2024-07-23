# -*- coding: utf-8 -*-
"""
Copyright 2019-2020

Ramiz Qussous (INATECH - University of Freibug)
Nick Harder (INATECH - University of Freibug)
Dr. Thomas Künzel (Fichtner GmbH & Co. KG. - Hochschule Offenburg )
Prof. Dr. Anke Weidlich (INATECH - University of Freibug - Hochschule Offenburg)

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License as
published by the Free Software Foundation; either version 3 of the
License, or (at your option) any later version.
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

# Importing classes
from . import agent
from . import EOM
from . import DHM
from . import CRM
from . import MeritOrder
from . import resultsWriter

import pandas as pd
from datetime import datetime

import os

# Managing the logger and TQDM, PyPSA had to be imported after logging to set
# logging level correctly
import logging
import pypsa

# Set pypsa loggers to ERROR level
pypsa.pf.logger.setLevel(logging.ERROR)
pypsa.opf.logger.setLevel(logging.ERROR)
pypsa.linopf.logger.setLevel(logging.ERROR)

# Set pyomo and numexpr loggers to ERROR level
logging.getLogger('pyomo.core').setLevel(logging.ERROR)
logging.getLogger('numexpr.utils').setLevel(logging.ERROR)

# Define a custom formatter class to handle different formats based on log level
class CustomFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.DEBUG:
            # Block format for debug messages
            log_message = (
                f"----------------------------------------\n"
                f"Logger: {record.name}\n"
                f"Time: {self.formatTime(record)}\n"
                f"Level: {record.levelname}\n"
                f"Message: {record.getMessage()}\n"
                f"File: {record.filename}\n"
                f"Path: {record.pathname}\n"
                f"Line: {record.lineno}\n"
                f"----------------------------------------\n"
            )
        else:
            # Single line format for info and other levels
            log_message = (
                f"{self.formatTime(record)} - {record.levelname} - {record.getMessage()} - {record.filename}:{record.lineno}"
            )
        return log_message

handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
# Define the custom format
formatter = CustomFormatter()
handler.setFormatter(formatter)

# Set up the flexABLE logger
logger = logging.getLogger("flexABLE")
logger.setLevel(logging.DEBUG)  # Change to DEBUG to see all messages
logger.addHandler(handler)

# Prevent the root logger from handling messages
logger.propagate = False

class World():
    """
    This is the main container
    """
    def __init__(self, snapshots, simulationID = None, databaseName = 'flexABLE', startingDate = '2018-01-01T00:00:00', writeResultsToDB = False):
        self.logger = logger
        self.simulationID = simulationID
        self.powerplants = []
        self.storages = []
        self.agents = {}
        self.markets = {"EOM":{},
                        "CRM":{}}
        
        if type(snapshots) == int:
            self.snapshots = list(range(snapshots))
        elif type(snapshots) == list:
            self.snapshots = snapshots
            
        self.currstep = 0
        self.fuelPrices = {}
        self.emissionFactors = {}
        
        self.minBidEOM = 1
        self.minBidCRM = 5
        self.minBidDHM = 1
        self.minBidReDIS = 1
        
        self.dt = 0.25 # Although we are always dealing with power, dt is needed to calculate the revenue and for the energy market
        self.dtu = 16 # The frequency of reserve market
        
        self.dictPFC = [0]*snapshots # This is an artifact and should be removed
        self.PFC = [0]*snapshots
        self.EOMResult = [0]*snapshots
        self.IEDPrice = [2999.9]*snapshots
        
        self.startingDate = startingDate
        self.writeResultsToDB = writeResultsToDB
        self.networkEnabled= False
        
        if writeResultsToDB:
            self.ResultsWriter = resultsWriter.ResultsWriter(databaseName = databaseName,
                                                             simulationID = simulationID,
                                                             startingDate = startingDate,
                                                             world = self)
            
    
    def addAgent(self, name):
        self.agents[name] = agent.Agent(name, snapshots = self.snapshots, world = self)
        
        
    def addMarket(self, name, marketType, demand = None, CBtrades = None, HLP_DH = None, annualDemand = None):
        if marketType == "EOM":
            self.markets["EOM"][name] = EOM.EOM(name, demand = demand, CBtrades = CBtrades, world = self)
            
        if marketType == "DHM":
            self.markets["DHM"] = DHM.DHM(name, HLP_DH = HLP_DH, annualDemand = annualDemand, world = self)
            
        if marketType == "CRM":
            self.markets["CRM"] = CRM.CRM(name, demand = demand, world = self)
            
            
    #perform a single step on each market in the following order CRM, DHM, EOM 
    def step(self):
        
        if self.currstep < len(self.snapshots):
            for powerplant in self.powerplants:
                powerplant.checkAvailability(self.snapshots[self.currstep])
                
            self.markets['CRM'].step(self.snapshots[self.currstep], self.agents, products=["posCRMDemand","negCRMDemand"])
            self.markets['DHM'].step(self.snapshots[self.currstep])
            
            for market in self.markets["EOM"].values():
                market.step(self.snapshots[self.currstep],self.agents)
            
            self.markets['CRM'].step(self.snapshots[self.currstep], self.agents, products=["posCRMCall","negCRMCall"])

            for powerplant in self.powerplants:
                powerplant.step()
                
            for storage in self.storages:
                storage.step()
                
            self.currstep +=1
            
        else:
            logger.info("Reached simulation end")
            
            
    def runSimulation(self):
        start = datetime.now()
        df_ergebnisse_CRM = pd.DataFrame()

        
        if self.writeResultsToDB:
            tempDF = pd.DataFrame(self.dictPFC,
                                  index = pd.date_range(self.startingDate, periods = len(self.snapshots), freq = '15min'),
                                  columns=['Merit Order Price']).astype('float64')
            
            # tempDF['Merit Order Price'] = tempDF['Merit Order Price'].astype('float64')
            self.ResultsWriter.writeDataFrame(tempDF, 'PFC', tags={'simulationID':self.simulationID, "user": "EOM"})
            
        logger.info("######## Simulation Started ########")
        logger.info('Started at: {}'.format(start))
        
        for _ in self.snapshots:
            self.step()
            
        finished = datetime.now()
        logger.info('Simulation finished at: {}'.format(finished))
        logger.info('Simulation time: {}'.format(finished - start))
        
        
        #save the simulation results into a database
        if self.writeResultsToDB:
            start = datetime.now()
            logger.info('Writing Capacities in Server - This may take couple of minutes.')
            
            # writing EOM market prices
            tempDF = pd.DataFrame(self.dictPFC,
                                  index = pd.date_range(self.startingDate, periods = len(self.snapshots), freq = '15min'),
                                  columns = ['Price']).astype('float64')
            
            self.ResultsWriter.writeDataFrame(tempDF, 'PFC', tags = {'simulationID':self.simulationID, "user": "EOM"})
            
            #writing demand price (default 2999.9), changes if confirmed supply price is higher than demand price
            tempDF = pd.DataFrame(self.IEDPrice,
                                  index=pd.date_range(self.startingDate, periods = len(self.snapshots), freq = '15min'),
                                  columns=['IED_Price']).astype('float64')
            
            self.ResultsWriter.writeDataFrame(tempDF, 'PFC', tags = {'simulationID':self.simulationID, "user": "EOM"})


            #save total capacities of power plants
            for powerplant in self.powerplants:
                tempDF = pd.DataFrame(powerplant.dictCapacity,
                                      index = ['Power']).drop([-1], axis = 1).T.set_index(pd.date_range(self.startingDate,
                                                                                                        periods = len(self.snapshots),
                                                                                                        freq = '15min')).astype('float64')
                
                self.ResultsWriter.writeDataFrame(tempDF, 'Power', tags = {'simulationID':self.simulationID,
                                                                           'UnitName':powerplant.name,
                                                                           'Technology':powerplant.technology})
                tempDF = pd.DataFrame(powerplant.dictCapacityRedis,
                                      index = ['Power']).T.set_index(pd.date_range(self.startingDate,
                                                                                                        periods = len(self.snapshots),
                                                                                                        freq = '15min')).astype('float64')
                
                self.ResultsWriter.writeDataFrame(tempDF, 'Power_Redispatch', tags = {'simulationID':self.simulationID,
                                                                           'UnitName':powerplant.name,
                                                                           'Technology':powerplant.technology})
            
            #write must-run and flex capacities and corresponding bid prices
            for powerplant in self.powerplants:
                tempDF = pd.DataFrame(powerplant.dictCapacityMR,
                                      index = ['Power_MR', 'MR_Price']).T.set_index(pd.date_range(self.startingDate,
                                                                                                 periods = len(self.snapshots),
                                                                                                 freq = '15min')).astype('float64')
                
                self.ResultsWriter.writeDataFrame(tempDF, 'Capacities', tags = {'simulationID':self.simulationID,
                                                                                'UnitName':powerplant.name,
                                                                                'Technology':powerplant.technology})
                
                tempDF = pd.DataFrame(powerplant.dictCapacityFlex,
                                      index=['Power_Flex','Flex_Price']).T.set_index(pd.date_range(self.startingDate,
                                                                                                   periods = len(self.snapshots),
                                                                                                   freq = '15min')).astype('float64')
                
                self.ResultsWriter.writeDataFrame(tempDF, 'Capacities', tags = {'simulationID':self.simulationID,
                                                                                'UnitName':powerplant.name,
                                                                                'Technology':powerplant.technology})
                for t, bids in powerplant.sentBids_dict.items():
                    for bid in bids:
                        self.ResultsWriter.writeBid(powerplant, t, bid)

            # save different opt schedules off industry
                if powerplant.technology == "industry":
                    tempDF = powerplant.CapacityOptimization_all.set_index(pd.date_range(self.startingDate,
                                                                                                   periods = len(self.snapshots),
                                                                                                   freq = '15min')).astype('float64')

                    self.ResultsWriter.writeDataFrame(tempDF, 'Opt_Schedule', tags = {'simulationID':self.simulationID,
                                                                                    'UnitName':powerplant.name})
            
            #write storage capacities
            for powerplant in self.storages:
                tempDF = pd.DataFrame(powerplant.dictCapacity, index=['Power']).T.set_index(pd.date_range(self.startingDate,
                                                                                                          periods = len(self.snapshots),
                                                                                                          freq = '15min')).astype('float64')

                self.ResultsWriter.writeDataFrame(tempDF.clip(upper = 0), 'Power', tags = {'simulationID':self.simulationID,
                                                                                           'UnitName':powerplant.name+'_charge',
                                                                                           'direction':'charge',
                                                                                           'Technology':powerplant.technology})
                
                self.ResultsWriter.writeDataFrame(tempDF.clip(lower=0),'Power', tags = {'simulationID':self.simulationID,
                                                                                        'UnitName':powerplant.name+'_discharge',
                                                                                        'direction':'discharge',
                                                                                        'Technology':powerplant.technology})
            
            
            finished = datetime.now()
            logger.info('Writing results into database finished at: {}'.format(finished))
            logger.info('Saving into database time: {}'.format(finished - start))

            # writing EOM market prices as CSV (Temporär, an dieser Stelle eigentlich nicht nötig)
            tempDF = pd.DataFrame(self.dictPFC,
                                  index = pd.date_range(self.startingDate, periods = len(self.snapshots), freq = '15min'),
                                  columns = ['Price']).astype('float64')
            
            tempDF.to_csv('EOM_Prices.csv')
            
            
        else:
            logger.info('Saving results into CSV files...')
            
            directory = 'output/{}/'.format(self.scenario+self.simulationID)
            if not os.path.exists(directory):
                os.makedirs(directory)
                os.makedirs(directory+'/PP_capacities')
                os.makedirs(directory+'/STO_capacities')
                
            # writing EOM market prices as CSV
            tempDF = pd.DataFrame(self.dictPFC,
                                  index = pd.date_range(self.startingDate, periods = len(self.snapshots), freq = '15min'),
                                  columns = ['Price']).astype('float64')
            
            tempDF.to_csv(directory + 'EOM_Prices.csv')
            
            #save total capacities of power plants as CSV
            for powerplant in self.powerplants:
                tempDF = pd.DataFrame(powerplant.dictCapacity,
                                      index = ['Power']).drop([-1], axis = 1).T.set_index(pd.date_range(self.startingDate,
                                                                                                        periods = len(self.snapshots),
                                                                                                        freq = '15min')).astype('float64')
                                                                                                        
                try:                                                                              
                    tempDF.to_csv(directory + 'PP_capacities/{}_Capacity.csv'.format(powerplant.name))
                except OSError:
                    print('Could not save {} capacity'.format(powerplant.name))

                tempDF = pd.DataFrame(powerplant.dictCapacityRedis,
                                      index = ['Power']).T.set_index(pd.date_range(self.startingDate,
                                                                                   periods = len(self.snapshots),
                                                                                   freq = '15min')).astype('float64')
                tempDF.to_csv(directory + 'PP_capacities/{}_Capacity_redispatch.csv'.format(powerplant.name))
            #write storage capacities as CSV
            for powerplant in self.storages:
                tempDF = pd.DataFrame(powerplant.dictCapacity, index=['Power']).T.set_index(pd.date_range(self.startingDate,
                                                                                                          periods = len(self.snapshots),
                                                                                                          freq = '15min')).astype('float64')
                
                tempDF.to_csv(directory + 'STO_capacities/{}_Capacity.csv'.format(powerplant.name))
                
            logger.info('Saving results complete')
            
            
        logger.info("#########################")


    def loadScenario(self, scenario="Default", importStorages=False, importCRM=True, importDHM=True, importCBT=True, checkAvailability=False, meritOrder=True, startingPoint=0, networkEnabled=False):
        self.scenario = scenario
        self.simulationID = self.simulationID or '{}{}{}{}{}{}'.format(scenario, '_Sto' if importStorages else '', '_CRM' if importCRM else '', '_DHM' if importDHM else '', '_CBT' if importCBT else '', startingPoint)
        self.importStorages = importStorages
        self.importCRM = importCRM
        self.importDHM = importDHM
        self.importCBT = importCBT
        self.checkAvailability = checkAvailability
        self.meritOrder = meritOrder
        self.startingPoint = startingPoint
        self.networkEnabled = networkEnabled
                
        logger.info(f"Loading Scenario: {scenario}, SimulationID: {self.simulationID}")

        # Load data
        self.loadFuelData(scenario, startingPoint)
        self.loadDemandData(scenario, startingPoint, importCBT)
        self.loadDistrictHeatingData(scenario, startingPoint, importDHM)
        self.loadControlReserveData(scenario, startingPoint, importCRM)

        if networkEnabled:
            self.enableNetwork(scenario, startingPoint)

        self.loadAgentsAndAssets(scenario, checkAvailability)

        if importStorages:
            self.loadStorages(scenario)

        self.loadRenewablePowerGeneration(scenario, startingPoint, networkEnabled)

        if meritOrder:
            self.calculateMeritOrder()

    # Modularized methods
    def loadFuelData(self, scenario, startingPoint):
        logger.info("Loading fuel data....")
        fuelData = pd.read_csv(f'input/{scenario}/Fuel.csv', nrows=len(self.snapshots) + startingPoint, index_col=0)
        fuelData.drop(fuelData.index[0:startingPoint], inplace=True)
        fuelData.reset_index(drop=True, inplace=True)
        self.fuelPrices = dict(fuelData)
        
        emissionData = pd.read_csv(f'input/{scenario}/EmissionFactors.csv', index_col=0)
        self.emissionFactors = dict(emissionData['emissions'])
        logger.info("Fuel data loaded.")

    def loadDemandData(self, scenario, startingPoint, importCBT):
        logger.info("Loading demand....")
        demand = pd.read_csv(f'input/{scenario}/IED_DE.csv', nrows=len(self.snapshots) + startingPoint, index_col=0)
        demand.drop(demand.index[0:startingPoint], inplace=True)
        demand.reset_index(drop=True, inplace=True)
        self.demand = demand

        if importCBT:
            CBT = pd.read_csv(f'input/{scenario}/CBT_DE.csv', nrows=len(self.snapshots) + startingPoint, index_col=0)
            CBT.drop(CBT.index[0:startingPoint], inplace=True)
            CBT.reset_index(drop=True, inplace=True)
            self.addMarket('EOM_DE', 'EOM', demand=demand['demand'], CBtrades=CBT)
        else:
            self.addMarket('EOM_DE', 'EOM', demand=demand['demand'])

    def loadDistrictHeatingData(self, scenario, startingPoint, importDHM):
        logger.info("Loading District heating demand....")
        HLP_DH = pd.read_csv(f'input/{scenario}/HLP_DH_DE.csv', nrows=len(self.snapshots) + startingPoint, index_col=0)
        HLP_DH.drop(HLP_DH.index[0:startingPoint], inplace=True)
        HLP_DH.reset_index(drop=True, inplace=True)
                    
        annualDemand = pd.read_csv(f'input/{scenario}/DH_DE.csv', index_col=0)
        annualDemand *= 4 if importDHM else 0
        self.addMarket('DHM_DE', 'DHM', HLP_DH=HLP_DH, annualDemand=annualDemand)

    def loadControlReserveData(self, scenario, startingPoint, importCRM):
        logger.info("Loading control reserve demand....")
        CRM = pd.read_csv(f'input/{scenario}/CRM_DE.csv', nrows=len(self.snapshots) + startingPoint, index_col=0)
        CRM.drop(CRM.index[0:startingPoint], inplace=True)
        CRM.reset_index(drop=True, inplace=True)
        if not importCRM:
            CRM *= 0
        CRMdemand = {"posCRMDemand": dict(CRM['positive Demand [MW]']),
                     "negCRMDemand": dict(CRM['negative Demand [MW]']),
                     "posCRMCall": dict(CRM['positive Call-Off [MW]']),
                     "negCRMCall": dict(CRM['negative Call-Off [MW]'])}
        self.addMarket('CRM_DE', 'CRM', demand=CRMdemand)
        logger.info("Demand data loaded.")

    def enableNetwork(self, scenario, startingPoint):
        self.networkEnabled = True
        logger.info("Network enabled....")
        logger.info("Importing PyPSA")
        import pypsa
        logger.info("Building topology....")
        self.network = pypsa.Network()
        self.network.set_snapshots(range(len(self.snapshots) // 4))
        buses = pd.read_csv(f'input/{scenario}/nodes.csv', encoding="Latin-1", dtype={'name': str})
        buses.set_index('name', inplace=True)
        demand_dist = pd.read_csv(f'input/{scenario}/IED_dist.csv', nrows=len(self.snapshots) + startingPoint, index_col=0)
        demand_dist.drop(demand_dist.index[0:startingPoint], inplace=True)
        demand_dist.reset_index(drop=True, inplace=True)
        self.demand_dist = demand_dist
        solar_dist = pd.read_csv(f'input/{scenario}/solar_dist.csv', nrows=len(self.snapshots) + startingPoint, index_col=0)
        solar_dist.drop(solar_dist.index[0:startingPoint], inplace=True)
        solar_dist.reset_index(drop=True, inplace=True)
        wind_dist = pd.read_csv(f'input/{scenario}/wind_dist.csv', nrows=len(self.snapshots) + startingPoint, index_col=0)
        wind_dist.drop(wind_dist.index[0:startingPoint], inplace=True)
        wind_dist.reset_index(drop=True, inplace=True)
        self.addAgent('Renewables')

        self.network.madd('Bus', buses.index, x=buses['x'], y=buses['y'])
        self.network.madd('Load', demand_dist.columns, suffix='_load', bus=demand_dist.columns, p_set=pd.DataFrame(0, index=self.network.snapshots, columns=demand_dist.columns))
        self.network.madd('Generator', buses[buses['PV'] > 0].index, suffix='_PV_mrEOM', bus=buses[buses['PV'] > 0].index, carrier='PV', p_nom=1, p_max_pu=1, p_min_pu=1, marginal_cost=0)
        self.network.madd('Generator', buses[(buses['windOn'] + buses['windOff']) > 0].index, suffix='_Wind_mrEOM', bus=buses[(buses['windOn'] + buses['windOff']) > 0].index, carrier='Wind', p_nom=1, p_max_pu=1, p_min_pu=1, marginal_cost=0)
        self.network.madd('Generator', buses.index, suffix='_backup', bus=buses.index, carrier='backup', p_nom=50000, p_max_pu=1, p_min_pu=0, marginal_cost=30000)
        self.network.madd('Generator', buses.index, suffix='_loadshedding', bus=buses.index, carrier='loadshedding', sign=-1, p_nom=50000, p_max_pu=1, p_min_pu=0, marginal_cost=-30000)

        for name, info in buses.iterrows():
            if info['PV'] > 0:
                self.agents['Renewables'].addVREPowerplant(f'{name}_PV', FeedInTimeseries=(solar_dist[str(name)] * info['PV']).to_list())
            if info['windOn'] + info['windOff'] > 0:
                self.agents['Renewables'].addVREPowerplant(f'{name}_Wind', FeedInTimeseries=(wind_dist[name] * (info['windOn'] + info['windOff'])).to_list())
        
        lines = pd.read_csv(f'input/{scenario}/Lines.csv', encoding="Latin-1", dtype={'name': str, 'bus0': str, 'bus1': str})
        links = pd.read_csv(f'input/{scenario}/Links.csv', index_col=0, encoding="Latin-1")
        
        self.network.madd('Line', lines.index, bus0=lines['bus0'], bus1=lines['bus1'], x=lines['x'], r=lines['r'], s_nom=lines['s_nom'] * lines['Circuits'])
        self.network.madd('Link', links.index, bus0=links['bus0'], bus1=links['bus1'], p_nom=links['p_nom'])
    
    def loadAgentsAndAssets(self, scenario, checkAvailability):
        logger.info("Loading Agents and assets....")
        powerplantsList = pd.read_csv(f'input/{scenario}/FPP_DE.csv', index_col=0, dtype={'node': str}, encoding="Latin-1")
        self.powerplantsList = powerplantsList
        if self.networkEnabled:
            self.network.madd('Generator', powerplantsList.index, suffix='_mrEOM', bus=powerplantsList.node, carrier=powerplantsList['technology'], p_nom=1, p_max_pu=1, p_min_pu=1, marginal_cost=0)
        
        for company in powerplantsList.company.unique():
            self.addAgent(company)
        
        for powerplant, data in powerplantsList.iterrows():
            if checkAvailability:
                try:
                    availability = pd.read_csv(f'input/{scenario}/Availability/{powerplant}.csv', nrows=len(self.snapshots) + startingPoint, index_col=0)
                    availability.drop(availability.index[0:startingPoint], inplace=True)
                    availability.reset_index(drop=True, inplace=True)
                    availability = availability.Total.to_list()
                    self.agents[data['company']].addPowerplant(powerplant, availability=availability, **dict(data))
                except FileNotFoundError:
                    self.agents[data['company']].addPowerplant(powerplant, **dict(data))
            else:
                self.agents[data['company']].addPowerplant(powerplant, **dict(data))
    
    def loadStorages(self, scenario):
        storageList = pd.read_csv(f'input/{scenario}/STO_DE.csv', index_col=0, encoding="Latin-1")
        
        for company in storageList.company.unique():
            if company not in self.agents:
                self.addAgent(company)
        
        for storage, data in storageList.iterrows():
            self.agents[data['company']].addStorage(storage, **dict(data))
    
    def loadRenewablePowerGeneration(self, scenario, startingPoint, networkEnabled):
        vrepowerplantFeedIn = pd.read_csv(f'input/{scenario}/FES_DE.csv', index_col=0, nrows=len(self.snapshots) + startingPoint, encoding="Latin-1")
        vrepowerplantFeedIn.drop(vrepowerplantFeedIn.index[0:startingPoint], inplace=True)
        vrepowerplantFeedIn.reset_index(drop=True, inplace=True)
        self.vrepowerplantFeedIn = vrepowerplantFeedIn
        if not networkEnabled:
            self.addAgent('Renewables')
            for vre in vrepowerplantFeedIn:
                self.agents['Renewables'].addVREPowerplant(vre, FeedInTimeseries=vrepowerplantFeedIn[vre].to_list())
    
    def calculateMeritOrder(self):
        logger.info("Calculating PFC....")
        meritOrder = MeritOrder.MeritOrder(self.demand, self.powerplantsList, self.vrepowerplantFeedIn, self.fuelPrices, self.emissionFactors, self.snapshots)
        self.dictPFC = meritOrder.PFC()
        self.PFC = self.dictPFC.copy()
        logger.info("Merit Order calculated.")
            
            
        
if __name__ == "__main__":
    scenarios = [(2016,366)]#,(2017,365),(2018,365),(2019,365)]
    
    
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
        timeStamps = pd.date_range('{}-01-01T00:00:00'.format(year), '{}-01-01T00:00:00'.format(year+1), freq = '15min')
        
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
        
        