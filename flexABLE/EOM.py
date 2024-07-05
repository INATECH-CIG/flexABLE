# -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 16:08:03 2020

@author: intgridnb-02
"""
import operator
from .bid import Bid
import logging
from .MarketResults import MarketResults
import pyoptinterface as poi
from pyoptinterface import gurobi, highs



class EOM():
    def __init__(self, name, demand = None, CBtrades = None, world = None):
        self.name = name
        self.world = world
        self.snapshots = self.world.snapshots

        self.debug_results = []
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

    def feedback(self,award):
        pass

    def _prepareReceivedBids(self):
        bidsReceived = {"Supply": {}, "Demand": {}}
        for b in self.bids:
            bidsReceived[b.bidType][b.ID]=b

        return bidsReceived

    def _inelasticDemandBid(self, t):
        '''
        Create an inelastic demand bid for the given time step and adds it to self.bids
        '''
        self.bids.append(
            Bid(
                issuer=self,
                ID=f"IEDt{t}",
                price=3000.0,
                amount=self.demand[t],
                status="Sent",
                bidType="Demand",
            )
        )

    def marketClearing(self, t):
        # Add inelastic demand bid
        self._inelasticDemandBid(t)
        # Extract bids and categorize them
        bidsReceived = self._prepareReceivedBids()

        model = gurobi.Model()

        # Create variables
        # Supply bids
        supplyBids = model.add_variables(
                        [b.ID for b in bidsReceived["Supply"].values()],
                        name="Supply_Bids",
                    )
        
        # Setting upper and lower bounds for supply bids
        for b in bidsReceived["Supply"].values():
            model.set_variable_attribute(supplyBids[b.ID], poi.VariableAttribute.UpperBound, b.amount)
            model.set_variable_attribute(supplyBids[b.ID], poi.VariableAttribute.LowerBound, 0.0)

        # Demand bids
        demandBids = model.add_variables(
                        [b.ID for b in bidsReceived["Demand"].values()],
                        name="Demand_Bids",
                    )
        
        # Setting upper bounds for demand bids
        for b in bidsReceived["Demand"].values():
            model.set_variable_attribute(demandBids[b.ID], poi.VariableAttribute.UpperBound, b.amount)
            model.set_variable_attribute(demandBids[b.ID], poi.VariableAttribute.LowerBound, 0.0)

        # Constraints 
        # Energy balance constraint
        energy_balanace_lhs = poi.quicksum(demandBids[b.ID] for b in bidsReceived["Demand"].values()) - poi.quicksum(supplyBids[b.ID] for b in bidsReceived["Supply"].values())

        energy_balance = model.add_linear_constraint(
                            energy_balanace_lhs, 
                            poi.Eq, 
                            0, 
                            name="Energy_Balance"
                        )

        obj = poi.ExprBuilder()
        obj_str = ""
        for b in bidsReceived["Supply"].values():
            obj += supplyBids[b.ID] * -1 * b.price
            obj_str += f"{b.amount} * {b.price} \n"
        for b in bidsReceived["Demand"].values():
            obj += demandBids[b.ID] * b.price
            obj_str += f"{b.amount} * {b.price} \n"
        
        model.set_objective(obj, poi.ObjectiveSense.Maximize)
        # suppress the output of the solver
        model.set_model_attribute(poi.ModelAttribute.Silent, True)
        model.optimize()
        marketClearingPrice= model.get_constraint_raw_attribute(energy_balance, 'Pi')
        # Iterate over the bids to confirm or reject them
        for b in bidsReceived["Supply"].values():
            b.partialConfirm(model.get_value(supplyBids[b.ID]))
        for b in bidsReceived["Demand"].values():
            b.partialConfirm(model.get_value(demandBids[b.ID]))

        confirmedBids = [b for b in self.bids if b.status == "Confirmed"]
        rejectedBids = [b for b in self.bids if b.status == "Rejected"]
        partiallyConfirmedBids = [b for b in self.bids if b.status == "Partially Confirmed"]
        
        result = MarketResults("{}".format(self.name),
                    issuer = self.name,
                    confirmedBids = confirmedBids,
                    rejectedBids = rejectedBids,
                    partiallyConfirmedBids = partiallyConfirmedBids,
                    marketClearingPrice = marketClearingPrice,
                    marginalUnit = '',
                    status = '',
                    energyDeficit = 0,
                    energySurplus = 0,
                    timestamp = t)
        self.world.dictPFC[t] = marketClearingPrice
        self.debug_results.append(result)