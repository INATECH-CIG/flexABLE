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
import agent
import EOM
import DHM
import CRM
import resultsWriter

import pandas as pd
from tqdm import tqdm

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
import seaborn as sns
import matplotlib.pyplot as plt
sns.set_style('ticks')



class World():
    """
    This is the main container
    """
    def __init__(self, snapshots, fuelPrices={}, simulationID=None, networkEnabled=False, databaseName='flexABLE',startingDate='2018-01-01T00:00:00'):
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
        self.demandDistrib = None
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
        start = datetime.now()
        logger.info("######## Simulation Started ########")
        logger.info('Started at: {}'.format(start))
        progressBar = tqdm(total=len(self.snapshots))
        while True:
            if self.currstep < len(self.snapshots):
                self.step()
                progressBar.update(1)
            else:
                break
        finished = datetime.now()
        logger.info('Simulation finished at: {}'.format(finished))
        logger.info('Simulation time: {}'.format(finished - start))
        logger.info("#########################")
    def loadScenario(self, scenario="Default", importStorages=True, importCRM=True, importDHM=True, addBackup=False, CBTransfers=False, CBTMainland=None):
        # Some of the input files should be restructured such as demand, so it
        # could include more than one zone
        
        # Loads fuel prices from the required Scenario
        if self.simulationID == None:
            self.simulationID = '{}{}{}{}{}{}'.format(scenario,
                                                                          '_Sto' if importStorages else '',
                                                                          '_CRM' if importCRM else '',
                                                                          '_DHM' if importDHM else '',
                                                                          '_Net' if self.networkEnabled else '',
                                                                          '_CBT' if CBTransfers else '',)
        logger.info("Loading Scenario: {}, SimulationID:{}".format(scenario,self.simulationID))
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
                                             nrows=len(self.snapshots),
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
            nodes.region = nodes.region.astype(int).astype(str)
            lines = pd.read_csv('input/{}/lines.csv'.format(scenario),
                                index_col=0,
                                encoding="Latin-1")
            load_distribution = pd.read_csv('input/{}/IED_DE_Distrib.csv'.format(scenario),
                                            nrows=len(self.snapshots),
                                            index_col=0,
                                            encoding="Latin-1")
            self.demandDistrib =load_distribution.mul(demand.demand,axis=0)
            PV_CF = pd.read_csv('input/{}/PV_CF.csv'.format(scenario),
                                            nrows=len(self.snapshots),
                                            index_col=0,
                                            encoding="Latin-1")
            wind_CF = pd.read_csv('input/{}/wind_CF.csv'.format(scenario),
                                            nrows=len(self.snapshots),
                                            index_col=0,
                                            encoding="Latin-1")
            #self.network.set_snapshots(range(len(self.snapshots)))
            self.network.madd('Bus',
                              nodes.index,
                              x=nodes.x,
                              y=nodes.y)
            if addBackup:
                self.network.madd('Generator',
                                  nodes.index,
                                  suffix='_backupP',
                                  bus=nodes.index,
                                  p_nom=1000,
                                  p_min_pu=0,
                                  p_max_pu=1,
                                  marginal_cost=3000,
                                  carrier='backup_pos')
                self.network.madd('Generator',
                                  nodes.index,
                                  suffix='_backupN',
                                  bus=nodes.index,
                                  p_nom=1000,
                                  p_min_pu=0,
                                  p_max_pu=1,
                                  sign=-1,
                                  marginal_cost=3000,
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
                              s_nom_max=lines.s_nom*1.0,
                              s_nom_min=lines.s_nom,
                              capital_cost=20000)
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
                              powerplantsList.index,
                              suffix='_mrEOM_negRedis',
                              carrier= powerplantsList.technology + '_neg',
                              bus=powerplantsList.node,
                              p_nom=powerplantsList.maxPower,
                              p_min_pu=-1,
                              p_max_pu=0)
            self.network.madd('Generator',
                              powerplantsList.index,
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
                                      marginal_cost=-500,
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
                                      marginal_cost=-500,
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
                                      marginal_cost=-500,
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


    snapLength = 96*4
    networkEnabled=True
    importStorages=True
    importCRM=True
    addBackup=True
    CBTransfers=False
    CBTMainland='DE'
    example = World(snapLength, networkEnabled=networkEnabled, simulationID='Testing')
    
    pfc = pd.read_csv("input/2016/PFC_run1.csv", nrows = snapLength, index_col=0)
    
    example.dictPFC = list(pfc['price'])

    example.loadScenario(scenario='2015_Network',
                         importStorages=importStorages,
                         importCRM=importCRM,
                         addBackup=addBackup,
                         CBTransfers=CBTransfers,
                         CBTMainland=CBTMainland)

    example.runSimulation()
    

    
    if importStorages:
        example.storages[0].plotResults()
    #%%%
    import math 
    Tot=9
    Cols = math.ceil(Tot*(0.5))

    Rows = Tot // Cols 
    Rows += Tot % Cols
    fig,ax = plt.subplots(Rows,Cols)
    for _ in range(Tot):
        example.powerplants[_].plotResults(ax=ax[_//Cols][_%Cols], legend=False)
    
    handles, labels = ax[0][0].get_legend_handles_labels()
    fig.legend(handles, labels)    
    plt.show()
    #%% plot EOM prices
    def two_scales(ax1, time, data1, data2, c1, c2):
    
        ax2 = ax1.twinx()
    
        ax1.step(time, data1, color=c1)
        ax1.set_xlabel('snapshot')
        ax1.set_ylabel('Demand [MW/Snapshot]')
    
        ax2.step(time, data2, color=c2)
        ax2.set_ylabel('Market Clearing Price [€/MW]')
        return ax1, ax2
    
    t = range(len(example.dictPFC)-4)
    s1 = list(example.markets["EOM"]['EOM_DE'].demand.values())[:-4]
    s2 = example.dictPFC[:-4]
    # Create axes
    fig, ax = plt.subplots()
    ax1, ax2 = two_scales(ax, t, s1, s2, 'r', 'b')
    
    
    # Change color of each axis
    def color_y_axis(ax, color):
        """Color your axes."""
        for t in ax.get_yticklabels():
            t.set_color(color)
        return None
    
    color_y_axis(ax1, 'r')
    color_y_axis(ax2, 'b')
    plt.title(example.simulationID)
    plt.show()

#%% Plot network result
# This has been removed since the network snapshots feature was not used 
# anymore and the results is directly saved in the database
if False:
    import seaborn as sns
    sns.set(style="dark")
    colors = {'Waste':'brown',
              'nuclear':'#FF3232',
              'lignite':'brown',
              'hard coal':'k',
              'combined cycle gas turbine':'#FA964B',
              'oil':'#000000',
              'open cycle gas turbine':'#FA964B',
              'backup':'lightsteelblue',
              'Hydro':'mediumblue',
              'Biomass':'#009632',
              'PV':'#FFCD64',
              'Wind Onshore':'#AFC4A5',
              'Wind Offshore':'#AFC4A5',
              'PSPP_discharge':'#0096E1',
              'PSPP_charge':'#323296', 
              }
    
    colors = {**{f'{k}_pos': v for k, v in colors.items()},**{f'{k}_neg': v for k, v in colors.items()}}
    colors.update({'Export':'pink',
                   'Import':'#C5E7A7'})
    p_by_carrier = example.network.generators_t.p.groupby(example.network.generators.carrier, axis=1).sum()
    
    
    cols = ['PSPP_charge','Biolamass','nuclear','lignite', 'hard coal','oil', 'backup', 'combined cycle gas turbine',
             'open cycle gas turbine','PV', 'Wind Onshore', 'Wind Offshore','PSPP_discharge']
    cols = [*[f'{k}_pos' for k in cols],*[f'{k}_neg' for k in cols]]
    cols.extend(['Export','Import'])
    for carrier in list(set(cols)- set(p_by_carrier.columns)):
        cols.remove(carrier)
    
    p_by_carrier = p_by_carrier[cols]
    
    if importStorages:
        p_by_carrier['PSPP_charge_neg'] = -p_by_carrier['PSPP_charge_neg']
        p_by_carrier['PSPP_charge_pos'] = -p_by_carrier['PSPP_charge_pos']
    if CBTransfers:
        p_by_carrier['Import'] = -p_by_carrier['Import']
    fig,ax = plt.subplots(1,1)
    
    fig.set_size_inches(12,6)

    #p_by_carrier=p_by_carrier[p_by_carrier>=0].join(p_by_carrier[p_by_carrier<0], lsuffix="_A", rsuffix="_B")
    p_by_carrier.plot(kind="area",
                      ax=ax,
                      linewidth=0,
                      color=[colors[col] for col in p_by_carrier.columns],
                      alpha=0.7)
    
    ax.set_ylabel("GW")
    ax.legend(loc='center left', bbox_to_anchor=(1.0, 0.5))
    ax.set_xlim(0,snapLength-1)
    plt.tight_layout()
    
    #plot the reactive power
    import cartopy.crs as ccrs
    fig,ax = plt.subplots(1,1,subplot_kw={"projection":ccrs.PlateCarree()})
    
    fig.set_size_inches(6,6)
    
    p = example.network.buses_t.p.sum()/(example.network.buses_t.p.sum().max()*10)
    
    loading = abs(example.network.lines_t.p0/example.network.lines.s_nom).mean()
    
    bus_colors = pd.Series("r",example.network.buses.index)
    bus_colors[p< 0.] = "b"
    
    example.network.plot(bus_sizes=abs(p),
                         ax=ax,
                         bus_colors=bus_colors,
                         line_colors=abs(loading),
                         line_cmap=plt.cm.coolwarm,
                         title="Redispatched Energy (red=-ve, blue=+ve)")