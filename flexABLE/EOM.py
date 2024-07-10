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
from pyoptinterface import gurobi
import pandas as pd
import numpy as np


import contextlib
import sys

class DummyFile(object):
    def write(self, x): pass
    
    def flush(self): pass

@contextlib.contextmanager
def nostdout():
    save_stdout = sys.stdout
    sys.stdout = DummyFile()
    yield
    sys.stdout = save_stdout


class EOM():
    def __init__(self, name, demand = None, CBtrades = None, world = None):
        self.name = name
        self.world = world
        self.snapshots = self.world.snapshots
        self.debug_results = []

        if demand is None:
            self.demand = pd.DataFrame(0, index=self.snapshots)
        elif len(demand) != len(self.snapshots):
            print("Length of given demand does not match snapshots length!")
        else:
            self.demand = pd.Series(demand)

        if CBtrades is None:
            self.CBtrades = pd.DataFrame(0, index=self.snapshots, columns=["Import","Export"])
        elif len(CBtrades["Import"]) != len(self.snapshots) or len(CBtrades["Export"]) != len(self.snapshots):
            print("Length of given CBtrades does not match snapshots length!")
        else:
            self.CBtrades = CBtrades

        self.bids = []
        self.generation_cost = {}
        self.generation_market = {}
        self.generation_rampUp = {}
        self.generation_rampDown = {}

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
        energy_balanace_lhs = poi.quicksum(demandBids[b.ID] for b in bidsReceived["Demand"].values()) -poi.quicksum(supplyBids[b.ID] for b in bidsReceived["Supply"].values())

        energy_balance = model.add_linear_constraint(
                            energy_balanace_lhs, 
                            poi.Eq, 
                            0, 
                            name="Energy_Balance"
                        )

        obj = poi.ExprBuilder()

        for b in bidsReceived["Supply"].values():
            obj += supplyBids[b.ID] * -1 * b.price

        for b in bidsReceived["Demand"].values():
            obj += demandBids[b.ID] * b.price

        
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

        if self.world.networkEnabled:
            t_indexer = t % 4
            start_hour = t // 4
            end_hour = start_hour + 1

            self.generation_market[t] = {}
            self.generation_rampUp[t] = {}
            self.generation_rampDown[t] = {}
            self.generation_cost[t] = {}

            for bid in (confirmedBids + rejectedBids):
                if bid.bidType == 'Supply':
                    if bid.ID in self.world.network.generators.index:
                        self.generation_market[t][bid.ID] = bid.confirmedAmount
                        self.generation_cost[t][bid.ID] = bid.price
                    if bid.ID + '_positive' in self.world.network.generators.index:
                        self.generation_rampUp[t][bid.ID + '_positive'] = (bid.amount - bid.confirmedAmount)
                        self.generation_cost[t][bid.ID + '_positive'] = bid.price
                    if bid.ID + '_negative' in self.world.network.generators.index:
                        self.generation_rampDown[t][bid.ID + '_negative'] = bid.confirmedAmount
                        self.generation_cost[t][bid.ID + '_negative'] = -(marketClearingPrice - bid.price)

            if t_indexer == 3:
                # Calculate the correct network hour
                network_hour = t // 4

                # Prepare data for the last hour (4 timesteps)
                start_time = t - 3
                end_time = t + 1  # +1 because pandas slicing is end-exclusive

                # Prepare market units, ramp up and ramp down data
                market_units = pd.DataFrame(self.generation_market).T.fillna(0).loc[start_time:end_time]
                ramp_up_units = pd.DataFrame(self.generation_rampUp).T.fillna(0).loc[start_time:end_time]
                ramp_down_units = pd.DataFrame(self.generation_rampDown).T.fillna(0).loc[start_time:end_time]

                # Combine market and ramping data
                p_max_pu = pd.concat([market_units, ramp_up_units], axis=1)
                p_min_pu = pd.concat([market_units, -ramp_down_units], axis=1)

                # Ensure all generators are included, fill missing with 0
                p_max_pu = p_max_pu.reindex(self.world.network.generators.index, axis=1).fillna(0)
                p_min_pu = p_min_pu.reindex(self.world.network.generators.index, axis=1).fillna(0)

                # Set specific values for backup and loadshedding generators
                p_max_pu.loc[:, p_max_pu.columns.str.contains('_backup')] = 1
                p_min_pu.loc[:, p_min_pu.columns.str.contains('_backup')] = 0
                p_max_pu.loc[:, p_max_pu.columns.str.contains('_loadshedding')] = 0
                p_min_pu.loc[:, p_min_pu.columns.str.contains('_loadshedding')] = -1

                # Update the network's generator parameters
                self.world.network.generators_t.p_max_pu.loc[network_hour, p_max_pu.columns] = p_max_pu.mean()
                self.world.network.generators_t.p_min_pu.loc[network_hour, p_min_pu.columns] = p_min_pu.mean()

                # Prepare and update marginal costs
                marginal_costs = pd.DataFrame(self.generation_cost).T.fillna(0).loc[start_time:end_time]
                marginal_costs = marginal_costs.reindex(self.world.network.generators.index, axis=1).fillna(0)
                marginal_costs.loc[:, marginal_costs.columns.str.contains('_backup')] = 30000
                marginal_costs.loc[:, marginal_costs.columns.str.contains('_loadshedding')] = -30000
                self.world.network.generators_t.marginal_cost.loc[network_hour, marginal_costs.columns] = self.resample(marginal_costs).mean()

                # Calculate and update load values
                new_load_values = self.world.demand_dist.iloc[start_time:end_time].mul(
                    self.demand[start_time:end_time] + self.CBtrades['Export'][start_time:end_time] - self.CBtrades['Import'][start_time:end_time], 
                    axis=0
                ).sum().add_suffix('_load')

                new_load_df = pd.DataFrame(new_load_values).T
                new_load_df = new_load_df.reindex(columns=self.world.network.loads_t.p_set.columns).fillna(0)
                self.world.network.loads_t.p_set.loc[network_hour, :] = new_load_df.iloc[0]

                # Perform powerflow calculation
                with nostdout():
                    lopf_result = self.world.network.lopf(snapshots=[network_hour],
                                                        solver_name='gurobi',
                                                        solver_options={'ResultFile':'model.ilp'})
                
                if lopf_result[1] == 'optimal':
                    self.world.logger.info(f'Redispatch solution for hour {network_hour}: \033[1;32m optimal \x1b[0m')
                else:
                    self.world.logger.info(f'Redispatch solution for hour {network_hour}: \033[1;31m infeasible \x1b[0m')




        result = MarketResults(f"{self.name}",
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

    def resample(self,df, agg='sum'):
        if agg == 'sum':
            return df.groupby(df.index//4).sum()/4
        elif agg == 'mean':
            return df.groupby(df.index//4).mean()
        else:
            raise ValueError(f'agg must be either sum or mean, {agg} not implemented')
        