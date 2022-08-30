# -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 16:38:21 2020

@author: intgridnb-02
"""

from misc import initializer
from bid import Bid
import operator
import logging
from MarketResults import MarketResults


class DHM():
    """
    This class represents the district heating market DHM.
    This class collects the bids from eligible market participants and performs market clearing for each region separately.
    The demand is formulated per region in Germany (Bundesland) and only power plants positioned
    in that region can provide DH. No physical connection of power plants to the points of demand are considered.
    The demand does not have to be fulfilled at each given time point.   
    """
    
    @initializer
    def __init__(self, name, HLP_DH = None, annualDemand = None,  world = None):
        self.name = name
        
        if self.world.enable_DHM:
            for region, demand in self.annualDemand.iterrows():
                self.HLP_DH[region] = self.HLP_DH[region] * demand['Demand']
            
            # Initiates a dictionary to sort out which powerplants are allowed to participate in which region
            self.heatingDistricts = {region:[] for region in set([i.heatingDistrict for i in self.world.powerplants])}
            
            self.bids = {region:[] for region in set([i.heatingDistrict for i in self.world.powerplants])}
            
            for powerplant in self.world.powerplants:
                if powerplant.heatExtraction:
                    if powerplant.maxExtraction > 0:
                        self.heatingDistricts[powerplant.heatingDistrict].append(powerplant)
                        
            for key,value in list(self.heatingDistricts.items()):
                if value == []:
                    del self.heatingDistricts[key]
                    
        
    def collectBids(self, agents, t):
        for agent in agents.values():
            self.bids.extend(agent.request_bids(t))
            
            
    def step(self, t):
        '''
        This function both requests bids from agents, and clears the market
        '''
        self.bids = {region:[] for region in self.bids.keys()}
        
        for region in self.heatingDistricts.keys():
            for powerplant in self.heatingDistricts[region]:
                self.bids[region].extend(powerplant.formulate_bids(t, market = 'DHM'))
                
            self.marketClearing(t, region)
            

    def marketClearing(self, t, region):
        bidsReceived = {"Supply":[],
                        "Demand":[]}
        
        confirmedBids = []
        rejectedBids = []
        partiallyConfirmedBids = []
        
        for b in self.bids[region]:
            bidsReceived[b.bidType].append(b)

        bidsReceived["Supply"].sort(key = operator.attrgetter('price'),
                                    reverse = True)
        
        bidsReceived["Demand"].append(Bid(issuer = self, 
                                          ID = "IEDt{}".format(t),
                                          price = -3000,
                                          amount = self.HLP_DH[region].at[t],
                                          status = "Sent",
                                          bidType = "InelasticDemand"))
        
        bidsReceived["Demand"].sort(key = operator.attrgetter('price'),
                                    reverse = True)
        
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
        elif self.HLP_DH[region].at[t] > sum_totalSupply:
            """
            Since the Inelastic demand is higher than the sum of all supply offers
            all the supply offers are confirmed
            
            The marginal unit is assumed to be the last supply bid confirmed
            """
            
            for b in bidsReceived["Supply"]:
                confirmedBids.append(b)
                b.confirm()
                
            bidsReceived["Demand"][-1].partialConfirm(sum_totalSupply)
            
            partiallyConfirmedBids.append(bidsReceived["Demand"].pop())
            rejectedBids = list(set(bidsReceived["Supply"] + bidsReceived["Demand"]) - set(confirmedBids))
            marketClearingPrice=sorted(confirmedBids, key = operator.attrgetter('price'))[-1].price
            
            result = MarketResults("{}".format(self.name),
                                   issuer = self.name,
                                   confirmedBids = confirmedBids,
                                   rejectedBids = rejectedBids,
                                   partiallyConfirmedBids = partiallyConfirmedBids,
                                   marketClearingPrice = marketClearingPrice,
                                   marginalUnit = "None",
                                   status = "Case2",
                                   energyDeficit = self.HLP_DH[region].at[t] - sum_totalSupply,
                                   energySurplus = 0,
                                   timestamp = t)
            
        #Case 3
        else:
            confirmedBidsDemand = [bidsReceived["Demand"][-1]]
            # The inelastic demand is directly confirmed since the sum of supply energy it is enough to supply it
            bidsReceived["Demand"][-1].confirm()
            
            confirmedBidsSupply = []
            confQty_demand = bidsReceived["Demand"][-1].amount
            
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
                        
                    except IndexError:
                        confirmedBidsSupply[-1].partialConfirm(confirmedBidsSupply[-1].amount-(confQty_demand - confQty_supply))
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
                        break
    
                    # Checks whether the confirmed supply is greater than confirmed demand
                    elif (confQty_supply - abs(confirmedBidsSupply[-1].amount)) > (confQty_demand - confirmedBidsDemand[-1].amount):
                        confQty_supply -= confirmedBidsSupply[-1].amount
                        confirmedBidsDemand[-1].partialConfirm(confirmedBidsDemand[-1].amount - (confQty_demand - confQty_supply))
                        bidsReceived["Supply"].append(confirmedBidsSupply.pop())
                        bidsReceived["Supply"][-1].reject()
                        break
    
                    # The confirmed supply matches confirmed demand
                    else:
                        break
    
                # =============================================================================
                # Case 3.4
                # =============================================================================
                elif currBidPrice_demand == currBidPrice_supply:
                    
                    # Confirmed supply is greater than confirmed demand
                    if confQty_supply > confQty_demand:
                        confirmedBidsSupply[-1].partialConfirm(confirmedBidsSupply[-1].amount - (confQty_supply - confQty_demand))
                        break
    
                    # Confirmed demand is greater than confirmed supply
                    elif confQty_demand > confQty_supply:
                        confirmedBidsDemand[-1].partialConfirm(confirmedBidsDemand[-1].amount - (confQty_demand - confQty_supply))
                        confirmedBidsDemand[-1][1] -= (confQty_demand - confQty_supply)
                        break
    
                    # Confirmed supply and confirmed demand are equal
                    else:
                        break
    
                # Confirmed supply and confirmed demand are equal
                else:
                    break
            
            
            confirmedBids = confirmedBidsDemand + confirmedBidsSupply
            rejectedBids = list(set(bidsReceived["Supply"] + bidsReceived["Demand"]) - set(confirmedBids))
            marketClearingPrice = sorted(confirmedBids, key = operator.attrgetter('price'))[-1].price
            marginalUnit = sorted(confirmedBids, key = operator.attrgetter('price'))[-1].ID
    
            result = MarketResults("{}".format(self.name),
                                   issuer = self.name,
                                   confirmedBids  = confirmedBids,
                                   rejectedBids = rejectedBids,
                                   partiallyConfirmedBids = partiallyConfirmedBids,
                                   marketClearingPrice = marketClearingPrice,
                                   marginalUnit = marginalUnit,
                                   status = "Case3",
                                   energyDeficit = 0,
                                   energySurplus = 0,
                                   timestamp = t)
            
    
    def feedback(self,award):
        pass

