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
# import EOM_v2 as EOM
from .import EOM
from .import DHM
from .import CRM
from .import MeritOrder
from .import resultsWriter

import pandas as pd
#from tqdm import tqdm

#from NetworkOperator import NetworkOperator
# Managing the logger and TQDM, PyPSA had to be imported after logging to set
# logging level correctly
import logging
import pypsa
pypsa.pf.logger.setLevel(logging.ERROR)
pypsa.opf.logger.setLevel(logging.ERROR)
pypsa.linopf.logger.setLevel(logging.ERROR)
logger = logging.getLogger("flexABLE")
logging.basicConfig(level=logging.INFO)
logging.getLogger('pyomo.core').setLevel(logging.ERROR)
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


from datetime import datetime
# Plotting packages




class World():
    """
    This is the main container
    """
    def __init__(self, snapshots, simulationID=None, networkEnabled=False, databaseName='flexABLE',startingDate='2018-01-01T00:00:00', writeResultsToDB=True):
        self.simulationID = simulationID
        self.powerplants=[]
        self.storages = []
        self.agents = {}
        self.markets = {"EOM":{},
                        "CRM":{}}
        if type(snapshots) == int:
            self.snapshots = list(range(snapshots))
        elif type(snapshots) == list:
            self.snapshots = snapshots
        self.currstep = 0
        self.fuelPrices={}
        self.emissionFactors = {}
        
        self.minBidEOM =1
        self.minBidCRM =5
        self.minBidDHM =1
        self.minBidReDIS =1
        self.dt = 0.25 # Although we are always dealing with power, dt is needed to calculate the revenue and for the energy market
        self.dtu = 16 # The frequency of reserve market
        self.dictPFC = [0]*snapshots # This is an artifact and should be removed
        self.PFC = [0]*snapshots
        self.EOMResult = [0]*snapshots
        self.IEDPrice = [2999.9]*snapshots
        self.networkEnabled = None
        self.network = None
        self.demandDistrib = None
        self.startingDate=startingDate
        self.writeResultsToDB = writeResultsToDB
        if writeResultsToDB:
            self.ResultsWriter = resultsWriter.ResultsWriter(databaseName=databaseName,
                                                            simulationID=simulationID,
                                                            startingDate=startingDate,
                                                            world=self)
    def addAgent(self, name):
        self.agents[name] = agent.Agent(name, snapshots=self.snapshots , world=self)
        
    def addMarket(self, name, marketType, demand=None, CBtrades=None, HLP_DH=None, HLP_HH=None, annualDemand=None):
        if marketType == "EOM":
            self.markets["EOM"][name] = EOM.EOM(name, demand=demand, CBtrades=CBtrades,
                                                networkEnabled= self.networkEnabled, world=self)
        if marketType == "DHM":
            self.markets["DHM"] = DHM.DHM(name, HLP_DH=HLP_DH, HLP_HH=HLP_HH, annualDemand=annualDemand, world=self)
        if marketType == "CRM":
            self.markets["CRM"] = CRM.CRM(name, demand=demand, world=self)
    def step(self):

        if self.currstep < len(self.snapshots):
            for powerplant in self.powerplants:
                powerplant.checkAvailability(self.snapshots[self.currstep])
            self.markets['CRM'].step(self.snapshots[self.currstep],self.agents)
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
            tempDF = pd.DataFrame(self.dictPFC,index=pd.date_range(self.startingDate, periods=len(self.snapshots), freq='15T') ,columns=['Merit Order Price'])
            tempDF['Merit Order Price']= tempDF['Merit Order Price'].astype('float64')
            self.ResultsWriter.writeDataFrame(tempDF,'PFC',
                                        tags={'simulationID':self.simulationID,
                                            "user": "EOM"})
        logger.info("######## Simulation Started ########")
        logger.info('Started at: {}'.format(start))
        #progressBar = tqdm(total=len(self.snapshots), position=1, leave=True)
        for _ in self.snapshots:
            self.step()
            
        finished = datetime.now()
        logger.info('Simulation finished at: {}'.format(finished))
        logger.info('Simulation time: {}'.format(finished - start))
        
        if self.writeResultsToDB:
            start = datetime.now()
            logger.info('Writing Capacities in Server - This may take couple of minutes.')
            
            tempDF = pd.DataFrame(self.dictPFC,index=pd.date_range(self.startingDate, periods=len(self.snapshots), freq='15T') ,columns=['Price'])
            tempDF['Price']= tempDF['Price'].astype('float64')
            self.ResultsWriter.writeDataFrame(tempDF,'PFC',
                                        tags={'simulationID':self.simulationID,
                                            "user": "EOM"})
            tempDF = pd.DataFrame(self.IEDPrice,index=pd.date_range(self.startingDate, periods=len(self.snapshots), freq='15T') ,columns=['IED_Price'])
            tempDF['IED_Price']= tempDF['IED_Price'].astype('float64')
            self.ResultsWriter.writeDataFrame(tempDF,'PFC',
                                        tags={'simulationID':self.simulationID,
                                            "user": "EOM"})
            for powerplant in self.powerplants:
                tempDF = pd.DataFrame(powerplant.dictCapacity, index=['Power']).drop([-1],axis=1).T.set_index(pd.date_range(self.startingDate, periods=len(self.snapshots), freq='15T'))
                tempDF['Power']= tempDF['Power'].astype('float64')
                
                self.ResultsWriter.writeDataFrame(tempDF,'Power',
                                            tags={'simulationID':self.simulationID,
                                                'UnitName':powerplant.name,
                                                'Technology':powerplant.technology})
            
            for powerplant in self.powerplants:
                tempDF = pd.DataFrame(powerplant.dictCapacityMR, index=['Power_MR','MR_Price']).T.set_index(pd.date_range(self.startingDate, periods=len(self.snapshots), freq='15T'))
                tempDF['Power_MR']= tempDF['Power_MR'].astype('float64')
                tempDF['MR_Price']= tempDF['MR_Price'].astype('float64')
                
                self.ResultsWriter.writeDataFrame(tempDF,'Capacities',
                                            tags={'simulationID':self.simulationID,
                                                'UnitName':powerplant.name,
                                                'Technology':powerplant.technology})
                tempDF = pd.DataFrame(powerplant.dictCapacityFlex, index=['Power_Flex','Flex_Price']).T.set_index(pd.date_range(self.startingDate, periods=len(self.snapshots), freq='15T'))
                tempDF['Power_Flex']= tempDF['Power_Flex'].astype('float64')
                tempDF['Flex_Price']= tempDF['Flex_Price'].astype('float64')
                
                self.ResultsWriter.writeDataFrame(tempDF,'Capacities',
                                            tags={'simulationID':self.simulationID,
                                                'UnitName':powerplant.name,
                                                'Technology':powerplant.technology})
                
            for powerplant in self.storages:
                tempDF = pd.DataFrame(powerplant.dictCapacity, index=['Power']).T.set_index(pd.date_range(self.startingDate, periods=len(self.snapshots), freq='15T'))
                tempDF['Power']= tempDF['Power'].astype('float64')
                self.ResultsWriter.writeDataFrame(tempDF.clip(upper=0),'Power',
                                            tags={'simulationID':self.simulationID,
                                                'UnitName':powerplant.name+'_charge',
                                                'direction':'charge',
                                                'Technology':powerplant.technology})
                self.ResultsWriter.writeDataFrame(tempDF.clip(lower=0),'Power',
                                            tags={'simulationID':self.simulationID,
                                                'UnitName':powerplant.name+'_discharge',
                                                'direction':'discharge',
                                                'Technology':powerplant.technology})
            finished = datetime.now()
            logger.info('Writing results into database finished at: {}'.format(finished))
            logger.info('Saving into database time: {}'.format(finished - start))
        logger.info("#########################")
    def loadScenario(self, scenario="Default",
                     importStorages=False,
                     importCRM=True,
                     importDHM=True,
                     meritOrder=True,
                     addBackup=False,
                     CBTransfers=False,
                     CBTMainland=None,
                     startingPoint=0,
                     line_expansion= 1.5,
                     line_expansion_price=1000,
                     backupPerNode = 1000):
        # Some of the input files should be restructured such as demand, so it
        # could include more than one zone
        
        # Loads fuel prices from the required Scenario
        if self.simulationID == None:
            self.simulationID = '{}{}{}{}{}{}{}'.format(scenario,
                                                        '_Sto' if importStorages else '',
                                                        '_CRM' if importCRM else '',
                                                        '_DHM' if importDHM else '',
                                                        '_Net' if self.networkEnabled else '',
                                                        '_CBT' if CBTransfers else '',
                                                        startingPoint)
        logger.info("Loading Scenario: {}, SimulationID:{}".format(scenario,self.simulationID))
        logger.info("Loading fuel data....")
        fuelData = pd.read_csv('{}/Fuel.csv'.format(scenario),
                               nrows=len(self.snapshots)+startingPoint,
                               index_col=0)
        fuelData.drop(fuelData.index[0:startingPoint],inplace=True)
        fuelData.reset_index(drop=True,inplace=True)
        self.fuelPrices=dict(fuelData)
        emissionData = pd.read_csv('{}/EmissionFactors.csv'.format(scenario),
                                   index_col=0)
        self.emissionFactors = dict(emissionData['emissions'])
        logger.info("Fuel data loaded.")
        # Loads powerplant related data from the required Scenario and creates the agents and powerplants
        logger.info("Loading Agents and assets....")
        powerplantsList = pd.read_csv('{}/FPP_DE.csv'.format(scenario),
                              index_col=0,
                              encoding="Latin-1")
        for _ in powerplantsList.company.unique():
            self.addAgent(_)
        for powerplant, data in powerplantsList.iterrows():
            try:
                availability= pd.read_csv('{}/Availability/{}.csv'.format(scenario,powerplant),
                                          nrows=len(self.snapshots)+startingPoint,
                                          index_col=0)
                availability.drop(availability.index[0:startingPoint],inplace=True)
                availability.reset_index(drop=True,inplace=True)
                availability=availability.Total.to_list()
                self.agents[data['company']].addPowerplant(powerplant, availability=availability,**dict(data))
            except FileNotFoundError:
                self.agents[data['company']].addPowerplant(powerplant,**dict(data))
        # =====================================================================
        # Adding Storages     
        # =====================================================================
        if importStorages: 
            storageList = pd.read_csv('{}/STO_DE.csv'.format(scenario),
                                  index_col=0,
                                  encoding="Latin-1")
    
            for _ in storageList.company.unique():
                if _ not in self.agents:
                    self.addAgent(_)
                    
            for storage, data in storageList.iterrows():
                self.agents[data['company']].addStorage(storage,**dict(data))
    
        if not(self.networkEnabled):           
            vrepowerplantFeedIn =pd.read_csv('{}/FES_DE.csv'.format(scenario),
                                             index_col=0,
                                             nrows=len(self.snapshots)+startingPoint,
                                             encoding="Latin-1")
            vrepowerplantFeedIn['Solar [MW]'] = vrepowerplantFeedIn['Solar [MW]']*1.25
            vrepowerplantFeedIn.drop(vrepowerplantFeedIn.index[0:startingPoint],inplace=True)
            vrepowerplantFeedIn.reset_index(drop=True,inplace=True)
            self.addAgent('Renewables')
            for _ in vrepowerplantFeedIn:
                self.agents['Renewables'].addVREPowerplant(_, FeedInTimeseries=vrepowerplantFeedIn[_].to_list())
        logger.info("Agents and assets loaded.")
        # Loads the inelastic demand data
        # This could be extended with another file that specifies to which zone
        # or market does the demand belong to and automatically loads all required
        # information
        logger.info("Loading demand....")
        demand = pd.read_csv('{}/IED_DE.csv'.format(scenario),
                               nrows=len(self.snapshots)+startingPoint,
                               index_col=0)
        demand.drop(demand.index[0:startingPoint],inplace=True)
        demand.reset_index(drop=True,inplace=True)
        CBT = pd.read_csv('{}/CBT_DE.csv'.format(scenario),
                          nrows=len(self.snapshots)+startingPoint,
                          index_col=0)
        CBT.drop(CBT.index[0:startingPoint],inplace=True)
        CBT.reset_index(drop=True,inplace=True)
        

        CBT["Import"]=CBT["Import"]*CBTransfers
        CBT["Export"]=CBT["Export"]*CBTransfers
        self.addMarket('EOM_DE','EOM', demand=dict(demand['demand']), CBtrades=CBT)

        
        logger.info("Loading District heating demand....")
        HLP_DH= pd.read_csv('{}/HLP_DH_DE.csv'.format(scenario),
                            nrows=len(self.snapshots)+startingPoint,
                               index_col=0)
        HLP_DH.drop(HLP_DH.index[0:startingPoint],inplace=True)
        HLP_DH.reset_index(drop=True,inplace=True)
        HLP_HH= pd.read_csv('{}/HLP_HH_DE.csv'.format(scenario),
                            nrows=len(self.snapshots)+startingPoint,
                            index_col=0)
        HLP_HH.drop(HLP_HH.index[0:startingPoint],inplace=True)
        HLP_HH.reset_index(drop=True,inplace=True)
        annualDemand= pd.read_csv('{}/DH_DE.csv'.format(scenario),
                                  index_col=0)
        annualDemand *=4
        self.addMarket('DHM_DE','DHM', HLP_DH=HLP_DH, HLP_HH=HLP_HH, annualDemand=annualDemand)
        
        logger.info("Loading control reserve demand....")
        CRM= pd.read_csv('{}/CRM_DE.csv'.format(scenario),
                            nrows=len(self.snapshots)+startingPoint,
                               index_col=0)
        CRM.drop(CRM.index[0:startingPoint],inplace=True)
        CRM.reset_index(drop=True,inplace=True)
        if importCRM ==False:
            CRM = CRM * 0
        CRMdemand = {"posCRMDemand":dict(CRM['positive Demand [MW]']),
                  "negCRMDemand":dict(CRM['negative Demand [MW]']),
                  "posCRMCall":dict(CRM['positive Call-Off [MW]']),
                  "negCRMCall":dict(CRM['negative Call-Off [MW]'])}
        self.addMarket('CRM_DE','CRM', demand=CRMdemand)
        
        logger.info("Demand data loaded.")
        
        if meritOrder:
            logger.info("Calculating PFC....")
            meritOrder = MeritOrder.MeritOrder(demand, powerplantsList, vrepowerplantFeedIn, self.fuelPrices, self.emissionFactors, self.snapshots)
            self.dictPFC = meritOrder.PFC()
            self.PFC = self.dictPFC.copy()
            logger.info("Merit Order calculated.")
        if self.networkEnabled:
            # Loading Network data
            logger.info("Setting up Network.")
            self.network = pypsa.Network()
            nodes = pd.read_csv('{}/nodes.csv'.format(scenario),
                                index_col=0,
                                encoding="Latin-1")
            nodes.region = nodes.region.astype(int).astype(str)
            lines = pd.read_csv('{}/lines.csv'.format(scenario),
                                index_col=0,
                                encoding="Latin-1")
            load_distribution = pd.read_csv('{}/IED_DE_Distrib.csv'.format(scenario),
                                            nrows=len(self.snapshots)+startingPoint,
                                            index_col=0,
                                            encoding="Latin-1")
            self.demandDistrib =load_distribution.mul(demand.demand,axis=0)
            PV_CF = pd.read_csv('{}/PV_CF.csv'.format(scenario),
                                            nrows=len(self.snapshots)+startingPoint,
                                            index_col=0,
                                            encoding="Latin-1")
            PV_CF.drop(PV_CF.index[0:startingPoint],inplace=True)
            PV_CF.reset_index(drop=True,inplace=True)
            wind_CF = pd.read_csv('{}/wind_CF.csv'.format(scenario),
                                            nrows=len(self.snapshots)+startingPoint,
                                            index_col=0,
                                            encoding="Latin-1")
            wind_CF.drop(wind_CF.index[0:startingPoint],inplace=True)
            wind_CF.reset_index(drop=True,inplace=True)

            self.network.madd('Bus',
                              nodes.index,
                              x=nodes.x,
                              y=nodes.y)
            if addBackup:
                self.network.madd('Generator',
                                  nodes.index,
                                  suffix='_backupP',
                                  bus=nodes.index,
                                  p_nom=backupPerNode,
                                  p_min_pu=0,
                                  p_max_pu=1,
                                  marginal_cost=75,
                                  carrier='backup_pos')
                self.network.madd('Generator',
                                  nodes.index,
                                  suffix='_backupN',
                                  bus=nodes.index,
                                  p_nom=backupPerNode,
                                  p_min_pu=0,
                                  p_max_pu=1,
                                  sign=-1,
                                  marginal_cost=75,
                                  carrier='backup_neg')
            if CBTransfers:
                self.network.madd('Generator',
                                  nodes[nodes.country !='DE'].index,
                                  suffix='_Export',
                                  bus=nodes[nodes.country !='DE'].index,
                                  p_nom=nodes[nodes.country !='DE'].InstalledConCapacity,
                                  p_min_pu=0,
                                  p_max_pu=1,
                                  sign=-1,
                                  marginal_cost=nodes[nodes.country !='DE'].averageMC,
                                  carrier='Export')
                self.network.madd('Generator',
                                  nodes[nodes.country !='DE'].index,
                                  suffix='_Import',
                                  bus=nodes[nodes.country !='DE'].index,
                                  p_nom=nodes[nodes.country !='DE'].InstalledConCapacity,
                                  p_min_pu=0,
                                  p_max_pu=1,
                                  sign=-1,
                                  marginal_cost=-nodes[nodes.country !='DE'].averageMC,
                                  carrier='Import')
            self.network.madd('Line',
                              lines.index,
                              bus0=lines.bus0,
                              bus1=lines.bus1,
                              x= lines.x,
                              r= lines.r,
                              s_nom= lines.s_nom,
                              s_nom_extendable=True,
                              s_nom_max=lines.s_nom*line_expansion,
                              s_nom_min=lines.s_nom*1.30,
                              capital_cost=line_expansion_price)
            self.network.madd('Load',
                              nodes.index,
                              suffix='_load',
                              bus=nodes.index,
                              p_set=0)
            self.network.madd('Load',
                              nodes.index,
                              suffix='_mcFeedIn',
                              sign=1,
                              bus=nodes.index,
                              p_set=0)
            self.network.madd('Generator',
                              powerplantsList[powerplantsList.Redispatch == True].index,
                              suffix='_mrEOM_posRedis',
                              carrier= powerplantsList.technology + '_pos',
                              bus=powerplantsList.node,
                              p_nom=powerplantsList.maxPower,
                              p_min_pu=0,
                              p_max_pu=1)
            self.network.madd('Generator',
                              powerplantsList[powerplantsList.Redispatch == True].index,
                              suffix='_flexEOM_posRedis',
                              carrier= powerplantsList.technology + '_pos',
                              bus=powerplantsList.node,
                              p_nom=powerplantsList.maxPower,
                              p_min_pu=0,
                              p_max_pu=1)
            self.network.madd('Generator',
                              powerplantsList[powerplantsList.Redispatch == True].index,
                              suffix='_mrEOM_negRedis',
                              carrier= powerplantsList.technology + '_neg',
                              bus=powerplantsList.node,
                              p_nom=powerplantsList.maxPower,
                              p_min_pu=-1,
                              p_max_pu=0)
            self.network.madd('Generator',
                              powerplantsList[powerplantsList.Redispatch == True].index,
                              suffix='_flexEOM_negRedis',
                              carrier= powerplantsList.technology + '_neg',
                              bus=powerplantsList.node,
                              p_nom=powerplantsList.maxPower,
                              p_min_pu=-1,
                              p_max_pu=0)
            self.addAgent('Renewables')
            for _ , data in nodes.iterrows():
                if data.PV:
                    self.network.add('Generator',
                                      "{}_PV_negRedis".format(_),
                                      bus=_,
                                      p_nom=data.PV,
                                      p_min_pu=-1,
                                      p_max_pu=0,
                                      marginal_cost=0,
                                      carrier='PV_neg')
                    self.agents['Renewables'].addVREPowerplant("{}_PV".format(_),
                                                               FeedInTimeseries=(PV_CF[str(data.region)]*data.PV).to_list(),
                                                               node=_)
                if data.windOff:
                    self.network.add('Generator',
                                      "{}_windOff_negRedis".format(_),
                                      bus=_,
                                      p_nom=data.windOff,
                                      p_min_pu=-1,
                                      p_max_pu=0,
                                      marginal_cost=0,
                                      carrier='Wind Offshore_neg')
                    self.agents['Renewables'].addVREPowerplant("{}_windOff".format(_),
                                                               FeedInTimeseries=(wind_CF[str(_)]*data.windOff).to_list(),
                                                               node=_)
                if data.windOn:
                    self.network.add('Generator',
                                      "{}_windOn_negRedis".format(_),
                                      bus=_,
                                      p_nom=data.windOn,
                                      p_min_pu=-1,
                                      p_max_pu=0,
                                      marginal_cost=0,
                                      carrier='Wind Onshore_neg')
                    self.agents['Renewables'].addVREPowerplant("{}_windOn".format(_),
                                                               FeedInTimeseries=(wind_CF[str(_)]*data.windOn).to_list(),
                                                               node=_)
                # if data.BIO:
                #     self.networ02k.add('Generator',
                #                       "{}_Bio".format(_),
                #                       bus=_,
                #                       p_nom=data.BIO,
                #                       p_min_pu=0,
                #                       p_max_pu=1,
                #                       marginal_cost=0,
                #                       carrier='Biomass')
                #     self.agents['Renewables'].addVREPowerplant("{}_Bio".format(_),
                #                                                FeedInTimeseries=[data.BIO]*len(self.snapshots),
                #                                                node=_)   
            if importStorages: 
                self.network.madd('Generator',
                                  storageList.index,
                                  suffix='_supplyEOM_posRedis',
                                  carrier= 'PSPP_discharge_pos',
                                  bus=storageList.node,
                                  p_nom=0,
                                  p_min_pu=0,
                                  p_max_pu=1)
                self.network.madd('Generator',
                                  storageList.index,
                                  suffix='_demandEOM_posRedis',
                                  carrier= 'PSPP_charge_pos',
                                  bus=storageList.node,
                                  p_nom=0,
                                  sign=-1,
                                  p_min_pu=-1,
                                  p_max_pu=0)
                self.network.madd('Generator',
                                  storageList.index,
                                  suffix='_supplyEOM_negRedis',
                                  carrier= 'PSPP_discharge_neg',
                                  bus=storageList.node,
                                  p_nom=0,
                                  p_min_pu=-1,
                                  p_max_pu=0)
                self.network.madd('Generator',
                                  storageList.index,
                                  suffix='_demandEOM_negRedis',
                                  carrier= 'PSPP_charge_neg',
                                  bus=storageList.node,
                                  p_nom=0,
                                  sign=-1,
                                  p_min_pu=0,
                                  p_max_pu=1)
            logger.info("Network Loaded.")
        
if __name__=="__main__":
    scenarios = [(2016,1)]#,(2017,365),(2018,365),(2019,365)]
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
                        simulationID='debugging_energyCharts', startingDate=timeStamps[startingPoint])
    
        
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
        