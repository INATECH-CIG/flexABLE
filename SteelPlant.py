# -*- coding: utf-8 -*-
"""
Created on 18 July 2022

@author: Louis

"""
from tracemalloc import Snapshot
from misc import initializer
from bid import Bid
import pyomo.environ as pyo
from pyomo.opt import SolverFactory
import numpy as np
from pyomo.opt import SolverStatus, TerminationCondition

class SteelPlant():
    
    @initializer
    def __init__(self,
                 agent=None,
                 name='KKW ISAR 2',
                 technology='Steel_Plant',
                 max_capacity=1500,
                 min_capacity=375,
                 target_capacity=1200,
                 HBI_storage_capacity=200,
                 mass_ratio_iron=1.66,
                 mass_ratio_DRI=1.03,
                 mass_ratio_liquid_steel=1,
                 spec_elec_cons_EH=.37,
                 spec_elec_cons_DRP=.127,
                 spec_elec_cons_AF=.575,
                 spec_NG_cons_DRP=1.56,
                 spec_NG_cons_AF=.216,
                 spec_coal_cons_AF=.028,
                 company='producer_01',
                 node='Bus_DE',
                 world=None,
                 **kwargs):

        #define time horizon in which production compnesation must be achieved 
        self.opt_horizon = int(7*24/self.world.dt)

        #hourly steel production target
        self.target_capacity = self.target_capacity*self.world.dt

        #steel production target for snapshot window 
        self.target_prod = self.target_capacity*self.opt_horizon
                  
        self.limits = self.calc_power_limits()
        self.solver = pyo.SolverFactory('glpk') 
                
        #price signals for elec, NG, and coal 
        self.elec_price_signal = self.world.pfc.copy()
        self.ng_price_signal = self.world.fuelPrices['natural gas']
        self.coal_price_signal = self.world.fuelPrices['hard coal']


    def reset(self):
        """
        Resets the status of the simulation
        """
        self.total_capacity = [0. for n in self.world.snapshots]
        
        self.sentBids = []

        #run optimization for the whole simulation horizon         
        self.op_params = self.process_opt(time_horizon=self.opt_horizon,
                                          total_prod=self.target_prod)

        #and extract values
        self.opt_cap = [0. for i in self.world.snapshots]
        self.pos_flex_cap = [0. for i in self.world.snapshots]
        self.neg_flex_cap = [0. for i in self.world.snapshots]

        self.opt_cap[:self.opt_horizon] = self.op_params['elec_cons']
        temp = self.flex_available(time_horizon=self.opt_horizon,
                                   elec_cons=self.opt_cap)
        self.pos_flex_cap[:self.opt_horizon] = temp[0]
        self.neg_flex_cap[:self.opt_horizon] =temp[1]

        self.opt_prod = [0. for i in self.world.snapshots]
        self.opt_prod[:self.opt_horizon] = self.op_params['liquid_steel']

        #create dictionaries for the confirmed capacities
        self.conf_plan = {n:0 for n in self.world.snapshots}
        self.conf_neg_flex = {n:0 for n in self.world.snapshots}
        self.conf_pos_flex = {n:0 for n in self.world.snapshots}

        self.bids_plan = {n:(0.,0.) for n in self.world.snapshots}
        self.bids_flex_neg = {n:(0.,0.) for n in self.world.snapshots}
        self.bids_flex_pos = {n:(0.,0.) for n in self.world.snapshots}

        #varaible to keep track of steel produciton
        self.total_prod = 0.
        self.deficit = 0.


    def formulate_bids(self, t, market="EOM"):
        bids=[]
        
        #create three bids
        if market == "EOM":
            bids_dict = self.calculateBidEOM(t)
            if bids_dict['bid_cap_plan'] >= self.world.minBidEOM:
                bids.append(Bid(issuer=self,
                                ID="{}_norm_op_EOM".format(self.name),
                                price=3000.,
                                amount=bids_dict['bid_cap_plan'],
                                status="Sent",
                                bidType="Demand",
                                node=self.node))

            if bids_dict['bid_cap_flex_pos'] >= self.world.minBidEOM:
                bids.append(Bid(issuer=self,
                                ID="{}_pos_flex_EOM".format(self.name),
                                price=bids_dict['bid_cap_flex_pos'],
                                amount=bids_dict['bid_price_flex_pos'],
                                status="Sent",
                                bidType="Supply",
                                node=self.node))

            if bids_dict['bid_cap_flex_neg'] >= self.world.minBidEOM:
                bids.append(Bid(issuer=self,
                                ID="{}_neg_flex_EOM".format(self.name),
                                price=bids_dict['bid_cap_flex_neg'],
                                amount=bids_dict['bid_price_flex_neg'],
                                status="Sent",
                                bidType="Demand",
                                node=self.node))

        return bids
    

    def calculateBidEOM(self, t):
        bid_cap_plan = self.opt_cap[t]
        
        bid_cap_flex_pos = self.pos_flex_cap[t]
        bid_price_flex_pos = 100.
        
        bid_cap_flex_neg = self.neg_flex_cap[t]
        bid_price_flex_neg = 10.

        bids_dict = {'bid_cap_plan': bid_cap_plan,
                     'bid_cap_flex_pos': bid_cap_flex_pos,
                     'bid_price_flex_pos': bid_price_flex_pos,
                     'bid_cap_flex_neg': bid_cap_flex_neg,
                     'bid_price_flex_neg': bid_price_flex_neg}

        return bids_dict


    def step(self):
        t = self.world.currstep

        for bid in self.sentBids:
            if 'norm_op_EOM' in bid.ID:
                self.total_capacity[t] += bid.confirmedAmount
                self.bids_plan[t] = (bid.confirmedAmount, bid.price)
            elif 'neg_flex_EOM' in bid.ID:
                self.total_capacity[t] += bid.confirmedAmount
                self.bids_flex_neg[t] = (bid.confirmedAmount, bid.price)
            elif 'pos_flex_EOM' in bid.ID:
                self.total_capacity[t] -= bid.confirmedAmount
                self.bids_flex_pos[t] = (bid.confirmedAmount, bid.price)

        if self.total_capacity[t] == self.opt_cap[t]: #equal to the optimal operation
                self.total_prod += self.opt_prod[t]

        else:
            # define consumption signal
            flex_params = {'hour_called': 0,
                           'cons_signal': self.total_capacity[t]}

            self.op_params = self.process_opt(time_horizon=self.opt_horizon,
                                              total_prod=self.target_prod+self.deficit,
                                              flex_params=flex_params)

            self.opt_cap[t:t+self.opt_horizon] = self.op_params['elec_cons']
            temp = self.flex_available(time_horizon=self.opt_horizon,
                                    elec_cons=self.opt_cap)
            self.pos_flex_cap[t:t+self.opt_horizon] = temp[0]
            self.neg_flex_cap[t:t+self.opt_horizon] = temp[1]

            self.opt_prod[t:t+self.opt_horizon] = self.op_params['liquid_steel']

            #determine how much liquid steel needs to be compensated for 
            self.total_prod += self.op_params['liquid_steel'][0]
            self.deficit = self.target_capacity*t - self.total_prod
                             
        self.sentBids = []
                
        
    def feedback(self, bid):

        if 'norm_op_mrEOM' in bid.ID:
            self.conf_plan[self.world.currstep] = bid.confirmedAmount
            
        elif 'pos_flex_mrEOM' in bid.ID:
            self.conf_pos_flex[self.world.currstep] = bid.confirmedAmount

        elif 'neg_flex_mrEOM' in bid.ID:
            self.conf_neg_flex[self.world.currstep] = bid.confirmedAmount   
            
        self.sentBids.append(bid)
        

    def calc_power_limits(self):
        liquid_steel_max = self.max_capacity
        liquid_steel_min = self.min_capacity
        
        dri_max = liquid_steel_max*self.mass_ratio_DRI
        dri_min = liquid_steel_min*self.mass_ratio_DRI
        
        iron_ore_max = dri_max*self.mass_ratio_iron
        iron_ore_min = dri_min*self.mass_ratio_iron
        
        EH_max = iron_ore_max*self.spec_elec_cons_EH
        EH_min = iron_ore_min*self.spec_elec_cons_EH
        
        DRP_max = dri_max*self.spec_elec_cons_DRP
        DRP_min = dri_min*self.spec_elec_cons_DRP
        
        AF_max = liquid_steel_max*self.spec_elec_cons_AF
        AF_min = liquid_steel_min*self.spec_elec_cons_AF

        total_max = EH_max + DRP_max + AF_max

        if self.HBI_storage_capacity != 0:
            total_min = AF_min
        else:
            total_min = EH_min + DRP_min + AF_min

        limits = {'max_ls': liquid_steel_max,
                  'min_ls': liquid_steel_min,
                  'max_dri': dri_max,
                  'min_dri': dri_min,
                  'max_iron': iron_ore_max,
                  'min_iron': iron_ore_min,
                  'EH_max': EH_max,
                  'EH_min': EH_min,
                  'DRP_max': DRP_max,
                  'DRP_min': DRP_min,
                  'AF_max': AF_max,
                  'AF_min': AF_min,
                  'total_max': total_max,
                  'total_min': total_min}

        return limits


    def process_opt(self, time_horizon, total_prod, flex_params=None):
        model = pyo.ConcreteModel()    
        
        model.t = pyo.RangeSet(0, time_horizon-1)

        model.iron_ore = pyo.Var(model.t, domain = pyo.NonNegativeReals) 
        model.storage_status = pyo.Var(model.t, within=pyo.Binary)

        model.dri_direct = pyo.Var(model.t, domain = pyo.NonNegativeReals)
        model.dri_to_storage = pyo.Var(model.t, domain = pyo.NonNegativeReals)
        model.dri_from_storage = pyo.Var(model.t, domain = pyo.NonNegativeReals)
        
        model.liquid_steel = pyo.Var(model.t, domain = pyo.NonNegativeReals, bounds = (self.limits['min_ls'],self.limits['max_ls'])) 

        model.storage = pyo.Var(model.t, domain=pyo.NonNegativeReals, bounds=(0,self.limits['max_dri']))
        
        model.elec_cons = pyo.Var(model.t, domain = pyo.NonNegativeReals)
        model.ng_cons = pyo.Var(model.t, domain = pyo.NonNegativeReals)
        model.coal_cons = pyo.Var(model.t, domain = pyo.NonNegativeReals)

        model.elec_cost = pyo.Var(model.t)
        model.ng_cost = pyo.Var(model.t)
        model.coal_cost = pyo.Var(model.t)
        
        #flexibility variables 
        model.pos_flex = pyo.Var(model.t,domain = pyo.NonNegativeReals )  #could set bounds to power limits
        model.neg_flex = pyo.Var(model.t, domain = pyo.NonNegativeReals)

        #represents the step of electric arc furnace
        def eaf_rule(model, t):
            return model.liquid_steel[t] == (model.dri_direct[t] + model.dri_from_storage[t]*0.95) / self.mass_ratio_DRI

        #represents the direct reduction plant
        def iron_reduction_rule(model, t):
            return model.dri_direct[t] + model.dri_to_storage[t] == model.iron_ore[t] / self.mass_ratio_iron

        def dri_min_rule(model, t):
            return (model.dri_direct[t] + model.dri_to_storage[t]) >= self.limits['min_dri']*model.storage_status[t]
        
        def dri_max_rule(model, t):
            return (model.dri_direct[t] + model.dri_to_storage[t]) <= self.limits['max_dri']*model.storage_status[t]
        
        def iron_ore_min_rule(model, t):
            return model.iron_ore[t] >= self.limits['min_iron']*model.storage_status[t]     #62.5
            
        def iron_ore_max_rule(model, t):
            return model.iron_ore[t] <= self.limits['max_iron']*model.storage_status[t]
        
        def storage_rule(model, t):
            if t==0:
                return model.storage[t] == 0 + model.dri_to_storage[t] - model.dri_from_storage[t]
            else:
                return model.storage[t] == model.storage[t-1] + model.dri_to_storage[t] - model.dri_from_storage[t]
        
        #total electricity consumption
        def elec_consumption_rule(model, t):
            return model.elec_cons[t] == self.spec_elec_cons_EH*model.iron_ore[t] + \
                self.spec_elec_cons_DRP*(model.dri_direct[t] + model.dri_from_storage[t]) + \
                self.spec_elec_cons_AF*model.liquid_steel[t]

        #total electricity cost
        def elec_cost_rule(model, t):
            return model.elec_cost[t] == self.elec_price_signal[t]*model.elec_cons[t]
        
    # =============================================================================
    #     #flexibility rule
        def elec_flex_rule(model, t):
            if t == flex_params['hour_called']:
            #reduce consumption
                return model.elec_cons[t] == flex_params['cons_signal']
            else:
                return model.elec_cons[t] >= 0
    #         
    # =============================================================================
            
        #total NG consumption
        def ng_consumption_rule(model,t):
            return model.ng_cons[t] == self.spec_NG_cons_DRP*(model.dri_direct[t] + model.dri_from_storage[t]) + \
                self.spec_NG_cons_AF*model.liquid_steel[t] 
        
        #total NG cost
        def ng_cost_rule(model,t):
            return model.ng_cost[t] == self.ng_price_signal[t]*model.ng_cons[t]
        
        #total coal consumption
        def coal_consumption_rule(model, t):
            return model.coal_cons[t] == self.spec_coal_cons_AF*model.liquid_steel[t]
        
        #total coal cost
        def coal_cost_rule(model,t):
            return model.coal_cost[t] == self.coal_price_signal[t]*model.coal_cons[t]

        def total_steel_prod_rule(model):
            return pyo.quicksum(model.liquid_steel[t] for t in model.t) >= total_prod

        #cost objective function (elec, NG, and coal)
        def cost_obj_rule(model):
            return pyo.quicksum(model.elec_cost[t] + model.ng_cost[t] + model.coal_cost[t] for t in model.t)

        model.eaf_rule = pyo.Constraint(model.t, rule=eaf_rule)
        model.iron_reduction_rule = pyo.Constraint(model.t, rule=iron_reduction_rule)
        model.elec_consumption_rule = pyo.Constraint(model.t, rule=elec_consumption_rule)
        model.elec_cost_rule = pyo.Constraint(model.t, rule=elec_cost_rule)
        model.ng_consumption_rule = pyo.Constraint(model.t, rule = ng_consumption_rule)
        model.ng_cost_rule = pyo.Constraint(model.t, rule = ng_cost_rule)
        model.coal_consumption_rule = pyo.Constraint(model.t, rule = coal_consumption_rule)
        model.coal_cost_rule = pyo.Constraint(model.t, rule = coal_cost_rule)
        model.total_steel_prod_rule = pyo.Constraint(rule = total_steel_prod_rule)

        model.storage_rule = pyo.Constraint(model.t, rule = storage_rule)
        model.dri_min_rule = pyo.Constraint(model.t, rule = dri_min_rule)
        model.dri_max_rule = pyo.Constraint(model.t, rule = dri_max_rule)

        model.iron_ore_min_rule = pyo.Constraint(model.t, rule = iron_ore_min_rule)
        model.iron_ore_max_rule = pyo.Constraint(model.t, rule = iron_ore_max_rule)
        
        #flexibility constraint included if called
        if flex_params is not None:
            model.elec_flex_rule = pyo.Constraint(model.t, rule = elec_flex_rule)
            
        model.obj = pyo.Objective(rule = cost_obj_rule, sense = pyo.minimize)

        self.solver.solve(model)

        op_params = self.get_values(model=model,
                                           time_horizon=time_horizon)

        return op_params
    
    def flex_available(self, time_horizon, elec_cons):
        pos_flex = []
        neg_flex = []
            
        for i in range(1, time_horizon): #why from 1?
            # potential to increase elec consumption from grid
            neg_flex.append(self.limits['total_max'] - elec_cons[i-1])
            # potential to reduce elec consumption
            pos_flex.append(elec_cons[i-1] - self.limits['total_min'])

        return pos_flex, neg_flex
    
        
    def get_values(self, model, time_horizon):
        op_params = {}

        iron_ore = []
        storage_status = []
        dri_direct = []
        dri_to_storage = []
        dri_from_storage = []
        liquid_steel = []
        elec_cons = []
        elec_cost = []
        ng_cons = []
        ng_cost = []
        coal_cons = []
        coal_cost = []
        
    # list to check flexibility calc in model 
        elec_cons_EH = []
        elec_cons_DRP = []
        elec_cons_AF = []
        storage = []
    
        for i in range(1, time_horizon):            
            iron_ore.append(model.iron_ore[i].value)
            dri_direct.append(model.dri_direct[i].value)
            dri_to_storage.append(model.dri_to_storage[i].value)
            dri_from_storage.append( model.dri_from_storage[i].value)
            liquid_steel.append(model.liquid_steel[i].value)
            elec_cons.append(model.elec_cons[i].value)
            elec_cost.append(model.elec_cost[i].value)
            ng_cons.append(model.ng_cons[i].value)
            ng_cost.append(model.ng_cost[i].value)
            coal_cons.append(model.coal_cons[i].value)
            coal_cost.append(model.coal_cost[i].value)
            
            elec_cons_EH.append(self.spec_elec_cons_EH*model.iron_ore[i].value)
            elec_cons_DRP.append(self.spec_elec_cons_DRP*(model.dri_direct[i].value + model.dri_to_storage[i].value))
            elec_cons_AF.append( self.spec_elec_cons_AF*model.liquid_steel[i].value)
            storage_status.append(model.storage_status[i].value)
            storage.append(model.storage[i].value)
    
        op_params['iron_ore'] = iron_ore
        op_params['dri_direct'] = dri_direct
        op_params['dri_to_storage'] = dri_to_storage
        op_params['dri_from_storage'] = dri_from_storage
        op_params['liquid_steel'] =liquid_steel
        op_params['elec_cons'] =elec_cons
        op_params['ng_cons'] = ng_cons
        op_params['coal_cons'] =coal_cons
        op_params['coal_cost'] = coal_cost
        op_params['EH_elec_cons'] = elec_cons_EH
        op_params['DRP_elec_cons'] = elec_cons_DRP
        op_params['AF_elec_cons'] = elec_cons_AF
        op_params['storage_status'] = storage_status
        op_params['storage'] = storage
                       
        return op_params
            
    
    

    
    
    
    
    
    
    
    
    