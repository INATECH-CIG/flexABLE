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

class EOM():
    def __init__(self, name, demand=None, CBtrades=None, networkEnabled=False,  world=None, solver_name='gurobi'):
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
        bidsReceived = {"Supply":[],
                        "Demand":[]}
        confirmedBids = []
        rejectedBids = []
        partiallyConfirmedBids = []
        for b in self.bids:
            bidsReceived[b.bidType].append(b)
        bidsReceived["Supply"].append(Bid(issuer = self,
                                          ID = "Bu{}t{}_import".format(self.name,t),
                                          price = -500.,
                                          amount = self.CBtrades['Import'][t],
                                          status = "Sent",
                                          bidType = "Supply"))
        bidsReceived["Demand"].append(Bid(issuer = self,
                                          ID = "Bu{}t{}_export".format(self.name,t),
                                          price = 2999.,
                                          amount = self.CBtrades['Export'][t],
                                          status = "Sent",
                                          bidType = "Demand"))
        
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


        # self.marketResults[t]=result
        self.world.dictPFC[t] = result.marketClearingPrice

    def marketNetworkClearing(self,t):
        #print(sorted(self.bids[t].values(),key=operator.attrgetter('price')))
        # =============================================================================
        # A double ended que might be considered instead of lists if the amount of agents
        # is too high, in-order to speed up the matching process, an alternative would be
        # reverse sorting the lists
        # =============================================================================
        bidsReceived = {"Supply":[],
                        "Demand":[]}
        confirmedBids = []
        rejectedBids = []
        partiallyConfirmedBids = []
        for b in self.bids[t]:
            bidsReceived[b.bidType].append(b)
        # =============================================================================
        # We can consider defining the function outside the marketNetworkClearing part
        # to increase performance (Nested Functions), but the overhead of such definition
        # is not that high
        # =============================================================================
        
        # Attaching bids to powerplants
        p_nom = dict(map(lambda x: [x.ID, x.amount], bidsReceived['Supply']))
        p_nom.update(dict(map(lambda x: [x.ID, x.amount], bidsReceived['Demand'])))
        self.world.network.generators.loc[self.world.network.generators.carrier != 'backup','p_nom'] = 0
        self.world.network.generators.loc[p_nom.keys(),'p_nom'] = pd.Series(p_nom)
        # Attaching marginal costs
        marginal_cost = dict(map(lambda x: [x.ID, x.price], bidsReceived['Supply']))
        marginal_cost.update(dict(map(lambda x: [x.ID, -x.price], bidsReceived['Demand'])))
        self.world.network.generators.loc[:,'marginal_cost'] = 3000
        self.world.network.generators.loc[marginal_cost.keys(),'marginal_cost'] = pd.Series(marginal_cost)

        
        self.world.network.lines.s_nom *= 1000
        confirmedBids = []
        rejectedBids = []
        partiallyConfirmedBids = []
        supplyDict = dict(map(lambda x: [x.ID, (x,x.amount,x.price)], bidsReceived['Supply']))
        demandDict = dict(map(lambda x: [x.ID, (x,x.amount,x.price)], bidsReceived['Demand']))
        
        def confirmBidsNetwork(powerplant):
            try:
                supplyDict[powerplant.name][0].partialConfirm(powerplant[t])
                if powerplant[t] > 0:
                    confirmedBids.append(supplyDict[powerplant.name][0])
                if powerplant[t] <= 0:
                    rejectedBids.append(supplyDict[powerplant.name][0])
            except KeyError:
                pass
            return powerplant[t]
        
        # solution = self.world.network.lopf(t, pyomo = False,
        #                                     solver_name= 'gurobi',
        #                                     solver_dir = 'Solver',
        #                                     solver_options={'OutputFlag':0})
        
        solution= self.world.network.lopf(t,
                                          solver_name= self.solver_name)
        
        self.world.network.lines.s_nom /= 1000
        self.world.network.generators_t.p.iloc[[t],:].T.apply(
            lambda x:confirmBidsNetwork(x), axis=1)

        result = MarketResults("{}".format(self.name),
                   issuer = self.name,
                   confirmedBids = confirmedBids,
                   rejectedBids = rejectedBids,
                   partiallyConfirmedBids = partiallyConfirmedBids,
                   marketClearingPrice = sorted(confirmedBids,key=operator.attrgetter('price'))[-1].price,
                   marginalUnit = 0,
                   status = 0,
                   energyDeficit = 0,
                   energySurplus = 0,
                   timestamp = t)

        self.marketResults[t]=result
        self.world.dictPFC[t] = result.marketClearingPrice
        
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