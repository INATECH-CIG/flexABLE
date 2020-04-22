# -*- coding: utf-8 -*-
"""
Created on Mon Apr  6 16:45:41 2020

@author: intgridnb-02
"""
import operator
from bid import Bid
import logging
from MarketResults import MarketResults
import shelve
import matplotlib.pyplot as plt

class EOM():
    def __init__(self, name, demand=None, CBtrades=None,  world=None):
        self.name = name
        self.world=world
        self.snapshots = self.world.snapshots
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

        self.bids = {t:[] for t in self.snapshots}
        self.marketResults = {}
        
        self.performance = 0
    def step(self,t,agents):
        self.collectBids(agents, t)
        self.marketClearing(t)
    def collectBids(self, agents, t):
        for agent in agents.values():
            self.bids[t].extend(agent.requestBid(t))

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
        for b in self.bids[t]:
            bidsReceived[b.bidType].append(b)
        bidsReceived["Supply"].append(Bid(self,
                                          "Bu{}t{}_import".format(self.name,t),
                                          -500,
                                          self.CBtrades['Import'][t],
                                          "Sent",
                                          "Supply"))
        bidsReceived["Demand"].append(Bid(self,
                                          "Bu{}t{}_export".format(self.name,t),
                                          3000,
                                          self.CBtrades['Export'][t],
                                          "Sent",
                                          "Demand"))
        bidsReceived["Supply"].sort(key=operator.attrgetter('price'),
                                    reverse=True)
        
        bidsReceived["Demand"].append(Bid(self, "IEDt{}".format(t),
                                      -3000,
                                      -self.demand[t],
                                      "Sent",
                                      "InelasticDemand"))
        
        bidsReceived["Demand"].sort(key=operator.attrgetter('price'),
                                    reverse=True)
        
        sum_totalSupply = sum(bidsReceived["Supply"])
        sum_totalDemand = sum(bidsReceived["Demand"])
        # =====================================================================
        # The different cases of uniform price market clearing
        # Case 1: The sum of either supply or demand is 0
        # Case 2: Inelastic demand is higher than sum of all supply bids
        # Case 3: Covers all other cases       
        # =====================================================================
        if sum_totalSupply == 0 or sum_totalDemand == 0:
            mcp = 3000.2
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
            confirmedBidsDemand = [bidsReceived["Demand"][-1]]
            # The inelastic demand is directly confirmed since the sum of supply energy it is enough to supply it
            bidsReceived["Demand"][-1].confirm()
            confirmedBidsSupply = []
            # Hilfsvariablen
            idx_demand = 0
            idx_supply = 0
            confQty_demand = bidsReceived["Demand"][-1].amount
            confQty_supply = 0
            currBidPrice_demand = 3000.00
            currBidPrice_supply = -3000.00
    
            while True:
                # =============================================================================
                # Cases to accept bids
                # Case 1: Demand is larger than confirmed supply, and the current demand price is
                #         higher than the current supply price, which signals willingness to buy
                # Case 2: Confirmed demand is less or equal to confirmed supply but the current 
                #         demand price is higher than current supply price, which means there is till 
                #         willingness to buy and energy supply is still available, so an extra demand
                #         offer is accepted
                # Case 3: The intersection of the demand-supply curve has been exceeded (Confirmed Supply 
                #         price is higher than demand)
                # Case 4: The intersection of the demand-supply curve found, and the price of bother offers
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
                        confirmedBidsSupply[-1].partialConfirm(confirmedBidsSupply[-1].amount-(confQty_demand - confQty_supply))
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
                        break
    
                    # Checks whether the confirmed supply is greater than confirmed demand
                    elif (confQty_supply - abs(confirmedBidsSupply[-1].amount)) > (
                            confQty_demand - confirmedBidsDemand[-1].amount):

                        confQty_supply -= confirmedBidsSupply[-1].amount
                        confirmedBidsDemand[-1].partialConfirm(confirmedBidsDemand[-1].amount - (confQty_demand - confQty_supply))
                        bidsReceived["Supply"].append(confirmedBidsSupply.pop())
                        bidsReceived["Supply"][-1].reject()
                        break
    
                    # The confirmed supply matches confirmed demand
                    else:
                        break
    
                # =============================================================================
                # Case 4
                # =============================================================================
                elif currBidPrice_demand == currBidPrice_supply:
    
                    # Kontrahiertes Angebot ist größer als kontrahierte Nachfrage
                    if confQty_supply > confQty_demand:
                        confirmedBidsSupply[-1].partialConfirm(confirmedBidsSupply[-1].amount - (confQty_supply - confQty_demand))
                        break
    
                    # Kontrahierte Nachfrage ist größer als kontrahiertes Angebot
                    elif confQty_demand > confQty_supply:
                        confirmedBidsDemand[-1].partialConfirm(confirmedBidsDemand[-1].amount - (confQty_demand - confQty_supply))
                        confirmedBidsDemand[-1][1] -= (confQty_demand - confQty_supply)
                        break
    
                    # Kontrahiertes Angebot und kontrahierte Nachfrage sind gleich groß
                    else:
                        break
    
                # Preis und Menge der kontrahierten Angebote und Nachfrage bereits identisch
                else:
                    break
            
            
            # Zusammenführung der Listen
            confirmedBids = confirmedBidsDemand + confirmedBidsSupply
            rejectedBids = list(set(bidsReceived["Supply"]+bidsReceived["Demand"])-set(confirmedBids))

            result = MarketResults("{}".format(self.name),
                       issuer=self.name,
                       confirmedBids=confirmedBids,
                       rejectedBids=rejectedBids,
                       partiallyConfirmedBids=partiallyConfirmedBids,
                       marketClearingPrice=sorted(confirmedBids,key=operator.attrgetter('price'))[-1].price,
                       marginalUnit=sorted(confirmedBids,key=operator.attrgetter('price'))[-1].ID,
                       status="Case3",
                       energyDeficit=0,
                       energySurplus=0,
                       timestamp=t)


        self.marketResults[t]=result

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