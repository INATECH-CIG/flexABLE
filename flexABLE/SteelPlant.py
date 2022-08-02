# -*- coding: utf-8 -*-
"""
Created on 18 July 2022

@author: Louis

"""
from tracemalloc import Snapshot
from auxFunc import initializer
from bid import Bid
import pyomo.environ as pyo
from pyomo.opt import SolverFactory

class SteelPlant():
    
    @initializer
    def __init__(self,
                 agent = None,
                 name = 'KKW ISAR 2',
                 technology = 'Steel_Plant',
                 max_capacity = 1500,
                 min_production = 0,
                 profit_margin = 0.,
                 optimization_horizon = 24,
                 node = 'Bus_DE',
                 world = None):
        
        # bids status parameters
        snapshots = range(100)
        self.dictCapacity = {n:None for n in snapshots}

        self.dict_capacity_opt = {n:(0,0) for n in snapshots}
        self.dict_capacity_neg_flex = {n:(0,0) for n in snapshots}
        self.dict_capacity_pos_flex = {n:(0,0) for n in snapshots}

        # Unit status parameters
        self.sentBids=[]

        self.spec_elec_cons = {'electric_heater': .37,
                               'iron_reduction': .127,
                               'arc_furnace': .575}

        self.spec_ng_cons = {'iron_reduction': 1.56,
                             'arc_furnace': .216}

        self.spec_coal_cons = {'arc_furnace': .028}

        self.iron_mass_ratio = {'iron': 1.66,
                                'DRI': 1.03,
                                'liquid_steel': 1}

        self.limits = self.calc_power_limits()
        self.solver = pyo.SolverFactory('glpk') 
        
        #eventually replace with something similar to average price in storage agents
        self.elec_price = np.array(input_data['electricity_price']) 
        
    def step(self):
        self.dictCapacity[self.world.currstep] = 0
        
        for bid in self.sentBids:
            self.dictCapacity[self.world.currstep] += bid.confirmedAmount
            if 'mrEOM' in bid.ID:
                self.dictCapacityMR[self.world.currstep] = (bid.confirmedAmount, bid.price)
                
            else:
                self.dictCapacityFlex[self.world.currstep] = (bid.confirmedAmount, bid.price)
                
        self.sentBids=[]
        
        
    def feedback(self, bid):
        self.sentBids.append(bid)
        
        
    def requestBid(self, t, market):
        bids=[]
        bid1, bid2, bid3 = self.calculateBidEOM(t)
        
        #create three bids
        if market=="EOM":
            bids.append(Bid(issuer = self,
                            ID = "{}_norm_op_mrEOM".format(self.name),
                            price = norm_op_bid_Quantity,
                            amount = norm_op_bid_Price,
                            status = "Sent",
                            bidType = "Demand",
                            node = self.node))
            
            #assuming bid2 is pos flexibility bid
            bids.append(Bid(issuer = self,
                            ID = "{}_pos_flex_mrEOM".format(self.name),
                            price = pos_flex_bid_Quantity,
                            amount = pos_flex_bid_Price,
                            status = "Sent",
                            bidType = "Supply",
                            node = self.node))

            #assuming bid3 is neg flexibility bid
            bids.append(Bid(issuer = self,
                            ID = "{}_neg_flex_mrEOM".format(self.name),
                            price = neg_flex_bid_Quantity,
                            amount = neg_flex_bid_Price,
                            status = "Sent",
                            bidType = "Demand",
                            node = self.node))

        return bids
    
    
    def calculateBidEOM(self, t):
        #needs to formulate bid quantity and bid price, it can also be several bids
        
        #varaible to keep track of steel produciton
        self.total_liquid_steel_produced =0
        
        norm_op_bid_Quantity, norm_op_bid_Price, pos_flex_bid_Quantity, pos_flex_bid_Price, \
            neg_flex_bid_Quantity, neg_flex_bid_Price = 0,0,0,0,0,0,0
        
        if t == 0:
            
            #Assumed base_model_params are avaialbe for base scenario...normal time horizon, no flexibility           
            
            #Bid_1 - Normal Operation
            norm_op_bid_Quantity = self.base_model_params['elec_cons'][self.optimization_horizon]
            norm_op_bid_Price = norm_op_bid_Quantity * self.elec_price[t]
            
            #Bid 2 - Pos Flex
            pos_flex_bid_Quantity = self.base_model_params['elec_cons'][t] - self.pos_flex_total[t]
            pos_flex_bid_Price =  (norm_op_bid_Quantity-pos_flex_bid_Quantity) * self.elec_price[t]
            
            #Bid 3 - Neg Flex
            neg_flex_bid_Quantity = self.base_model_params['elec_cons'][t] + self.neg_flex_total[t]
            neg_flex_bid_Price =  (norm_op_bid_Quantity + neg_flex_bid_Quantity) * self.elec_price[t]
            
        
        if t > 0:
            #acces which bid was succesful in previous time step and decide if production needs to be adjusted
                        
            if 'norm_op_mrEOM' in bid.ID:
                
                #reduce optimization horizon to reflect time steps remaining
                self.optimization_horizon -= 1
            
                #Save how much steel was produced in previous time step 
                self.total_liquid_steel_produced += self.base_model_params['liquid_steel'][t-1]
                
                #Bid_1 - Normal Operation
                norm_op_bid_Quantity = self.base_model_params['elec_cons'][t]
                norm_op_bid_Price = norm_op_bid_Quantity * self.elec_price[t]
                
                #Bid 2 - Pos Flex
                pos_flex_bid_Quantity = self.base_model_params['elec_cons'][t] - self.pos_flex_total[t]
                pos_flex_bid_Price =  (norm_op_bid_Quantity-pos_flex_bid_Quantity) * self.elec_price[t]  #make cost the profit lost by not following optimal operation
                
                #Bid 3 - Neg Flex
                neg_flex_bid_Quantity = self.base_model_params['elec_cons'][t] + self.neg_flex_total[t]
                neg_flex_bid_Price =  (norm_op_bid_Quantity + neg_flex_bid_Quantity) * self.elec_price[t]                
                                
               
            
            if 'pos_flex_mrEOM' in bid.ID:
                
                #determine liquid steel produced at previous timestep when pos flex called                
                self.flexibility = {'hour_called': t-1,
                                    'cons_signal':pos_flex_bid_Quantity,
                                    'type': 'pos'}
                
                self.flex_case = self.Price_Opt(
                                       steel_prod=self.steel_prod,
                                       optimization_horizon=self.optimization_horizon,
                                       flexibility_params=None)
                
                self.total_liquid_steel_produced += self.flex_case['elec_cons'][t-1]
                
                
                #subtract already produced steel from target produciton amount 
                self.steel_prod = self.steel_prod - self.total_liquid_steel_produced
               
                #reduce optimization horizon to reflect time steps remaining
                self.optimization_horizon -= 1
                
                #solve production for new steel target and new time horizon
                self.base_model = self.Price_Opt(
                                       steel_prod=self.steel_prod,
                                       optimization_horizon=self.optimization_horizon,
                                       flexibility_params=None)
                
                #determine new pos and neg flex avaialble 
                self.pos_flex_total, self.neg_flex_total = self.flexibility_available(self, self.model) 
                
                
                #determine new bids
                #Bid_1 - Normal Operation
                norm_op_bid_Quantity = self.base_model_params['elec_cons'][0]
                norm_op_bid_Price = norm_op_bid_Quantity * self.elec_price[t]
                
                #Bid 2 - Pos Flex
                pos_flex_bid_Quantity = self.base_model_params['elec_cons'][0] - self.pos_flex_total[0]
                pos_flex_bid_Price =  (norm_op_bid_Quantity-pos_flex_bid_Quantity) * self.elec_price[t]  #make cost the profit lost by not following optimal operation
                
                #Bid 3 - Neg Flex
                neg_flex_bid_Quantity = self.base_model_params['elec_cons'][0] + self.neg_flex_total[0]
                neg_flex_bid_Price =  (norm_op_bid_Quantity + neg_flex_bid_Quantity) * self.elec_price[t]   
            

              
            if 'neg_flex_mrEOM' in bid.ID:
                
                #determine liquid steel produced at previous timestep when pos flex called                
                self.flexibility = {'hour_called': t-1,
                                    'cons_signal':neg_flex_bid_Quantity,
                                    'type': 'neg'}
                
                self.flex_case = self.Price_Opt(
                                       steel_prod=self.steel_prod,
                                       optimization_horizon=self.optimization_horizon,
                                       flexibility_params=None)
                
                self.total_liquid_steel_produced += self.flex_case['elec_cons'][t-1]
                
                
                #subtract already produced steel from target produciton amount 
                self.steel_prod = self.steel_prod - self.total_liquid_steel_produced
               
                #reduce optimization horizon to reflect time steps remaining
                self.optimization_horizon -= 1
                
                #solve production for new steel target and new time horizon
                self.base_model = self.Price_Opt(
                                       steel_prod=self.steel_prod,
                                       optimization_horizon=self.optimization_horizon,
                                       flexibility_params=None)
                
                #determine new pos and neg flex avaialble 
                self.pos_flex_total, self.neg_flex_total = self.flexibility_available(self, self.model) 
                
                
                #determine new bids
                #Bid_1 - Normal Operation
                norm_op_bid_Quantity = self.base_model_params['elec_cons'][0]
                norm_op_bid_Price = norm_op_bid_Quantity * self.elec_price[t]
                
                #Bid 2 - Pos Flex
                pos_flex_bid_Quantity = self.base_model_params['elec_cons'][0] - self.pos_flex_total[0]
                pos_flex_bid_Price =  (norm_op_bid_Quantity-pos_flex_bid_Quantity) * self.elec_price[t]  #make cost the profit lost by not following optimal operation
                
                #Bid 3 - Neg Flex
                neg_flex_bid_Quantity = self.base_model_params['elec_cons'][0] + self.neg_flex_total[0]
                neg_flex_bid_Price =  (norm_op_bid_Quantity + neg_flex_bid_Quantity) * self.elec_price[t]      
                
                
                
        return  (norm_op_bid_Quantity, norm_op_bid_Price,pos_flex_bid_Quantity, pos_flex_bid_Price ,neg_flex_bid_Quantity, neg_flex_bid_Price)




    def calc_power_limits(self):


        liquid_steel_max = self.max_capacity/self.optimization_horizon
        liquid_steel_min = .25*liquid_steel_max
        
        dri_max = liquid_steel_max*self.iron_mass_ratio['DRI']
        dri_min = dri_max*.25
        
        iron_ore_max = dri_max*self.iron_mass_ratio['iron']
        iron_ore_min = iron_ore_max*.25
        
        EH_max = self.spec_elec_cons['electric_heater']*iron_ore_max
        EH_min = self.spec_elec_cons['electric_heater']*iron_ore_min
        
        DRP_max = self.spec_elec_cons['iron_reduction']*dri_max
        DRP_min = self.spec_elec_cons['iron_reduction']*dri_min
        
        AF_max = self.spec_elec_cons['arc_furnace']*liquid_steel_max
        AF_min = self.spec_elec_cons['arc_furnace']*liquid_steel_min
        
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


    def process_opt(self, flexibility_params=None,):

        model = pyo.ConcreteModel()    
        
        model.t = pyo.RangeSet(1, self.optimization_horizon)

                
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
            return model.liquid_steel[t] == (model.dri_direct[t] + model.dri_from_storage[t]*0.95) / self.iron_mass_ratio['DRI']

        #represents the direct reduction plant
        def iron_reduction_rule(model, t):
            return model.dri_direct[t] + model.dri_to_storage[t] == model.iron_ore[t] / self.iron_mass_ratio['iron']

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
            return model.elec_cons[t] == self.spec_elec_cons['electric_heater']*model.iron_ore[t] + \
                self.spec_elec_cons['iron_reduction']*(model.dri_direct[t] + model.dri_from_storage[t]) + \
                self.spec_elec_cons['arc_furnace']*model.liquid_steel[t]

        #total electricity cost
        def elec_cost_rule(model, t):
            return model.elec_cost[t] == self.input_data['electricity_price'].iat[t]*model.elec_cons[t]
        
    # =============================================================================
    #     #flexibility rule
        def elec_flex_rule(model, t):
            if t == flexibility_params['hour_called']:
            #reduce consumption
                if flexibility_params['type'] == 'pos':
                    return model.elec_cons[t] <= flexibility_params['cons_signal']
                else:
                    return model.elec_cons[t] >= flexibility_params['cons_signal']
            else:
                return model.elec_cons[t] >= 0
    #         
    # =============================================================================
            
        #total NG consumption
        def ng_consumption_rule(model,t):
            return model.ng_cons[t] == self.spec_ng_cons['iron_reduction']*(model.dri_direct[t] + model.dri_from_storage[t]) + \
                self.spec_ng_cons['arc_furnace']*model.liquid_steel[t] 
        
        #total NG cost
        def ng_cost_rule(model,t):
            return model.ng_cost[t] == self.fuel_data['natural gas'].iat[t]*model.ng_cons[t]
        
        #total coal consumption
        def coal_consumption_rule(model, t):
            return model.coal_cons[t] == self.spec_coal_cons['arc_furnace']*model.liquid_steel[t]
        
        #total coal cost
        def coal_cost_rule(model,t):
            return model.coal_cost[t] == self.fuel_data['hard coal'].iat[t]*model.coal_cons[t]

        def total_steel_prod_rule(model):
            return pyo.quicksum(model.liquid_steel[t] for t in model.t) >= self.steel_prod

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
    
    def flexibility_available(self, model) :
        
        self.pos_flex_total = []
        self.neg_flex_total = []
            
        for i in range(1, self.optimization_horizon+1):
                     
        # potential to increase elec consumption from grid
          self.neg_flex_total.append(self.limits['Total_max'] - self.elec_cons[i-1])
          
         # potential to reduce elec consumption   
          self.pos_flex_total.append(self.elec_cons[i-1] - self.limits['AF_min'])
                       
                          
        return self.pos_flex_total, self.neg_flex_total
    
    
    
    
    
    
    
    
    
    
    
    