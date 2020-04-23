# -*- coding: utf-8 -*-
"""
Created on Mon Apr  6 15:56:51 2020

@author: intgridnb-02
"""

import agent
import EOM
import DHM
from loggingGUI import logger
import pandas as pd
from tqdm import tqdm
import time
import random
import crm as CRM
class World():
    """
    This is the main container
    """
    def __init__(self, snapshots, fuelPrices={}):
        self.powerplants=[]
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
        self.dictPFC = {n:0 for n in self.snapshots}
        
    def addAgent(self, name):
        self.agents[name] = agent.Agent(name, snapshots=self.snapshots , world=self)
        
    def addMarket(self, name, marketType, demand=None, CBtrades=None, HLP_DH=None, HLP_HH=None, annualDemand=None):
        if marketType == "EOM":
            self.markets["EOM"][name] = EOM.EOM(name, demand=demand, CBtrades=CBtrades, world=self)
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
            for powerplant in self.powerplants:
                powerplant.step()
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
    def loadScenario(self, scenario="Default"):
        # Some of the input files should be restructured such as demand, so it
        # could include more than one zone
        
        # Loads fuel prices from the required Scenario
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
        CRMdemand = {"posCRMDemand":dict(CRM['positive Demand [MW]']),
                  "negCRMDemand":dict(CRM['negative Demand [MW]']),
                  "posCRMCall":dict(CRM['positive Call-Off [MW]']),
                  "negCRMCall":dict(CRM['negative Call-Off [MW]'])}
        self.addMarket('CRM_DE','CRM', demand=CRMdemand)
        
        logger.info("Demand data loaded.")
        
if __name__=="__main__":
    #loggerGUI()
    logger.info("Script started")
    snapLength = 96*1
    example = World(snapLength)
    example.loadScenario(scenario='2016')
    example.dictPFC = {0: 30.84,
 1: 21.08504504504505,
 2: 21.243120567375886,
 3: 21.303333333333335,
 4: 20.594285714285714,
 5: 19.811174042302337,
 6: 19.374285714285712,
 7: 19.23428571428572,
 8: 19.23428571428572,
 9: 19.084999999999994,
 10: 18.954343434343436,
 11: 18.92215053763441,
 12: 19.61120865899329,
 13: 20.693733867073355,
 14: 19.084999999999994,
 15: 18.86833333333333,
 16: 19.21,
 17: 20.938494623655913,
 18: 19.084999999999994,
 19: 20.932150537634406,
 20: 20.984343434343437,
 21: 19.989333234965397,
 22: 20.99832298136646,
 23: 21.003333333333337,
 24: 19.084999999999994,
 25: 19.461520507662378,
 26: 20.932150537634406,
 27: 21.006204278812977,
 28: 21.08504504504505,
 29: 21.006204278812977,
 30: 21.506021505376346,
 31: 20.58481023266654,
 32: 21.63215053763441,
 33: 21.584036278863227,
 34: 21.243120567375886,
 35: 22.271627486437612,
 36: 22.174027777777784,
 37: 22.584285714285713,
 38: 22.536666666666665,
 39: 22.550952380952378,
 40: 22.6975,
 41: 23.08820512820513,
 42: 23.16875,
 43: 23.534285714285716,
 44: 23.42712157888149,
 45: 23.68,
 46: 23.68,
 47: 23.68,
 48: 23.68,
 49: 23.68,
 50: 23.68,
 51: 23.68,
 52: 23.559259259259257,
 53: 23.487291666666668,
 54: 23.68,
 55: 23.68,
 56: 23.68,
 57: 23.68,
 58: 23.68,
 59: 23.68,
 60: 23.867609961120294,
 61: 24.31,
 62: 24.63,
 63: 24.69,
 64: 24.69,
 65: 25.168333333333333,
 66: 25.516666666666666,
 67: 26.054705882352938,
 68: 26.29,
 69: 26.16156028368794,
 70: 26.296666666666667,
 71: 26.426034046468832,
 72: 26.42,
 73: 26.29,
 74: 26.119334393930675,
 75: 25.848400412257178,
 76: 25.94777487055511,
 77: 24.9989649446335,
 78: 25.29,
 79: 24.69,
 80: 24.31,
 81: 24.63,
 82: 23.68,
 83: 23.68,
 84: 23.559814814814814,
 85: 23.68,
 86: 23.01594202898551,
 87: 23.559259259259257,
 88: 23.68,
 89: 23.68,
 90: 22.536666666666665,
 91: 22.550952380952378,
 92: 21.243120567375886,
 93: 20.785053763440857,
 94: 19.974285714285713,
 95: 19.532150537634408}
    example.runSimulation()
    
    example.markets["EOM"]['EOM_DE'].plotResults()
    #example.markets["DHM"].plotResults()