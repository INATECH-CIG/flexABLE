# -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 15:56:51 2020

@author: intgridnb-02
"""
import logging
logging.getLogger('pyomo.core').setLevel(logging.ERROR)
import agent
import EOM
import DHM
from loggingGUI import logger
import pandas as pd
from tqdm import tqdm
import CRM
#from NetworkOperator import NetworkOperator
import pypsa
import seaborn as sns
import matplotlib.pyplot as plt
sns.set_style('ticks')
class World():
    """
    This is the main container
    """
    def __init__(self, snapshots, fuelPrices={}, simulationID=None, networkEnabled=False):
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
        self.dictPFC = [0]*snapshots
        self.networkEnabled = networkEnabled
        self.network = pypsa.Network()
        
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
            self.markets['CRM'].step(self.snapshots[self.currstep],self.agents)
            self.markets['DHM'].step(self.snapshots[self.currstep])
            for market in self.markets["EOM"].values():
                market.step(self.snapshots[self.currstep],self.agents)
            #self.network.step()
            for powerplant in self.powerplants:
                powerplant.step()
            for storage in self.storages:
                storage.step()
            self.currstep +=1
        else:
            logger.info("Reached simulation end")
    def runSimulation(self):
        if self.currstep==0: logger.info("Simulation started")
        progressBar = tqdm(total=len(self.snapshots))
        while True:
            if self.currstep < len(self.snapshots):
                self.step()
                progressBar.update(1)
            else:
                break
        logger.info("reached simulation end")
    def loadScenario(self, scenario="Default", importStorages=True, importCRM=True, importDHM=True, addBackup=False):
        # Some of the input files should be restructured such as demand, so it
        # could include more than one zone
        
        # Loads fuel prices from the required Scenario
        if self.simulationID == None:
            self.simulationID = '{}_s{}_c{}_h{}'.format(scenario, importStorages, importCRM, importDHM)
        logger.info("Loading fuel data....")
        fuelData = pd.read_csv('input/{}/Fuel.csv'.format(scenario),
                               nrows=len(self.snapshots),
                               index_col=0)
        self.fuelPrices=dict(fuelData)
        emissionData = pd.read_csv('input/{}/EmissionFactors.csv'.format(scenario),
                                   index_col=0)
        self.emissionFactors = dict(emissionData['emissions'])
        logger.info("Fuel data loaded.")
        # Loads powerplant related data from the required Scenario and creates the agents and powerplants
        logger.info("Loading Agents and assets....")
        powerplantsList = pd.read_csv('input/{}/FPP_DE.csv'.format(scenario),
                              index_col=0,
                              encoding="Latin-1")
        for _ in powerplantsList.company.unique():
            self.addAgent(_)
        for powerplant, data in powerplantsList.iterrows():
            self.agents[data['company']].addPowerplant(powerplant,**dict(data))
        # =====================================================================
        # Adding Storages     
        # =====================================================================
        if importStorages: 
            storageList = pd.read_csv('input/{}/STO_DE.csv'.format(scenario),
                                  index_col=0,
                                  encoding="Latin-1")
    
            for _ in storageList.company.unique():
                if _ not in self.agents:
                    self.addAgent(_)
                    
            for storage, data in storageList.iterrows():
                self.agents[data['company']].addStorage(storage,**dict(data))
    
        if not(self.networkEnabled):           
            vrepowerplantFeedIn =pd.read_csv('input/{}/FES_DE.csv'.format(scenario),
                                             index_col=0,
                                             encoding="Latin-1")
            self.addAgent('Renewables')
            for _ in vrepowerplantFeedIn:
                self.agents['Renewables'].addVREPowerplant(_, FeedInTimeseries=vrepowerplantFeedIn[_].to_list())
        logger.info("Agents and assets loaded.")
        # Loads the inelastic demand data
        # This could be extended with another file that specifies to which zone
        # or market does the demand belong to and automatically loads all required
        # information
        logger.info("Loading demand....")
        demand = pd.read_csv('input/{}/IED_DE.csv'.format(scenario),
                               nrows=len(self.snapshots),
                               index_col=0)
        CBT = pd.read_csv('input/{}/CBT_DE.csv'.format(scenario),
                          nrows=len(self.snapshots),
                          index_col=0)

        {"Import":{t:q for t,q in zip(self.snapshots,CBT["Import"].to_list())},
         "Export":{t:q for t,q in zip(self.snapshots,CBT["Export"].to_list())}}
        self.addMarket('EOM_DE','EOM', demand=dict(demand['demand']), CBtrades=CBT)

        
        logger.info("Loading District heating demand....")
        HLP_DH= pd.read_csv('input/{}/HLP_DH_DE.csv'.format(scenario),
                            nrows=len(self.snapshots),
                               index_col=0)
        HLP_HH= pd.read_csv('input/{}/HLP_HH_DE.csv'.format(scenario),
                            nrows=len(self.snapshots),
                            index_col=0)
        annualDemand= pd.read_csv('input/{}/DH_DE.csv'.format(scenario),
                                  nrows=len(self.snapshots),
                                  index_col=0)
        
        self.addMarket('DHM_DE','DHM', HLP_DH=HLP_DH, HLP_HH=HLP_HH, annualDemand=annualDemand)
        
        logger.info("Loading control reserve demand....")
        CRM= pd.read_csv('input/{}/CRM_DE.csv'.format(scenario),
                            nrows=len(self.snapshots),
                               index_col=0)
        if importCRM ==False:
            CRM = CRM * 0
        CRMdemand = {"posCRMDemand":dict(CRM['positive Demand [MW]']),
                  "negCRMDemand":dict(CRM['negative Demand [MW]']),
                  "posCRMCall":dict(CRM['positive Call-Off [MW]']),
                  "negCRMCall":dict(CRM['negative Call-Off [MW]'])}
        self.addMarket('CRM_DE','CRM', demand=CRMdemand)
        
        logger.info("Demand data loaded.")
        if self.networkEnabled:
            # Loading Network data
            logger.info("Setting up Network.")
            nodes = pd.read_csv('input/{}/nodes.csv'.format(scenario),
                                index_col=0,
                                encoding="Latin-1")
            lines = pd.read_csv('input/{}/lines.csv'.format(scenario),
                                index_col=0,
                                encoding="Latin-1")
            load_distribution = pd.read_csv('input/{}/IED_DE_Distrib.csv'.format(scenario),
                                            nrows=len(self.snapshots),
                                            index_col=0,
                                            encoding="Latin-1")
            self.network.set_snapshots(range(len(self.snapshots)))
            self.network.madd('Bus',
                              nodes.index,
                              x=nodes.x,
                              y=nodes.y)
            if addBackup:
                self.network.madd('Generator',
                                  nodes.index,
                                  suffix='_backup',
                                  bus=nodes.index,
                                  p_nom=100,
                                  p_min_pu=0,
                                  p_max_pu=1,
                                  marginal_cost=3000,
                                  carrier='_backup')
            self.network.madd('Line',
                              lines.index,
                              bus0=lines.bus0,
                              bus1=lines.bus1,
                              x= lines.x,
                              r= lines.r,
                              s_nom= lines.s_nom)
            self.network.madd('Load',
                              nodes.index,
                              suffix='_load',
                              bus=nodes.index,
                              p_set=load_distribution.mul(demand.demand,axis=0))
            self.network.madd('Generator',
                              powerplantsList.index,
                              suffix='_mrEOM',
                              carrier= powerplantsList.technology,
                              bus=powerplantsList.node,
                              p_nom=powerplantsList.maxPower,
                              p_min_pu=0,
                              p_max_pu=1)
            self.network.madd('Generator',
                              powerplantsList.index,
                              suffix='_flexEOM',
                              carrier= powerplantsList.technology,
                              bus=powerplantsList.node,
                              p_nom=powerplantsList.maxPower,
                              p_min_pu=0,
                              p_max_pu=1)
            
            
            
            # vrepowerplantFeedIn =pd.read_csv('input/{}/FES_DE.csv'.format(scenario),
            #                                  index_col=0,
            #                                  encoding="Latin-1")
            # self.addAgent('Renewables')
            # for _ in vrepowerplantFeedIn:
            #     self.agents['Renewables'].addVREPowerplant(_, FeedInTimeseries=vrepowerplantFeedIn[_].to_list())
            # self.network = NetworkOperator(importCSV=True, world=self)
            logger.info("Network Loaded.")
        
if __name__=="__main__":
    logger.info("Script started")
    snapLength = 96*1
    example = World(snapLength, networkEnabled=True)
    
    pfc = pd.read_csv("input/2016/PFC_run1.csv", nrows = snapLength, index_col=0)
    example.dictPFC = list(pfc['price'])
    
    example.loadScenario(scenario='2015_Network', importStorages=False, importCRM=True,addBackup=True)


    example.runSimulation()
    
    example.markets["EOM"]['EOM_DE'].plotResults()

    #example.storages[0].plotResults()
    example.powerplants[0].plotResults()
    example.powerplants[1].plotResults()
    # example.powerplants[1].plotResults()
    
#%% Plot
colors = {'Waste':'brown',
          'nuclear':'#FF3232',
          'lignite':'brown',
          'hard coal':'k',
          'combined cycle gas turbine':'orange',
          'oil':'#000000',
          'open cycle gas turbine':'navy',
          '_backup':'lightsteelblue',
          'Hydro':'mediumblue',
          'Biomass':'forestgreen',
          'PV':'yellow',
          'Wind Onshore':'blue',
          'Wind Offshore':'blue',}


p_by_carrier = example.network.generators_t.p.groupby(example.network.generators.carrier, axis=1).sum()


cols = ['nuclear','lignite', 'hard coal','oil', '_backup', 'combined cycle gas turbine',
         'open cycle gas turbine']
p_by_carrier = p_by_carrier[cols]

fig,ax = plt.subplots(1,1)

fig.set_size_inches(12,6)

(p_by_carrier/1e3).plot(kind="area",ax=ax,
                        linewidth=0,
                        color=[colors[col] for col in p_by_carrier.columns],
                        alpha=0.7)


ax.legend(ncol=4,loc="upper left")

ax.set_ylabel("GW")

# ax.set_xlabel("")