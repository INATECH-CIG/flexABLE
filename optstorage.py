 # -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 16:06:57 2020

@author: intgridnb-02
"""
import pandas as pd
import pyomo.environ as pyo
from pyomo.opt import SolverFactory

from misc import initializer
from bid import Bid

class OptStorage():
    
    @initializer
    def __init__(self,
                 agent=None,
                 name='Storage_1',
                 technology='PSPP',
                 min_soc=1,
                 max_soc=1000,
                 max_power_ch=100,
                 max_power_dis=100,
                 efficiency_ch=0.8,
                 efficiency_dis=0.9,
                 ramp_up=100,
                 ramp_down=100,
                 variable_cost_ch=0.28,
                 variable_cost_dis=0.28,
                 natural_inflow = 1.8, # [MWh/qh]
                 company = 'UNIPER',
                 world = None,
                 **kwargs):

        self.name += '_opt'
        # Unit status parameters
        self.currentCapacity = 0
        self.foresight = int(2/self.world.dt)

        if self.world.rl_mode:
            self.device = self.world.device
            self.float_type = self.world.float_type


    def reset(self):
        self.total_capacity = [0. for n in self.world.snapshots]

        self.soc = [0. for n in self.world.snapshots]
        self.soc[0] = self.min_soc
        self.soc.append(self.min_soc)

        self.energy_cost = [0. for n in self.world.snapshots]
        self.energy_cost.append(0.)

        self.bids_supply = {n:(0.,0.) for n in self.world.snapshots}
        self.bids_demand = {n:(0.,0.) for n in self.world.snapshots}
        self.confQtyCRM_neg = {n:0 for n in self.world.snapshots}
        self.confQtyCRM_pos = {n:0 for n in self.world.snapshots}

        self.sent_bids=[]

        self.rewards = [0. for _ in self.world.snapshots]
        self.profits = [0. for _ in self.world.snapshots]

        self.opt_soc = [0. for n in self.world.snapshots]
        self.opt_soc[0] = self.min_soc
        self.opt_soc.append(self.min_soc)      
        self.opt_profits = [0. for _ in self.world.snapshots]
        self.opt_bids_supply = {n:(0.,0.) for n in self.world.snapshots}
        self.opt_bids_demand = {n:(0.,0.) for n in self.world.snapshots}

        # pfc = pd.read_csv('input/{}/mcp.csv'.format(self.world.scenario))
        # pfc = pfc['Price'].tolist()
        pfc=None
        self.p_ch, self.p_dis = self.optimal_strategy(pfc)


    def step(self):
        t = self.world.currstep
        conf_bid_supply, conf_bid_demand = 0., 0.
            
        for bid in self.sent_bids:
            if 'supplyEOM' in bid.ID:
                conf_bid_supply = bid.confirmedAmount
                self.bids_supply[t] = (bid.confirmedAmount, bid.price)
            if 'demandEOM' in bid.ID:
                conf_bid_demand = bid.confirmedAmount
                self.bids_demand[t] = (bid.confirmedAmount, bid.price)

        self.total_capacity[t] = conf_bid_supply-conf_bid_demand

        self.soc[t+1] = self.soc[t] + (conf_bid_demand*self.efficiency_ch - conf_bid_supply/self.efficiency_dis)*self.world.dt
        self.soc[t+1] = max(self.soc[t+1], self.min_soc)

        if self.soc[t+1] >= self.min_soc+self.world.minBidEOM:
            self.energy_cost[t+1] = (self.energy_cost[t]*self.soc[t] - self.total_capacity[t]*self.world.mcp[t]*self.world.dt)/self.soc[t+1]
        else:
            self.energy_cost[t+1] = 0.

        profit = (conf_bid_supply-conf_bid_demand)*self.world.mcp[t]*self.world.dt
        profit -= (conf_bid_supply*self.variable_cost_dis + conf_bid_demand*self.variable_cost_ch)

        scaling = 0.1/self.max_power_ch

        self.rewards[t] = profit*scaling
        self.profits[t] = profit

        self.sent_bids=[]

        
    def feedback(self, bid):
        t = self.world.currstep

        if bid.status == "Confirmed":
            if 'CRMPosDem' in bid.ID:
                self.confQtyCRM_pos[t] = bid.confirmedAmount
                
            if 'CRMNegDem' in bid.ID:
                self.confQtyCRM_neg[t] = bid.confirmedAmount
            
        elif bid.status =="PartiallyConfirmed":
            if 'CRMPosDem' in bid.ID:
                self.confQtyCRM_pos[t] = bid.confirmedAmount
                
            if 'CRMNegDem' in bid.ID:
                self.confQtyCRM_neg[t] = bid.confirmedAmount
            
        self.sent_bids.append(bid)


    def formulate_bids(self, t, market="EOM"):
        bids = []
        
        if market == "EOM":
            bids.extend(self.calculate_bids_eom())
                        
        return bids
      

    def calculate_bids_eom(self):
        t = self.world.currstep
        bids = []

        bid_quantity_supply = min(max((self.soc[self.world.currstep] - self.min_soc)*self.efficiency_dis/self.world.dt, 0),
                                    self.p_dis[t])

        bid_quantity_demand = min(max((self.max_soc - self.soc[self.world.currstep])/self.efficiency_ch/self.world.dt, 0),
                                    self.p_ch[t])

        if bid_quantity_supply >= self.world.minBidEOM:
            bids.append(Bid(issuer=self,
                            ID="{}_supplyEOM".format(self.name),
                            price=(-100.),
                            amount=bid_quantity_supply,
                            status="Sent",
                            bidType="Supply",
                            node=self.node))

        if bid_quantity_demand >= self.world.minBidEOM:
            bids.append(Bid(issuer=self,
                            ID="{}_demandEOM".format(self.name),
                            price=100.,
                            amount=bid_quantity_demand,
                            status="Sent",
                            bidType="Demand",
                            node=self.node))

        return bids



    def optimal_strategy(self, pfc=None):
        if pfc == None:
            pfc = self.world.pfc
        #create model
        model = pyo.ConcreteModel()
        
        #define indices
        model.t = pyo.RangeSet(0, len(self.world.snapshots)-1)
        
        #define variables
        model.p_charge = pyo.Var(model.t, domain=pyo.NonNegativeReals, bounds = (0.0, self.max_power_ch)) 
        model.p_discharge = pyo.Var(model.t, domain=pyo.NonNegativeReals, bounds = (0.0, self.max_power_dis))
        model.soc = pyo.Var(model.t, domain=pyo.NonNegativeReals, bounds = (self.min_soc, self.max_soc))
        model.profit = pyo.Var(model.t, domain=pyo.Reals)

        #objective
        def rule_objective(model):
            return pyo.quicksum(model.profit[t] for t in model.t)
        
        model.obj = pyo.Objective(rule=rule_objective, sense=pyo.maximize)
        
    #constraints    
        def soc_rule(model, t):
            if t==0:
                return model.soc[t]== self.min_soc + model.p_charge[t]*self.efficiency_ch - model.p_discharge[t]/self.efficiency_dis
            else:
                return model.soc[t]== model.soc[t-1] + model.p_charge[t]*self.efficiency_ch - model.p_discharge[t]/self.efficiency_dis
        
        model.soc_rule = pyo.Constraint(model.t, rule=soc_rule)

        def profit_rule(model, t):
            expr = model.profit[t] == (model.p_discharge[t]-model.p_charge[t])*pfc[t]*self.world.dt -\
                (model.p_discharge[t]*self.variable_cost_dis +
                 model.p_charge[t]*self.variable_cost_ch)
            return expr

        model.profit_rule = pyo.Constraint(model.t, rule=profit_rule)
        
        # solve model
        opt = SolverFactory("glpk")
        
        opt.solve(model)

        p_ch = []
        p_dis = []
                
        for t in self.world.snapshots:
            p_ch.append(model.p_charge[t].value)
            p_dis.append(model.p_discharge[t].value)
            self.opt_soc[t+1] = model.soc[t].value
            self.opt_profits[t] = model.profit[t].value
            self.opt_bids_supply[t] = (model.p_discharge[t].value, 0.)
            self.opt_bids_demand[t] = (model.p_charge[t].value, 0.)
        
        return p_ch, p_dis