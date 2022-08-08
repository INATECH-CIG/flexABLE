# -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 16:08:03 2020

@author: intgridnb-02
"""
import operator
from bid import Bid
import logging
from MarketResults import MarketResults


class EOM():
    def __init__(self, name, demand = None, CBtrades = None, world = None):
        self.name = name
        self.world = world
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

        self.bids = []
        
        
    def step(self,t,agents):
        self.collectBids(agents, t)
        self.marketClearing(t)
    
    
    def collectBids(self, agents, t):
        self.bids = []
        for agent in agents.values():
            self.bids.extend(agent.requestBid(t))


    def marketClearing(self,t):
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
        
        bidsReceived["Supply"].sort(key = operator.attrgetter('price'), reverse = True)
        
        bidsReceived["Demand"].append(Bid(issuer = self,
                                          ID = "IEDt{}".format(t),
                                          price = 3000.,
                                          amount = self.demand[t],
                                          status = "Sent",
                                          bidType = "InelasticDemand"))
        
        bidsReceived["Demand"].sort(key = operator.attrgetter('price'))
        
        sum_totalSupply = sum(bidsReceived["Supply"])
        sum_totalDemand = sum(bidsReceived["Demand"])
        
        # =====================================================================
        # The different cases of uniform price market clearing
        # Case 1: The sum of either supply or demand is 0
        # Case 2: Inelastic demand is higher than sum of all supply bids
        # Case 3: Covers all other cases       
        # =====================================================================
        
        #Case 1
        if sum_totalSupply == 0 or sum_totalDemand == 0:
            logging.debug('The sum of either demand offers ({}) or supply '
                          'offers ({}) is 0 at t:{}'.format(sum_totalDemand, sum_totalSupply, t))
            
            result = MarketResults("{}".format(self.name),
                                   issuer = self.name,
                                   confirmedBids = [],
                                   rejectedBids = bidsReceived["Demand"] + bidsReceived["Supply"],
                                   marketClearingPrice = 3000.2,
                                   marginalUnit = "None",
                                   status = "Case1",
                                   timestamp = t)
        
        #Case 2
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
            rejectedBids = list(set(bidsReceived["Supply"] + bidsReceived["Demand"]) - set(confirmedBids))
            marketClearingPrice = sorted(confirmedBids,key=operator.attrgetter('price'))[-1].price
            
            result = MarketResults("{}".format(self.name),
                                   issuer = self.name,
                                   confirmedBids = confirmedBids,
                                   rejectedBids = rejectedBids,
                                   partiallyConfirmedBids = partiallyConfirmedBids,
                                   marketClearingPrice = marketClearingPrice,
                                   marginalUnit = "None",
                                   status = "Case2",
                                   energyDeficit = self.demand[t] - sum_totalSupply,
                                   energySurplus = 0,
                                   timestamp = t)
        
        #Case 3
        else:
            confirmedBidsDemand = []
            confirmedBidsDemand.append(bidsReceived["Demand"].pop())
            confQty_demand = confirmedBidsDemand[-1].amount
            confirmedBidsDemand[-1].confirm()
                        
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
                # Case 3.1
                # =============================================================================
                if confQty_demand > confQty_supply and currBidPrice_demand > currBidPrice_supply:
                    try:
                        '''
                        Tries accepting last supply offer since they are reverse sorted
                        excepts that there are no extra supply offers, then the last demand offer
                        is changed into a partially confirmed offer
                        '''
                        
                        confirmedBidsSupply.append(bidsReceived["Supply"].pop())
                        confQty_supply += confirmedBidsSupply[-1].amount
                        currBidPrice_supply = confirmedBidsSupply[-1].price
                        confirmedBidsSupply[-1].confirm()
    
                    except IndexError:
                        confirmedBidsDemand[-1].partialConfirm(confirmedBidsDemand[-1].amount-(confQty_demand - confQty_supply))
                        case = 'Case3.1'
                        break
                    
                # =============================================================================
                # Case 3.2
                # =============================================================================
                elif confQty_demand <= confQty_supply and currBidPrice_demand > currBidPrice_supply:
                    try:
                        '''
                        Tries accepting last demand offer since they are reverse sorted
                        excepts that there are no extra demand offers, then the last supply offer
                        is changed into a partially confirmed offer
                        '''
                        
                        confirmedBidsDemand.append(bidsReceived["Demand"].pop())
                        confQty_demand += confirmedBidsDemand[-1].amount
                        currBidPrice_demand = confirmedBidsDemand[-1].price
                        confirmedBidsDemand[-1].confirm()
                        self.world.IEDPrice[t] = currBidPrice_supply
                        
                    except IndexError:
                        confirmedBidsSupply[-1].partialConfirm(confirmedBidsSupply[-1].amount-(confQty_supply - confQty_demand))
                        case = 'Case3.2'
                        break
    
                # =============================================================================
                # Case 3.3    
                # =============================================================================
                elif currBidPrice_demand < currBidPrice_supply:
                    
                    # Checks whether the confirmed demand is greater than confirmed supply
                    if (confQty_supply - confirmedBidsSupply[-1].amount) < (confQty_demand - confirmedBidsDemand[-1].amount):
                        confQty_demand -= confirmedBidsDemand[-1].amount
                        confirmedBidsSupply[-1].partialConfirm(confirmedBidsSupply[-1].amount - (confQty_supply - confQty_demand))
                        bidsReceived["Demand"].append(confirmedBidsDemand.pop())
                        bidsReceived["Demand"][-1].reject()
                        case = 'Case3.3'
                        break
    
                    # Checks whether the confirmed supply is greater than confirmed demand
                    elif (confQty_supply - abs(confirmedBidsSupply[-1].amount)) > (confQty_demand - confirmedBidsDemand[-1].amount):
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
                # Case 3.4
                # =============================================================================
                elif currBidPrice_demand == currBidPrice_supply:
    
                    # Confirmed supply is greater than confirmed demand
                    if confQty_supply > confQty_demand:
                        confirmedBidsSupply[-1].partialConfirm(confirmedBidsSupply[-1].amount - (confQty_supply - confQty_demand))
                        case = 'Case3.4'
                        break
    
                    # Confirmed demand is greater than confirmed supply
                    elif confQty_demand > confQty_supply:
                        confirmedBidsDemand[-1].partialConfirm(confirmedBidsDemand[-1].amount - (confQty_demand - confQty_supply))
                        confirmedBidsDemand[-1][1] -= (confQty_demand - confQty_supply)
                        case = 'Case3.4'
                        break
    
                    # Confirmed supply and confirmed demand are equal
                    else:
                        case = 'Case3.4'
                        break
    
                # Confirmed supply and confirmed demand are equal
                else:
                    case = 'Case3.4'
                    break
            
            
            confirmedBids = confirmedBidsDemand + confirmedBidsSupply
            rejectedBids = list(set(bidsReceived["Supply"] + bidsReceived["Demand"]) - set(confirmedBids))
            marketClearingPrice = sorted(confirmedBidsSupply, key = operator.attrgetter('price'))[-1].price
            marginalUnit = sorted(confirmedBidsSupply,key=operator.attrgetter('price'))[-1].ID

            result = MarketResults("{}".format(self.name),
                       issuer = self.name,
                       confirmedBids = confirmedBids,
                       rejectedBids = rejectedBids,
                       partiallyConfirmedBids = partiallyConfirmedBids,
                       marketClearingPrice = marketClearingPrice,
                       marginalUnit = marginalUnit,
                       status = case,
                       energyDeficit = 0,
                       energySurplus = 0,
                       timestamp = t)

        self.world.dictPFC[t] = result.marketClearingPrice


    def feedback(self,award):
        pass
        
        
        