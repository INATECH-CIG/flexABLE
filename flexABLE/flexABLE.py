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
from .import EOM
from .import DHM
from .import CRM
from .import MeritOrder
from .import resultsWriter

import pandas as pd
from datetime import datetime
from tqdm import tqdm

import os

# Managing the logger and TQDM
# logging level correctly
import logging

logger = logging.getLogger("flexABLE")
logging.basicConfig(level=logging.INFO)
logging.getLogger('numexpr.utils').setLevel(logging.ERROR)
class TqdmLoggingHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET):
        super().__init__(level)

    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.tqdm.write(msg)
            self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record) 
log = logging.getLogger (__name__)
log.setLevel (logging.INFO)
log.addHandler (TqdmLoggingHandler ())



class World():
    """
    This is the main container
    """
    def __init__(self, snapshots, simulationID = None, databaseName = 'flexABLE', startingDate = '2018-01-01T00:00:00', writeResultsToDB = False):
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
                
            self.markets['CRM'].step(self.snapshots[self.currstep], self.agents)
            self.markets['DHM'].step(self.snapshots[self.currstep])
            
            for market in self.markets["EOM"].values():
                market.step(self.snapshots[self.currstep],self.agents)
                
            for powerplant in self.powerplants:
                powerplant.step()
                
            for storage in self.storages:
                storage.step()
                
            self.currstep +=1
            
        else:
            logger.info("Reached simulation end")
            
            
    def runSimulation(self):
        start = datetime.now()
        
        if self.writeResultsToDB:
            tempDF = pd.DataFrame(self.dictPFC,
                                  index = pd.date_range(self.startingDate, periods = len(self.snapshots), freq = '15T'),
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
                                  index = pd.date_range(self.startingDate, periods = len(self.snapshots), freq = '15T'),
                                  columns = ['Price']).astype('float64')
            
            self.ResultsWriter.writeDataFrame(tempDF, 'PFC', tags = {'simulationID':self.simulationID, "user": "EOM"})
            
            #writing demand price (default 2999.9), changes if confirmed supply price is higher than demand price
            tempDF = pd.DataFrame(self.IEDPrice,
                                  index=pd.date_range(self.startingDate, periods = len(self.snapshots), freq = '15T'),
                                  columns=['IED_Price']).astype('float64')
            
            self.ResultsWriter.writeDataFrame(tempDF, 'PFC', tags = {'simulationID':self.simulationID, "user": "EOM"})
            
            #save total capacities of power plants
            for powerplant in self.powerplants:
                tempDF = pd.DataFrame(powerplant.dictCapacity,
                                      index = ['Power']).drop([-1], axis = 1).T.set_index(pd.date_range(self.startingDate,
                                                                                                        periods = len(self.snapshots),
                                                                                                        freq = '15T')).astype('float64')
                
                self.ResultsWriter.writeDataFrame(tempDF, 'Power', tags = {'simulationID':self.simulationID,
                                                                           'UnitName':powerplant.name,
                                                                           'Technology':powerplant.technology})
            
            
            #write must-run and flex capacities and corresponding bid prices
            for powerplant in self.powerplants:
                tempDF = pd.DataFrame(powerplant.dictCapacityMR,
                                      index = ['Power_MR', 'MR_Price']).T.set_index(pd.date_range(self.startingDate,
                                                                                                 periods = len(self.snapshots),
                                                                                                 freq = '15T')).astype('float64')
                
                self.ResultsWriter.writeDataFrame(tempDF, 'Capacities', tags = {'simulationID':self.simulationID,
                                                                                'UnitName':powerplant.name,
                                                                                'Technology':powerplant.technology})
                
                tempDF = pd.DataFrame(powerplant.dictCapacityFlex,
                                      index=['Power_Flex','Flex_Price']).T.set_index(pd.date_range(self.startingDate,
                                                                                                   periods = len(self.snapshots),
                                                                                                   freq = '15T')).astype('float64')
                
                self.ResultsWriter.writeDataFrame(tempDF, 'Capacities', tags = {'simulationID':self.simulationID,
                                                                                'UnitName':powerplant.name,
                                                                                'Technology':powerplant.technology})
            
            #write storage capacities
            for powerplant in self.storages:
                tempDF = pd.DataFrame(powerplant.dictCapacity, index=['Power']).T.set_index(pd.date_range(self.startingDate,
                                                                                                          periods = len(self.snapshots),
                                                                                                          freq = '15T')).astype('float64')

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
            
        else:
            logger.info('Saving results into CSV files...')
            
            directory = 'output/{}/'.format(self.scenario)
            if not os.path.exists(directory):
                os.makedirs(directory)
                os.makedirs(directory+'/PP_capacities')
                os.makedirs(directory+'/STO_capacities')
                
            # writing EOM market prices as CSV
            tempDF = pd.DataFrame(self.dictPFC,
                                  index = pd.date_range(self.startingDate, periods = len(self.snapshots), freq = '15T'),
                                  columns = ['Price']).astype('float64')
            
            tempDF.to_csv(directory + 'EOM_Prices.csv')
            
            #save total capacities of power plants as CSV
            for powerplant in self.powerplants:
                tempDF = pd.DataFrame(powerplant.dictCapacity,
                                      index = ['Power']).drop([-1], axis = 1).T.set_index(pd.date_range(self.startingDate,
                                                                                                        periods = len(self.snapshots),
                                                                                                        freq = '15T')).astype('float64')
                                                                                                        
                tempDF.to_csv(directory + 'PP_capacities/{}_Capacity.csv'.format(powerplant.name))
                            
            
            #write storage capacities as CSV
            for powerplant in self.storages:
                tempDF = pd.DataFrame(powerplant.dictCapacity, index=['Power']).T.set_index(pd.date_range(self.startingDate,
                                                                                                          periods = len(self.snapshots),
                                                                                                          freq = '15T')).astype('float64')
                
                tempDF.to_csv(directory + 'STO_capacities/{}_Capacity.csv'.format(powerplant.name))
                
            logger.info('Saving results complete')
            
            
        logger.info("#########################")
        
        
    def loadScenario(self,
                     scenario = "Default",
                     importStorages = False,
                     importCRM = True,
                     importDHM = True,
                     importCBT = True,
                     checkAvailability = False,
                     meritOrder = True,
                     startingPoint = 0):
    
        self.scenario = scenario
        
        if self.simulationID == None:
            self.simulationID = '{}{}{}{}{}{}'.format(scenario,
                                                        '_Sto' if importStorages else '',
                                                        '_CRM' if importCRM else '',
                                                        '_DHM' if importDHM else '',
                                                        '_CBT' if importCBT else '',
                                                        startingPoint)
            
        logger.info("Loading Scenario: {}, SimulationID:{}".format(scenario,self.simulationID))
        
        
        # =====================================================================
        # Load fuel prices and emission factors    
        # =====================================================================
        logger.info("Loading fuel data....")
        
        fuelData = pd.read_csv('input/{}/Fuel.csv'.format(scenario),
                               nrows = len(self.snapshots) + startingPoint,
                               index_col = 0)
        fuelData.drop(fuelData.index[0:startingPoint], inplace = True)
        fuelData.reset_index(drop = True, inplace = True)
        self.fuelPrices=dict(fuelData)
        
        emissionData = pd.read_csv('input/{}/EmissionFactors.csv'.format(scenario), index_col=0)
        self.emissionFactors = dict(emissionData['emissions'])
        
        logger.info("Fuel data loaded.")
        
        
        # =====================================================================
        # Create agents and load power plants    
        # =====================================================================
        logger.info("Loading Agents and assets....")
        
        powerplantsList = pd.read_csv('input/{}/FPP_DE.csv'.format(scenario),
                                      index_col = 0,
                                      encoding = "Latin-1")
        
        # =====================================================================
        # Add all unique agents (power plant operators)    
        # =====================================================================
        for _ in powerplantsList.company.unique():
            self.addAgent(_)
        
        # =====================================================================
        # Add availability information if provided   
        # =====================================================================
        for powerplant, data in powerplantsList.iterrows():
            if checkAvailability:
                try:
                    availability= pd.read_csv('input/{}/Availability/{}.csv'.format(scenario,powerplant),
                                              nrows = len(self.snapshots) + startingPoint,
                                              index_col = 0)
                    
                    availability.drop(availability.index[0:startingPoint], inplace = True)
                    availability.reset_index(drop = True, inplace = True)
                    availability = availability.Total.to_list()
                    
                    self.agents[data['company']].addPowerplant(powerplant, availability = availability, **dict(data))
                
                except FileNotFoundError:
                    self.agents[data['company']].addPowerplant(powerplant,**dict(data))
                    
            else:
                self.agents[data['company']].addPowerplant(powerplant,**dict(data))
        
        
        # =====================================================================
        # Adding storages     
        # =====================================================================
        if importStorages: 
            storageList = pd.read_csv('input/{}/STO_DE.csv'.format(scenario),
                                      index_col = 0,
                                      encoding = "Latin-1")
    
            for _ in storageList.company.unique():
                if _ not in self.agents:
                    self.addAgent(_)
                    
            for storage, data in storageList.iterrows():
                self.agents[data['company']].addStorage(storage, **dict(data))
    
        
    
        # =====================================================================
        # Load renewable power generation  
        # =====================================================================
        vrepowerplantFeedIn = pd.read_csv('input/{}/FES_DE.csv'.format(scenario),
                                          index_col = 0,
                                          nrows = len(self.snapshots) + startingPoint,
                                          encoding = "Latin-1")
        
        vrepowerplantFeedIn.drop(vrepowerplantFeedIn.index[0:startingPoint], inplace = True)
        vrepowerplantFeedIn.reset_index(drop = True, inplace = True)
        
        self.addAgent('Renewables')
        
        for _ in vrepowerplantFeedIn:
            self.agents['Renewables'].addVREPowerplant(_, FeedInTimeseries = vrepowerplantFeedIn[_].to_list())
                
        logger.info("Agents and assets loaded.")
        
        
        # =====================================================================
        # Loads the inelastic demand data and cross border capacities
        # =====================================================================
        logger.info("Loading demand....")
        
        demand = pd.read_csv('input/{}/IED_DE.csv'.format(scenario),
                             nrows  =len(self.snapshots) + startingPoint,
                             index_col = 0)
        demand.drop(demand.index[0:startingPoint], inplace = True)
        demand.reset_index(drop = True, inplace = True)
        
        if importCBT:
            CBT = pd.read_csv('input/{}/CBT_DE.csv'.format(scenario),
                              nrows = len(self.snapshots) + startingPoint,
                              index_col = 0)
            CBT.drop(CBT.index[0:startingPoint], inplace = True)
            CBT.reset_index(drop = True, inplace = True)
            
            self.addMarket('EOM_DE','EOM', demand=dict(demand['demand']), CBtrades = CBT)
            
        else:
            self.addMarket('EOM_DE','EOM', demand=dict(demand['demand']))

        
        # =====================================================================
        # Loads the demand for district heating
        # =====================================================================
        if importDHM:
            logger.info("Loading District heating demand....")
            
            HLP_DH = pd.read_csv('input/{}/HLP_DH_DE.csv'.format(scenario),
                                 nrows = len(self.snapshots) + startingPoint,
                                 index_col = 0)
            HLP_DH.drop(HLP_DH.index[0:startingPoint], inplace = True)
            HLP_DH.reset_index(drop = True, inplace = True)
                        
            annualDemand = pd.read_csv('input/{}/DH_DE.csv'.format(scenario),
                                       index_col=0)
            annualDemand *= 4
            
            self.addMarket('DHM_DE', 'DHM', HLP_DH = HLP_DH, annualDemand = annualDemand)
        
        
        # =====================================================================
        # Loads the control reserve demand
        # =====================================================================
        if importCRM:
            logger.info("Loading control reserve demand....")
            
            CRM = pd.read_csv('input/{}/CRM_DE.csv'.format(scenario),
                              nrows = len(self.snapshots) + startingPoint,
                              index_col = 0)
            CRM.drop(CRM.index[0:startingPoint], inplace = True)
            CRM.reset_index(drop = True, inplace = True)
            
            CRMdemand = {"posCRMDemand":dict(CRM['positive Demand [MW]']),
                         "negCRMDemand":dict(CRM['negative Demand [MW]']),
                         "posCRMCall":dict(CRM['positive Call-Off [MW]']),
                         "negCRMCall":dict(CRM['negative Call-Off [MW]'])}
            
            self.addMarket('CRM_DE','CRM', demand = CRMdemand)
        
        logger.info("Demand data loaded.")
        
        
        # =====================================================================
        # Calculate prce forward curve using simple merit order
        # =====================================================================
        if meritOrder:
            logger.info("Calculating PFC....")
            
            meritOrder = MeritOrder.MeritOrder(demand,
                                               powerplantsList,
                                               vrepowerplantFeedIn,
                                               self.fuelPrices,
                                               self.emissionFactors,
                                               self.snapshots)
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
        
        