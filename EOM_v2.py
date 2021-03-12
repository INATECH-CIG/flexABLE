# -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 16:08:03 2020

@author: intgridnb-02
"""
import operator
from bid import Bid
import logging
from MarketResults import MarketResults
import shelve
import matplotlib.pyplot as plt
import pandas as pd
from itertools import groupby
from operator import itemgetter

from MarketClearing import MarketClearing

class EOM():
    def __init__(self, name, demand=None, CBtrades=None, networkEnabled=False,  world=None, solver_name='gurobi_direct'):
        self.name = name
        self.world=world
        self.snapshots = self.world.snapshots
        self.networkEnabled = networkEnabled
        
        if demand == None:
            self.demand = {t:0 for t in self.snapshots}
        elif len(demand) != len(self.snapshots):
            print("Length of given demand does not match snapshots length!")
        else:
            self.demand = demand

        if CBtrades is None:
            self.CBtrades = {"Import":{t:0 for t in self.snapshots},
                             "Export":{t:0 for t in self.snapshots}}
        elif len(CBtrades["Import"]) != len(self.snapshots) or len(CBtrades["Export"]) != len(self.snapshots):
            print("Length of given CBtrades does not match snapshots length!")
        else:
            self.CBtrades = CBtrades

        self.bids = []
        # self.marketResults = {}
        
        self.performance = 0
        self.solver_name = solver_name
        
        self.clearing = MarketClearing(solver_name)
        
    def step(self,t,agents):
        self.collectBids(agents, t)
        if self.networkEnabled:
            self.marketNetworkClearing(t)
        else:
            self.marketClearing(t)
        
    def collectBids(self, agents, t):
        self.bids = []
        for agent in agents.values():
            self.bids.extend(agent.requestBid(t))

    def marketClearing(self,t):
        #print(sorted(self.bids[t].values(),key=operator.attrgetter('price')))
        # =============================================================================
        # A double ended que might be considered instead of lists if the amount of agents
        # is too high, in-order to speed up the matching process, an alternative would be
        # reverse sorting the lists
        # =============================================================================
        data = {None: {'indexSupplyMR': {None: []},
                       'indexSupplyFlex': {None: []},
                       'indexDemand': {None: []},
                       'mrPrice': {},
                       'flexPrice': {},
                       'mrPower': {},
                       'flexPower': {},
                       'mrTotal': {},
                       'flexTotal': {},
                       'demandPrice': {},
                       'demandPower': {},
                       'demandTotal': {},
                       'IED': {None: None}
                      }
                }
        
        for b in self.bids:
            if b.amount != 0:
                if "mrEOM" in b.ID:
                    data[None]["indexSupplyMR"][None].append(b.ID)
                    data[None]['mrPrice'][b.ID] = float(b.price)
                    data[None]['mrPower'][b.ID] = float(b.amount)
                    data[None]['mrTotal'][b.ID] = b.amount * b.price
                    
                elif ("flexEOM" in b.ID) or ("supplyEOM" in b.ID):
                    data[None]["indexSupplyFlex"][None].append(b.ID)
                    data[None]['flexPrice'][b.ID] = float(b.price)
                    data[None]['flexPower'][b.ID] = float(b.amount)
                    data[None]['flexTotal'][b.ID] = b.amount * b.price
                    
                elif "demandEOM" in b.ID:
                    data[None]["indexDemand"][None].append(b.ID)
                    data[None]['demandPrice'][b.ID] = float(b.price)
                    data[None]['demandPower'][b.ID] = float(b.amount)
                    data[None]['demandTotal'][b.ID] = b.amount * b.price
                
        # import
        if self.CBtrades['Import'][t] != 0:
            ID = "Bu{}t{}_import".format(self.name,t)
            data[None]["indexSupplyFlex"][None].append(ID)
            data[None]['flexPrice'][ID] = -500.
            data[None]['flexPower'][ID] = float(self.CBtrades['Import'][t])
            data[None]['flexTotal'][ID] = self.CBtrades['Import'][t] * -500.
        
        #export
        if self.CBtrades['Export'][t] != 0:
            ID = "Bu{}t{}_export".format(self.name,t)
            data[None]["indexDemand"][None].append(ID)
            data[None]['demandPrice'][ID] = 2999.
            data[None]['demandPower'][ID] = float(self.CBtrades['Export'][t])
            data[None]['demandTotal'][ID] = self.CBtrades['Export'][t] * 2999.

        # inelastic demand
        data[None]["IED"][None] = float(self.demand[t])
        
        instance = self.clearing.clear(data)
        
        confirmedBidsSupply = []
        
        for b in self.bids:
            if b.amount != 0:
                if "mrEOM" in b.ID:
                    conf = instance.mrOrder[b.ID].value
                    b.partialConfirm(confirmedAmount = b.amount * conf)
                    if conf > 0:
                        confirmedBidsSupply.append(b)
                    
                elif ("flexEOM" in b.ID) or ("supplyEOM" in b.ID):
                    conf = instance.flexOrder[b.ID].value
                    b.partialConfirm(confirmedAmount = b.amount * conf)
                    if conf > 0:
                        confirmedBidsSupply.append(b)
                    
                elif "demandEOM" in b.ID:
                    b.partialConfirm(confirmedAmount = b.amount * instance.demandOrder[b.ID].value)
            else:
                b.partialConfirm(confirmedAmount = 0)

        result = MarketResults("{}".format(self.name),
                   issuer = self.name,
                   confirmedBids = self.bids,
                   rejectedBids = [],
                   partiallyConfirmedBids = [],
                   marketClearingPrice = sorted(confirmedBidsSupply,key=operator.attrgetter('price'))[-1].price,
                   marginalUnit = sorted(confirmedBidsSupply,key=operator.attrgetter('price'))[-1].ID,
                   status = None,
                   energyDeficit = 0,
                   energySurplus = 0,
                   timestamp = t)

        # self.world.ResultsWriter.writeMarketResult(result)
        # self.marketResults[t]=result
        self.world.dictPFC[t] = result.marketClearingPrice

    def marketNetworkClearing(self,t):
        # =============================================================================
        # This is basically the same function as normal market clearing, but also includes
        # a network that would allow redispatch
        # =============================================================================
        bidsReceived = {"Supply":[],
                        "Demand":[]}
        confirmedBids = []
        rejectedBids = []
        partiallyConfirmedBids = []
        for b in self.bids:
            bidsReceived[b.bidType].append(b)
    
        bidsReceived["Supply"].sort(key=operator.attrgetter('price'),
                                    reverse=True)
        
        bidsReceived["Demand"].append(Bid(issuer = self,
                                          ID = "IEDt{}".format(t),
                                          price = 3000.,
                                          amount = self.demand[t],
                                          status = "Sent",
                                          bidType = "InelasticDemand"))
        
        bidsReceived["Demand"].sort(key=operator.attrgetter('price'))
        
        sum_totalSupply = sum(bidsReceived["Supply"])
        sum_totalDemand = sum(bidsReceived["Demand"])
        # =====================================================================
        # The different cases of uniform price market clearing
        # Case 1: The sum of either supply or demand is 0
        # Case 2: Inelastic demand is higher than sum of all supply bids
        # Case 3: Covers all other cases       
        # =====================================================================
        if sum_totalSupply == 0 or sum_totalDemand == 0:
            logging.debug('The sum of either demand offers ({}) or supply '
                          'offers ({}) is 0 at t:{}'.format(sum_totalDemand,
                                                            sum_totalSupply,
                                                            t))
            result = MarketResults("{}".format(self.name),
                                   issuer=self.name,
                                   confirmedBids=[],
                                   rejectedBids=bidsReceived["Demand"] + bidsReceived["Supply"],
                                   marketClearingPrice=3000.2,
                                   marginalUnit="None",
                                   status="Case1",
                                   timestamp=t)
            
        elif self.demand[t] > sum_totalSupply:
            """
            Since the Inelastic demand is higher than the sum of all supply offers
            all the supply offers are confirmed
            
            the marginal unit is assumed to be the last supply bid confirmed
            """
            for b in bidsReceived["Supply"]:
                confirmedBids.append(b)
                b.confirm()
            bidsReceived["Demand"][-1].partialConfirm(sum_totalSupply)
            partiallyConfirmedBids.append(bidsReceived["Demand"].pop())
            rejectedBids = list(set(bidsReceived["Supply"]+bidsReceived["Demand"])-set(confirmedBids))
            
            result = MarketResults("{}".format(self.name),
                                   issuer=self.name,
                                   confirmedBids=confirmedBids,
                                   rejectedBids=rejectedBids,
                                   partiallyConfirmedBids=partiallyConfirmedBids,
                                   marketClearingPrice=sorted(confirmedBids,key=operator.attrgetter('price'))[-1].price,
                                   marginalUnit="None",
                                   status="Case2",
                                   energyDeficit=self.demand[t] - sum_totalSupply,
                                   energySurplus=0,
                                   timestamp=t)

        else:
            confirmedBidsDemand = []
            confirmedBidsDemand.append(bidsReceived["Demand"].pop())
            confQty_demand = confirmedBidsDemand[-1].amount
            confirmedBidsDemand[-1].confirm()
            
            #confirmedBidsDemand = [bidsReceived["Demand"][-1]]
            # The inelastic demand is directly confirmed since the sum of supply energy it is enough to supply it
            #bidsReceived["Demand"][-1].confirm()
            #confQty_demand = bidsReceived["Demand"][-1].amount
            
            confirmedBidsSupply = []
            confQty_supply = 0
            currBidPrice_demand = 3000.00
            currBidPrice_supply = -3000.00
    
            while True:
                # =============================================================================
                # Cases to accept bids
                # Case 3.1: Demand is larger than confirmed supply, and the current demand price is
                #         higher than the current supply price, which signals willingness to buy
                # Case 3.2: Confirmed demand is less or equal to confirmed supply but the current 
                #         demand price is higher than current supply price, which means there is till 
                #         willingness to buy and energy supply is still available, so an extra demand
                #         offer is accepted
                # Case 3.3: The intersection of the demand-supply curve has been exceeded (Confirmed Supply 
                #         price is higher than demand)
                # Case 3.4: The intersection of the demand-supply curve found, and the price of bother offers
                #         is equal
                # =============================================================================
                # Case 1
                # =============================================================================
                if confQty_demand > confQty_supply and currBidPrice_demand > currBidPrice_supply:
                    try:
                        # Tries accepting last supply offer since they are reverse sorted
                        # excepts that there are no extra supply offers, then the last demand offer
                        # is changed into a partially confirmed offer
                        confirmedBidsSupply.append(bidsReceived["Supply"].pop())
                        confQty_supply += confirmedBidsSupply[-1].amount
                        currBidPrice_supply = confirmedBidsSupply[-1].price
                        confirmedBidsSupply[-1].confirm()
    
                    except IndexError:
                        confirmedBidsDemand[-1].partialConfirm(confirmedBidsDemand[-1].amount-(confQty_demand - confQty_supply))
                        case = 'Case3.1'
                        break
                # =============================================================================
                # Case 2
                # =============================================================================
                elif confQty_demand <= confQty_supply and currBidPrice_demand > currBidPrice_supply:
                    try:
                        confirmedBidsDemand.append(bidsReceived["Demand"].pop())
                        confQty_demand += confirmedBidsDemand[-1].amount
                        currBidPrice_demand = confirmedBidsDemand[-1].price
                        confirmedBidsDemand[-1].confirm()
                        
                    except IndexError:
                        confirmedBidsSupply[-1].partialConfirm(confirmedBidsSupply[-1].amount-(confQty_supply - confQty_demand))
                        case = 'Case3.2'
                        break
    
                # =============================================================================
                # Case 3    
                # =============================================================================
                elif currBidPrice_demand < currBidPrice_supply:
                    # Checks whether the confirmed demand is greater than confirmed supply
                    if (confQty_supply - confirmedBidsSupply[-1].amount) < (
                            confQty_demand - confirmedBidsDemand[-1].amount):
    
                        confQty_demand -= confirmedBidsDemand[-1].amount
                        confirmedBidsSupply[-1].partialConfirm(confirmedBidsSupply[-1].amount - (confQty_supply - confQty_demand))
                        bidsReceived["Demand"].append(confirmedBidsDemand.pop())
                        bidsReceived["Demand"][-1].reject()
                        case = 'Case3.3'
                        break
    
                    # Checks whether the confirmed supply is greater than confirmed demand
                    elif (confQty_supply - abs(confirmedBidsSupply[-1].amount)) > (
                            confQty_demand - confirmedBidsDemand[-1].amount):

                        confQty_supply -= confirmedBidsSupply[-1].amount
                        confirmedBidsDemand[-1].partialConfirm(confirmedBidsDemand[-1].amount - (confQty_demand - confQty_supply))
                        bidsReceived["Supply"].append(confirmedBidsSupply.pop())
                        bidsReceived["Supply"][-1].reject()
                        case = 'Case3.3'
                        break
    
                    # The confirmed supply matches confirmed demand
                    else:
                        case = 'Case3.3'
                        break
    
                # =============================================================================
                # Case 4
                # =============================================================================
                elif currBidPrice_demand == currBidPrice_supply:
    
                    # Kontrahiertes Angebot ist größer als kontrahierte Nachfrage
                    if confQty_supply > confQty_demand:
                        confirmedBidsSupply[-1].partialConfirm(confirmedBidsSupply[-1].amount - (confQty_supply - confQty_demand))
                        case = 'Case3.4'
                        break
    
                    # Kontrahierte Nachfrage ist größer als kontrahiertes Angebot
                    elif confQty_demand > confQty_supply:
                        confirmedBidsDemand[-1].partialConfirm(confirmedBidsDemand[-1].amount - (confQty_demand - confQty_supply))
                        confirmedBidsDemand[-1][1] -= (confQty_demand - confQty_supply)
                        case = 'Case3.4'
                        break
    
                    # Kontrahiertes Angebot und kontrahierte Nachfrage sind gleich groß
                    else:
                        case = 'Case3.4'
                        break
    
                # Preis und Menge der kontrahierten Angebote und Nachfrage bereits identisch
                else:
                    case = 'Case3.4'
                    break
            
            
            # Zusammenführung der Listen
            confirmedBids = confirmedBidsDemand + confirmedBidsSupply
            rejectedBids = list(set(bidsReceived["Supply"]+bidsReceived["Demand"])-set(confirmedBids))

            # setting the market clearing price
            mcp = sorted(confirmedBidsSupply,key=operator.attrgetter('price'))[-1].price
            self.world.dictPFC[t] = sorted(confirmedBidsSupply,key=operator.attrgetter('price'))[-1].price
            
            # Summing powerfeed of each node
            perNodeGeneration = sorted([('{}_mcFeedIn'.format(x.node), x.confirmedAmount if x.bidType=='Supply' else -x.confirmedAmount) for x in confirmedBids])
            perNodeGeneration = dict([(k, sum([x for _, x in g])) for k, g in groupby(perNodeGeneration, itemgetter(0))])
            del perNodeGeneration['DefaultNode_mcFeedIn']
            # Attaching load to nodes
            perNodeLoad = {f'{k}_load': v for k, v in self.world.demandDistrib.loc[t].to_dict().items()}
            nodalLoads = {**perNodeGeneration,**perNodeLoad}
            # The original load should be set to Zero before re-assigning values to avoid having values from earlier steps
            self.world.network.loads.p_set = 0
            self.world.network.loads.loc[nodalLoads.keys(),'p_set'] = pd.Series(nodalLoads)
            
            neg_redispatch = dict(map(lambda x: ['{}_negRedis'.format(x.ID), x.confirmedAmount if x.bidType=='Supply' else x.confirmedAmount], confirmedBids))
            self.world.network.generators.loc[self.world.network.generators.index.str.contains('_negRedis'),'p_nom'] = pd.Series(neg_redispatch)
            marginal_cost = dict(map(lambda x: ['{}_negRedis'.format(x.ID), -(abs(mcp-x.redispatch_price))], confirmedBids))
            marginal_cost = dict(map(lambda x: ['{}_negRedis'.format(x.ID), -mcp], confirmedBids))
            self.world.network.generators.loc[self.world.network.generators.index.str.contains('_negRedis'),'marginal_cost'] = pd.Series(marginal_cost)
            
            pos_redispatch_bids = rejectedBids + confirmedBids
            pos_redispatch = dict(map(lambda x: ['{}_posRedis'.format(x.ID), (x.amount-x.confirmedAmount) if x.bidType=='Supply' else -(x.confirmedAmount-x.amount)], pos_redispatch_bids))
            self.world.network.generators.loc[self.world.network.generators.index.str.contains('_posRedis'),'p_nom'] = pd.Series(pos_redispatch)
            marginal_cost = dict(map(lambda x: ['{}_posRedis'.format(x.ID), x.redispatch_price], pos_redispatch_bids))
            marginal_cost = dict(map(lambda x: ['{}_posRedis'.format(x.ID), mcp], pos_redispatch_bids))
            self.world.network.generators.loc[self.world.network.generators.index.str.contains('_posRedis'),'marginal_cost'] = pd.Series(marginal_cost)
            
            
            self.world.network.generators.p_nom.fillna(0, inplace=True)
            # This should be inspected a little bit closer
            #self.world.network.generators.marginal_cost[self.world.network.generators.index.str.contains('_negRedis')].fillna(-3000, inplace=True)
            #self.world.network.generators.marginal_cost[self.world.network.generators.index.str.contains('_posRedis')].fillna(3000, inplace=True)
            self.world.network.generators.marginal_cost.fillna(-3000, inplace=True)
            bidsDict = dict(map(lambda x: [x.ID, x], rejectedBids + confirmedBids))
            def confirmBidsNetwork(powerplant):
                try:
                    bidsDict[powerplant.name[:-9]].redispatch(powerplant['now'])
                except KeyError:
                    pass

            solution= self.world.network.lopf(solver_name= self.solver_name)
            
            self.world.network.generators_t.p.T.apply(
                lambda x:confirmBidsNetwork(x), axis=1)

            
            result = MarketResults("{}".format(self.name),
                       issuer = self.name,
                       confirmedBids = confirmedBids,
                       rejectedBids = rejectedBids,
                       partiallyConfirmedBids = partiallyConfirmedBids,
                       marketClearingPrice = sorted(confirmedBidsSupply,key=operator.attrgetter('price'))[-1].price,
                       marginalUnit = sorted(confirmedBidsSupply,key=operator.attrgetter('price'))[-1].ID,
                       status = case,
                       energyDeficit = 0,
                       energySurplus = 0,
                       timestamp = t)
            self.world.ResultsWriter.writeMarketResult(result)
            #self.world.ResultsWriter.writeGeneratorsPower(self.world.network.generators_t.p,t)
            self.world.ResultsWriter.writeRedispatchPower(self.world.network.generators_t.p,t)
            #self.world.ResultsWriter.writeNodalPower(self.world.network, t)

    def plotResults(self):
        def two_scales(ax1, time, data1, data2, c1, c2):

            ax2 = ax1.twinx()
        
            ax1.step(time, data1, color=c1)
            ax1.set_xlabel('snapshot')
            ax1.set_ylabel('Demand [MW/Snapshot]')
        
            ax2.step(time, data2, color=c2)
            ax2.set_ylabel('Market Clearing Price [€/MW]')
            return ax1, ax2
        
        
        # Create some mock data
        t = range(len(self.marketResults))
        s1 = list(self.demand.values())
        s2 = [_.marketClearingPrice for _ in self.marketResults.values()]
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
        plt.title(self.world.simulationID)
        plt.show()
            
        # plt.xticks(range(len(self.marketResults)), list(self.marketResults.keys()))
        # plt.show()
    def exportResults(self,t):
        '''
        Export results as a database / shelve. This was originally within the scope of the market clearing function
        but was spilt to save the overhead of opening file at each tick.

        Parameters
        ----------
        t : TYPE
            DESCRIPTION.

        Returns
        -------
        None.

        '''
        database = shelve.open("output/MarketResults/"+self.name+'.db') 
        database['MC_{}'.format(t)] = result
        database.close()
        
    def feedback(self,award):
        self.performance +=award