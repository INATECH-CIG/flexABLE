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
                 agent = None,
                 name = 'KKW ISAR 2',
                 technology = 'Steel_Plant',
                 max_capacity = 1500,
                 min_production = 375,  
                 HBI_storage_capacity = 200 ,              
                 mass_ratio_iron = 1.66,
                 mass_ratio_DRI = 1.03,
                 mass_ratio_liquid_steel = 1,                 
                spec_elec_cons_EH = .37,
                spec_elec_cons_DRP = .127,
                spec_elec_cons_AF = .575,
                spec_NG_cons_DRP = 1.56,
                spec_NG_cons_AF = .216,
                spec_coal_cons_AF = .028,  
                company = 'producer_01',
                 node = 'Bus_DE',
                 world = None,
                  **kwargs):
        
        # bids status parameters
        self.snapshots = range(100)
      
        self.optimization_horizon = 48
       
       #daily steel production target
        self.daily_steel_prod_target = self.max_capacity * 0.8
       
       #average hourly production target 
        self.hourly_prod = self.daily_steel_prod_target/24
       
       #annual steel production target
        self.steel_prod = self.daily_steel_prod_target* 365
       
        # Unit status parameters
        self.sentBids=[]          
           
        self.limits = self.calc_power_limits(time_horizon = len(self.snapshots))
        self.solver = pyo.SolverFactory('glpk') 
        
        #Left in case initialization needed
        #self.dict_capacity_opt = {n:0 for n in self.snapshots}
        #self.dict_capacity_neg_flex = {n:0 for n in self.snapshots}
        #self.dict_capacity_pos_flex = {n:0 for n in self.snapshots}
        
        #price signals for elec, NG, and coal 
        self.elec_price_signal = np.empty(len(self.snapshots), dtype=np.float)
        self.elec_price_signal.fill(30)
        
        self.ng_price_signal = np.empty(len(self.snapshots), dtype=np.float)
        self.ng_price_signal.fill(25)
        
        self.coal_price_signal = np.empty(len(self.snapshots), dtype=np.float)
        self.coal_price_signal.fill(8.5)

    def reset(self):
        """
        Resets the status of the simulation
        """
        self.total_capacity = [0. for n in self.snapshots]
        
        self.sentBids = []
        self.limits = self.calc_power_limits(time_horizon =len(self.snapshots))     
        self.solver = pyo.SolverFactory


        #run optimization for the whole simulation horizon         
        self.model = self.process_opt(time_horizon = len(self.snapshots),steel_prod =self.steel_prod ,flexibility_params=None)
        self.model_params = self.get_values(self.model, time_horizon = len(self.snapshots))
        
        #and extract values
        self.dict_capacity_opt = self.model_params['elec_cons']
        self.dict_capacity_pos_flex, self.dict_capacity_neg_flex = self.flexibility_available(time_horizon = self.snapshots, 
                                                                                               model = self.model,
                                                                                               elec_cons=self.model_params['elec_cons'])
        
        #create dictionaries for the confirmed capacities
        self.conf_opt = {n:0 for n in self.snapshots}
        self.conf_neg_flex = {n:0 for n in self.snapshots}
        self.conf_pos_flex = {n:0 for n in self.snapshots}

        #varaible to keep track of steel produciton
        self.total_liquid_steel_produced = 0


    def step(self):
        t = self.world.currstep

        for bid in self.sentBids:
            if 'norm_op_mrEOM' in bid.ID or 'neg_flex_mrEOM' in bid.ID:
                self.total_capacity[t] += bid.confirmedAmount
            elif 'pos_flex_mrEOM' in bid.ID:
                self.total_capacity[t] -= bid.confirmedAmount

        if self.total_capacity[t] == self.dict_capacity_opt[t]: #equal to the optimal operation
                self.total_liquid_steel_produced += self.model_params['liquid_steel'][t]
                

        else:
            # define consumption signal
            flexibility_params = {'hour_called': 0,
                                  'cons_signal': self.total_capacity[t]}

           
            #determine how much liquid steel needs to be compensated for 
            # deficit will be positive when pos flex called
            # deficit will be negative when neg flex called 
            self.steel_deficit = self.hourly_prod - self.model_params['liquid_steel'][t] 
            self.steel_prod_opt_horizon = self.optimization_horizon*self.hourly_prod + self.steel_deficit
                
                          
                       
           #rerun optimization (compensate steel prod within 48 hour optimization horizon)
            self.flex_case = self.process_opt(time_horizon = self.optimization_horizon ,
                                              steel_prod =self.steel_prod_opt_horizon,
                                              flexibility_params=flexibility_params)
            
            #extract values of flex_case
            self.flex_params = self.get_values(self.flex_case, time_horizon =  self.optimization_horizon)
            
                        
            #save new steel production - will be first value in new flex_params dict
            self.total_liquid_steel_produced += self.flex_params['liquid_steel'][0] 
            
            #update capacity dictionaries from current time step until optimization horizon ends
            self.dict_capacity_opt[t: t+ self.optimization_horizon ] = self.flex_params['elec_cons']
            self.dict_capacity_pos_flex[t:t+ self.optimization_horizon ], self.dict_capacity_neg_flex[t: ] = self.flexibility_available(time_horizon = self.optimization_horizon, 
                                                                                                   model = self.flex_case,
                                                                                                   elec_cons=self.flex_params['elec_cons'])
                 
        self.sentBids = []
                
        
    def feedback(self, bid):

        if bid.status == "Confirmed":
            if 'norm_op_mrEOM' in bid.ID:
                self.conf_opt[self.world.currstep] = bid.confirmedAmount
                
            if 'pos_flex_mrEOM' in bid.ID:
                self.conf_pos_flex[self.world.currstep] = bid.confirmedAmount

            if 'neg_flex_mrEOM' in bid.ID:
                self.conf_neg_flex[self.world.currstep] = bid.confirmedAmount   
            
        elif bid.status =="PartiallyConfirmed":
             if 'norm_op_mrEOM' in bid.ID:
                self.conf_opt[self.world.currstep] = bid.confirmedAmount
                
             if 'pos_flex_mrEOM' in bid.ID:
                self.conf_pos_flex[self.world.currstep] = bid.confirmedAmount

             if 'neg_flex_mrEOM' in bid.ID:
                self.conf_neg_flex[self.world.currstep] = bid.confirmedAmount   

        self.sentBids.append(bid)
        
        
    def formulate_bids(self, t, market="EOM"):
        bids=[]
        
        #create three bids
        if market=="EOM":
            norm_op_bid_Quantity, pos_flex_bid_Quantity, pos_flex_bid_Price, \
            neg_flex_bid_Quantity, neg_flex_bid_Price = self.calculateBidEOM(t)

            # add checks for min bid quantity
            if norm_op_bid_Quantity >= self.world.minBidEOM:
                bids.append(Bid(issuer = self,
                                ID = "{}_norm_op_mrEOM".format(self.name),
                                price = 3000.,
                                amount = norm_op_bid_Quantity,
                                status = "Sent",
                                bidType = "Demand",
                                node = self.node))
            
            #assuming bid2 is pos flexibility bid
            if pos_flex_bid_Quantity >= self.world.minBidEOM:
                bids.append(Bid(issuer = self,
                                ID = "{}_pos_flex_mrEOM".format(self.name),
                                price = pos_flex_bid_Price,
                                amount = pos_flex_bid_Quantity,
                                status = "Sent",
                                bidType = "Supply",
                                node = self.node))

            #assuming bid3 is neg flexibility bid
            if neg_flex_bid_Quantity >= self.world.minBidEOM:
                bids.append(Bid(issuer = self,
                                ID = "{}_neg_flex_mrEOM".format(self.name),
                                price = neg_flex_bid_Price,
                                amount = neg_flex_bid_Quantity,
                                status = "Sent",
                                bidType = "Demand",
                                node = self.node))

        return bids
    
    
    def calculateBidEOM(self, t):
        norm_op_bid_Quantity = self.dict_capacity_opt[t]
        
        pos_flex_bid_Quantity = self.dict_capacity_pos_flex[t]
        pos_flex_bid_Price = (norm_op_bid_Quantity -  pos_flex_bid_Quantity)*self.elec_price_signal[t]
        
        neg_flex_bid_Quantity = self.dict_capacity_neg_flex[t]
        neg_flex_bid_Price = (neg_flex_bid_Quantity - norm_op_bid_Quantity)*self.elec_price_signal[t]
        
        return  norm_op_bid_Quantity, pos_flex_bid_Quantity, pos_flex_bid_Price, neg_flex_bid_Quantity, neg_flex_bid_Price


    def calc_power_limits(self, time_horizon):
        liquid_steel_max = self.max_capacity/time_horizon
        liquid_steel_min = .25*liquid_steel_max
        
        dri_max = liquid_steel_max*self.mass_ratio_DRI
        dri_min = dri_max*.25
        
        iron_ore_max = dri_max*self.mass_ratio_iron
        iron_ore_min = iron_ore_max*.25
        
        EH_max = self.spec_elec_cons_EH*iron_ore_max
        EH_min = self.spec_elec_cons_EH*iron_ore_min
        
        DRP_max = self.spec_elec_cons_DRP*dri_max
        DRP_min = self.spec_elec_cons_DRP*dri_min
        
        AF_max = self.spec_elec_cons_AF*liquid_steel_max
        AF_min = self.spec_elec_cons_AF*liquid_steel_min
        
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
                  'Total_max': EH_max + DRP_max + AF_max,
                  'Total_min': EH_min + DRP_min + AF_min}

        return limits


    def process_opt(self,time_horizon, steel_prod, flexibility_params=None):

        model = pyo.ConcreteModel()    
        
        model.t = pyo.RangeSet(0, time_horizon)

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
            if t==1:
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
            if t == flexibility_params['hour_called']:
            #reduce consumption
                return model.elec_cons[t] == flexibility_params['cons_signal']
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
            return pyo.quicksum(model.liquid_steel[t] for t in model.t) >= steel_prod

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
        if flexibility_params is not None:
            model.elec_flex_rule = pyo.Constraint(model.t, rule = elec_flex_rule)
            
        model.obj = pyo.Objective(rule = cost_obj_rule, sense = pyo.minimize)

        return model
    
    def flexibility_available(self, time_horizon, model, elec_cons) :
        
        pos_flex_total = []
        neg_flex_total = []
            
        for i in range(1, time_horizon+1):
                     
        # potential to increase elec consumption from grid
          neg_flex_total.append(self.limits['Total_max'] - elec_cons[i-1])
          
         # potential to reduce elec consumption   
          pos_flex_total.append(elec_cons[i-1] - self.limits['AF_min'])
                       
                          
        return pos_flex_total, neg_flex_total
    
        
    def get_values(self,model,time_horizon):
        
        model_params = dict()
        
        time = []
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
    
        
        for i in range(1,time_horizon):
            time.append(i)
            
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
    
        
            model_params['time_step'] = time
            model_params['iron_ore'] = iron_ore
            model_params['dri_direct'] = dri_direct
            model_params['dri_to_storage'] = dri_to_storage
            model_params['dri_from_storage'] = dri_from_storage
            model_params['liquid_steel'] =liquid_steel
            model_params['elec_cons'] =elec_cons
            model_params['ng_cons'] = ng_cons
            model_params['coal_cons'] =coal_cons
            model_params['coal_cost'] = coal_cost
            model_params['EH_elec_cons'] = elec_cons_EH
            model_params['DRP_elec_cons'] = elec_cons_DRP
            model_params['AF_elec_cons'] = elec_cons_AF
            model_params['storage_status'] = storage_status
            model_params['storage'] = storage
                       
        return model_params
            
    
    

    
    
    
    
    
    
    
    
    
    