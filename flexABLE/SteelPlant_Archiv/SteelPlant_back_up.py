# -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 17:04:23 2020

@author: intgridnb-02
"""
from .auxFunc import initializer
from .bid import Bid
import pyomo.environ as pyo
from pyomo.opt import SolverFactory
import pandas as pd

class SteelPlant():
    

    @initializer
    def __init__(self,
                 agent = None,
                 maxPower = 400,
                 minPower = 50,
                 node = 'Bus_DE',
                 world = None,
                 requierdProduction = 24000,
                 minDowntime = 0,
                 minOperatingTime = 0,
                 rampUp = 400,
                 rampDown = 400,
                 technology = "industry",
                 **kwargs):

        # bid status parameters
        self.sentBids=[]

        self.dictCapacity = {n:None for n in self.world.snapshots}
        self.dictCapacity[self.world.snapshots[0]] = self.maxPower
        self.dictCapacity[-1] = self.maxPower

        self.dictCapacityMR = {n:(0,0) for n in self.world.snapshots}
        self.dictCapacityFlex = {n:(0,0) for n in self.world.snapshots}

        self.confQtyCRM_neg = {n:0 for n in self.world.snapshots}
        self.confQtyCRM_pos = {n:0 for n in self.world.snapshots}
        self.confEnCRM_neg = {n:0 for n in self.world.snapshots}
        self.confEnCRM_pos = {n:0 for n in self.world.snapshots}
        self.confQtyEOM = {n:0 for n in self.world.snapshots}
        self.confQtyCRM_neg_amount = {n:0 for n in self.world.snapshots}
        self.confQtyCRM_pos_amount = {n:0 for n in self.world.snapshots}

        self.dicPFC = self.world.PFC
        df_PFC = pd.DataFrame(self.dicPFC)
        df_PFC.to_csv(f'output/2016example/SteelPlant/PFC.csv', index=False)

        # df_PFC = pd.read_csv(f'input/2016/SteelPlant/PFC_EOM.csv',header=None,dtype=int)
        # self.dicPFC = df_PFC.iloc[:,0].values.tolist()
        # df_PFC.to_csv(f'output/2016example/SteelPlant/PFC.csv', index=False)

        # Unit status parameters
        self.meanMarketSuccess = 0
        self.marketSuccess = [0]
        self.currentDowntime = self.minDowntime # Keeps track of the powerplant if it reached the minimum shutdown time
        self.currentStatus = 0 # 0 means the power plant is currently off, 1 means it is on
        self.averageDownTime = [0] # average downtime during the simulation
        self.currentCapacity = 0
        self.sentBids=[]
        self.sentBids_dict = {}
        
        # additional parameters

        self.minDowntime /= self.world.dt          # This was added to consider dt 15 mins
        self.minOperatingTime /= self.world.dt     # This was added to consider dt 15 mins
        self.crmTime = int(4 / self.world.dt)
        self.foresight = int(self.minDowntime)

        self.CapacityOptimization = []
        self.CapacityOptimization_all = pd.DataFrame()
        self.segment = 24
        self.FlexNeg_total = []
        self.FlexPos_total = []

        
    def step(self):
        self.dictCapacity[self.world.currstep] = 0

        for bid in self.sentBids:
            if 'mrEOM' in bid.ID or 'flexEOM' in bid.ID:
                self.dictCapacity[self.world.currstep] += bid.confirmedAmount
                if 'mrEOM' in bid.ID:
                    self.dictCapacityMR[self.world.currstep] = (bid.confirmedAmount, bid.price)    
                else:
                    self.dictCapacityFlex[self.world.currstep] = (bid.confirmedAmount, bid.price)

            if "posCRMCall" in bid.ID:
                self.dictCapacity[self.world.currstep] += bid.confirmedAmount
            
            if "negCRMCall" in bid.ID:
                self.dictCapacity[self.world.currstep] -= bid.confirmedAmount

        #change crm capacity every 4 hours (CRM market clearing time)
        if self.world.currstep % self.crmTime:
            self.confQtyCRM_pos[self.world.currstep] = self.confQtyCRM_pos[self.world.currstep-1]
            self.confQtyCRM_neg[self.world.currstep] = self.confQtyCRM_neg[self.world.currstep-1]
            self.confEnCRM_neg[self.world.currstep] = self.confEnCRM_neg[self.world.currstep-1]
        
        self.sentBids_dict[self.world.currstep] = self.sentBids.copy()
        self.sentBids = []
        
        
    def feedback(self, bid):
    # confQtyCRM_### describes the accepted energy ("Call")
    # confQtyCRM_###_amount describes the accpeted capacity ("Demand")
        if bid.status == "Confirmed":
            if 'CRMPosDem' in bid.ID:
                self.confQtyCRM_pos.update({self.world.currstep+_:bid.confirmedAmount for _ in range(self.crmTime)})
                self.confQtyCRM_pos_amount.update({self.world.currstep+_:bid.amount for _ in range(self.crmTime)})
                
            if 'CRMNegDem' in bid.ID:
                self.confQtyCRM_neg.update({self.world.currstep+_:bid.confirmedAmount for _ in range(self.crmTime)})
                self.confQtyCRM_neg_amount.update({self.world.currstep+_:bid.amount for _ in range(self.crmTime)})

            if 'negCRMCall' in bid.ID:
                self.confEnCRM_neg.update({self.world.currstep+_:bid.confirmedAmount for _ in range(self.crmTime)})

            if 'EOM_DE' in bid.ID:
                self.confQtyEOM.update({self.world.currstep+_:bid.confirmedAmount for _ in range(self.crmTime)})
                
                
        elif bid.status =="PartiallyConfirmed":
            if 'CRMPosDem' in bid.ID:
                self.confQtyCRM_pos.update({self.world.currstep+_:bid.confirmedAmount for _ in range(self.crmTime)})
                self.confQtyCRM_pos_amount.update({self.world.currstep+_:bid.amount for _ in range(self.crmTime)})
                
            if 'CRMNegDem' in bid.ID:
                self.confQtyCRM_neg.update({self.world.currstep+_:bid.confirmedAmount for _ in range(self.crmTime)})
                self.confQtyCRM_neg_amount.update({self.world.currstep+_:bid.amount for _ in range(self.crmTime)})

            if 'negCRMCall' in bid.ID:
                self.confEnCRM_neg.update({self.world.currstep+_:bid.confirmedAmount for _ in range(self.crmTime)})

            if 'EOM_DE' in bid.ID:
                self.confQtyEOM.update({self.world.currstep+_:bid.confirmedAmount for _ in range(self.crmTime)})

        #self.write_to_db(self.world.currstep, bid)

        self.sentBids.append(bid)

    def write_to_db(self,t, bid):
        self.world.ResultsWriter.writeBid(self, t, bid)

    def requestBid(self, t, market):
        bids = []

        if market == "EOM":
            BidsDict, counter = self.calculateBidEOM(t)           
            if BidsDict['bidQuantity_plan'] != 0:
                bids.append(Bid(issuer = self,
                                ID = "{}_mrEOM".format(self.name),
                                price =  BidsDict['bidPrice_plan'],
                                amount = BidsDict['bidQuantity_plan'],
                                status = "Sent",
                                bidType = "Demand",
                                node = self.node))
                

            for i in range(1, counter):            
                if BidsDict[f'bidQuantity_FlexNeg_{i}'] != 0:
                    bids.append(Bid(issuer = self,
                                    ID = "{}_flexEOM".format(self.name),
                                    price =  BidsDict[f'bidPrice_FlexNeg_{i}'],
                                    amount = BidsDict[f'bidQuantity_FlexNeg_{i}'],
                                    status = "Sent",
                                    bidType = "Demand",
                                    node = self.node))
        
        elif market=="negCRMDemand":
            bids.extend(self.calculatingBidsSP_CRM_neg(t))

        elif market=="negCRMCall":
            bids.extend(self.calculatingBidsSP_CRM_neg_energy(t)) 

        elif market=="posCRMDemand":
            bids.extend(self.calculatingBidsSP_CRM_pos(t))

        elif market=="posCRMCall":
            bids.extend(self.calculatingBidsSP_CRM_pos_energy(t)) 
                
        return bids
    

    def calculatingBidsSP_CRM_neg(self, t):
        # SP_CRM_neg means that the production of the SteelPlant increases (Higher Production (pos) --> more Energy for the grid (neg))
        bidsCRM = []
        OptSegment = t // self.segment

        # calc available flex and opt production plan
        self.FlexNeg_total, self.FlexPos_total = self.calc_flex_CRMP(t = t, flex = "neg")

        # calc availabe amount (increasing prod --> neg flex)
        if ((self.currentStatus) or (not(self.currentStatus) and (self.currentDowntime >= self.minDowntime))):
            bidQtyCRM_neg = min(self.maxPower - max([self.CapacityOptimization[i] for i in range (t - (OptSegment * self.segment), t - (OptSegment * self.segment) + self.crmTime)]), self.rampUp)

        else:
            bidQtyCRM_neg = 0
      
        # calc prices and formulate bids    

        if bidQtyCRM_neg > self.world.minBidCRM:
            
            # Dieser block muss überarbeitet werden --> evtl. gesplittete Gebote
            if self.FlexPos_total.empty:
                bidQtyCRM_neg = 0

            # capcityPrice = 0 
            capacityPrice = 0.00      

            bidsCRM.append(Bid(issuer=self,
                    ID = "Bu{}t{}_CRMNegDem".format(self.name,t),
                    price = capacityPrice,
                    amount = bidQtyCRM_neg, 
                    status = "Sent",
                    bidType = "Supply",
                    node = self.node))
        else:
            bidsCRM.append(Bid(issuer=self,
                               ID = "Bu{}t{}_CRMNegDem".format(self.name,t),
                               price = 0,
                               amount = 0,
                               status = "Sent",
                               bidType = "Supply",
                               node = self.node))

        return bidsCRM
    

    def calculatingBidsSP_CRM_neg_energy(self, t):
        bidsCRM = []
        OptSegment = t // self.segment

        Ergebnis_CRM_neg_capacity = self.confQtyCRM_neg[t]
        self.world.minBidCRM_energy = self.world.minBidCRM

        # calc available flex and opt production plan
        self.FlexNeg_total, self.FlexPos_total = self.calc_flex_CRME(t = t)

        # calc availabe amount (increasing prod --> neg flex)
        if Ergebnis_CRM_neg_capacity:
            bidQtyCRM_neg = Ergebnis_CRM_neg_capacity
        else:
            if ((self.currentStatus) or (not(self.currentStatus) and (self.currentDowntime >= self.minDowntime))):
                bidQtyCRM_neg = min(self.maxPower - max([self.CapacityOptimization[i] for i in range (t - (OptSegment * self.segment), t - (OptSegment * self.segment) + self.crmTime)]), self.rampUp)

            else:
                bidQtyCRM_neg = 0
      
        # calc prices and formulate bids    

        if bidQtyCRM_neg > self.world.minBidCRM_energy:
            
             # Calculate energy Price
                # opportunity cost: If i higher my production, the cost which this generates must be equal or lower 
                # as the costs which i can safe through reducing my production at another timestep (FlexPos_total)
            # Dieser block muss überarbeitet werden --> evtl. gesplittete Gebote
            if self.FlexPos_total.empty:
                bidQtyCRM_neg = 0
                opportunity_cost = 0
            else:
                opportunity_cost = self.calc_opportunity_costs(t = t, bid = bidQtyCRM_neg,Flex_total = self.FlexPos_total,Flextype="neg")

            energyPrice = opportunity_cost            

            bidsCRM.append(Bid(issuer=self,
                    ID = "Bu{}t{}_CRMNegCall".format(self.name,t),
                    amount = bidQtyCRM_neg, 
                    energyPrice = energyPrice,
                    status = "Sent",
                    bidType = "Supply",
                    node = self.node))
        else:
            bidsCRM.append(Bid(issuer=self,
                               ID = "Bu{}t{}_CRMNegCall".format(self.name,t),
                               amount = 0,
                               energyPrice = 0,
                               status = "Sent",
                               bidType = "Supply",
                               node = self.node))

        return bidsCRM       


    def calculatingBidsSP_CRM_pos(self, t):
        # SP_CRM_pos means that the production of the SteelPlant decreas (decrease Production (neg) --> more Energy for the grid (pos))
        bidsCRM = []
        OptSegment = t // self.segment

        # calc available flex and opt production plan
        self.FlexNeg_total, self.FlexPos_total = self.calc_flex_CRMP(t = t, flex = "pos")

        # calc availabe amount (increasing prod --> neg flex)
        if ((self.currentStatus) or (not(self.currentStatus) and (self.currentDowntime >= self.minDowntime))):
            bidQtyCRM_pos = min(min([self.CapacityOptimization[i] for i in range (t - (OptSegment * self.segment), t - (OptSegment * self.segment) + self.crmTime)]) - self.minPower, self.rampDown)

        else:
            bidQtyCRM_pos = 0
      
        # calc prices and formulate bids    

        if bidQtyCRM_pos > self.world.minBidCRM:
            
            # Dieser block muss überarbeitet werden --> evtl. gesplittete Gebote
            if self.FlexPos_total.empty:
                bidQtyCRM_pos = 0

            # capcityPrice = 0 
            capacityPrice = 0.00      

            bidsCRM.append(Bid(issuer=self,
                    ID = "Bu{}t{}_CRMNegDem".format(self.name,t),
                    price = capacityPrice,
                    amount = bidQtyCRM_pos, 
                    status = "Sent",
                    bidType = "Supply",
                    node = self.node))
        else:
            bidsCRM.append(Bid(issuer=self,
                               ID = "Bu{}t{}_CRMNegDem".format(self.name,t),
                               price = 0,
                               amount = 0,
                               status = "Sent",
                               bidType = "Supply",
                               node = self.node))

        return bidsCRM


    def calculatingBidsSP_CRM_pos_energy(self, t):
        bidsCRM = []
        OptSegment = t // self.segment

        Ergebnis_CRM_pos_capacity = self.confQtyCRM_pos[t]
        self.world.minBidCRM_energy = self.world.minBidCRM

        # calc available flex and opt production plan
        self.FlexNeg_total, self.FlexPos_total = self.calc_flex_CRME(t = t)

        # calc availabe amount (increasing prod --> neg flex)
        if Ergebnis_CRM_pos_capacity:
            bidQtyCRM_pos = Ergebnis_CRM_pos_capacity
        else:
            if ((self.currentStatus) or (not(self.currentStatus) and (self.currentDowntime >= self.minDowntime))):
                bidQtyCRM_pos = min(self.maxPower - max([self.CapacityOptimization[i] for i in range (t - (OptSegment * self.segment), t - (OptSegment * self.segment) + self.crmTime)]), self.rampUp)

            else:
                bidQtyCRM_pos = 0
      
        # calc prices and formulate bids    
        
        if bidQtyCRM_pos > self.world.minBidCRM_energy:
            
             # Calculate energy Price
                # opportunity cost: If i higher my production, the cost which this generates must be equal or lower 
                # as the costs which i can safe through reducing my production at another timestep (FlexPos_total)

            # Dieser block muss überarbeitet werden --> evtl. gesplittete Gebote
            if self.FlexPos_total.empty:
                bidQtyCRM_pos = 0
                opportunity_cost = 0
            else:
                # opportunity costs müssen überarbeitet werden
                opportunity_cost = self.calc_opportunity_costs(t = t, bid = bidQtyCRM_pos,Flex_total = self.FlexNeg_total, Flextype="pos")

            energyPrice = opportunity_cost            

            bidsCRM.append(Bid(issuer=self,
                    ID = "Bu{}t{}_CRMPosCall".format(self.name,t),
                    amount = bidQtyCRM_pos, 
                    energyPrice = energyPrice,
                    status = "Sent",
                    bidType = "Supply",
                    node = self.node))
        else:
            bidsCRM.append(Bid(issuer=self,
                               ID = "Bu{}t{}_CRMPosCall".format(self.name,t),
                               amount = 0,
                               energyPrice = 0,
                               status = "Sent",
                               bidType = "Supply",
                               node = self.node))

        return bidsCRM    


    def calculateBidEOM(self, t):
        BidsEOM = {}
        
        OptSegment = t // self.segment
     
        # calculate flex
        self.FlexNeg_total, self.FlexPos_total = self.calc_flex_EOM(t = t, CRM = True)

        # planed production
        BidsEOM['bidQuantity_plan'] = self.CapacityOptimization[t - (OptSegment * self.segment)]
        BidsEOM['bidPrice_plan'] = 3000 # forecast wird erwartet, deswegen wird teuer in den Markt geboten

        # neg flex bids (increasing production)
        FlexNeg = self.maxPower - BidsEOM['bidQuantity_plan']
        counter = 0

        if self.FlexPos_total.empty:
                BidsEOM[f'bidQuantity_FlexNeg_{counter}'] = 0
                BidsEOM[f'bidPrice_FlexNeg_{counter}'] = 0
        else:
            for index, row in self.FlexPos_total.iterrows():
                counter += 1
                if FlexNeg <= 0:
                    break
                if row['Amount'] <= FlexNeg:
                    BidsEOM[f'bidQuantity_FlexNeg_{counter}'] = row['Amount']
                    BidsEOM[f'bidPrice_FlexNeg_{counter}'] = row['Costs']
                    FlexNeg -= row['Amount']
                else:
                    BidsEOM[f'bidQuantity_FlexNeg_{counter}'] = FlexNeg
                    BidsEOM[f'bidPrice_FlexNeg_{counter}'] = row['Costs']
                    FlexNeg = 0
            
        # for analysis porpuse

        df = pd.DataFrame({f'prod_opt_{OptSegment}': self.CapacityOptimization})
        df.to_csv(f'output/2016example/SteelPlant/prod_opt_{OptSegment}.csv', index=False)
        
        return BidsEOM, counter


    def checkAvailability(self, t):
        pass


    def cost_opt_base(self,
                      start = None,
                      OptimizationHorizon = None,
                      importCRM = None
                      ):

        print(start, "Optimization")
        print("SteelPlant.py wird genutzt")

        if OptimizationHorizon is None: 
            OptimizationHorizon = len(self.world.snapshots) - 1
        
        if start is None:
            start = 0

        

        restProduction = self.requierdProduction - sum(list(self.dictCapacity.values())[0:start])

        solver = pyo.SolverFactory('glpk')
        
        PFC_EOM = self.dicPFC
        
        # create model
        model = pyo.ConcreteModel()
        
        # set horizon
        model.t = pyo.RangeSet(start, OptimizationHorizon)
        
        #set variables
        model.product = pyo.Var(model.t, domain = pyo.NonNegativeReals)
        
        #set objective
        def cost_obj_rule(model):
            return pyo.quicksum((model.product[t]*PFC_EOM[t]) for t in model.t)
        
        model.obj = pyo.Objective(rule = cost_obj_rule, sense = pyo.minimize)
        
        #set constraints
        def product_max_rule(model,t):
            return model.product[t] <= self.maxPower 
        def product_min_rule(model,t):
            return model.product[t] >= self.minPower
        def product_total_rule(model,t):
            return pyo.quicksum(model.product[t] for t in model.t) >= restProduction
        

        def product_max_rule(model,t):
            if start % self.crmTime != 0 and importCRM:
                time = start % self.crmTime
                if t in range(start, start + time):
                    return model.product[t] <= self.maxPower - self.confQtyCRM_neg_amount[start] 
                else:
                    return model.product[t] <= self.maxPower 
            else:
                return model.product[t] <= self.maxPower 
        
        model.production_total_rule = pyo.Constraint(model.t, rule=product_total_rule)
        model.production_max_rule = pyo.Constraint(model.t, rule=product_max_rule)
        model.production_min_rule = pyo.Constraint(model.t, rule=product_min_rule)
        
        #solve model
        solver.solve(model)
        
        prod_base = []
        
        for i in range (start, OptimizationHorizon+1):
            prod_base.append(model.product[i].value)
            
        return prod_base
    

    def called_flex(self, FlexCalled, Flex_total):
        for index, row in Flex_total.iterrows():
            if FlexCalled <= 0:
                break
            if row['Amount'] <= FlexCalled:
                FlexCalled -= row['Amount']
                row['Amount'] = 0
                Flex_total = Flex_total.drop(index)
            else:
                row['Amount'] -= FlexCalled
                FlexCalled = 0
            
        return Flex_total
    

    def calc_flex_base(self, t):
        # opt schedule
        self.CapacityOptimization = self.cost_opt_base(start = t, importCRM = True)

        # alle optimization steps in einem dataframe
        OptSegement = t // self.segment

        x = self.CapacityOptimization
        print(x)
        print("SteelPlant.py")
        if self.CapacityOptimization_all.empty:
            self.CapacityOptimization_all[OptSegement] = x
        else:
            additional_zeros = len(self.CapacityOptimization_all[0]) - len(x)
            x = [None] * additional_zeros + x
            self.CapacityOptimization_all[OptSegement] = x

        

        print(self.CapacityOptimization_all)

        # calculate flexibilty
        # calculation of flexibility for future production, production in segment ist not considerd

        PFC_EOM = self.dicPFC

        neg_flex = pd.DataFrame(columns=['Amount','Costs']) # increase production
        pos_flex = pd.DataFrame(columns=['Amount','Costs']) # reduce production

        for i in range(t + self.segment,len(self.world.snapshots)):

            neg_flex_t = self.maxPower 
            neg_flex_t_c = PFC_EOM[i]

            pos_flex_t = self.CapacityOptimization[i-t] - self.minPower
            pos_flex_t_c = PFC_EOM[i]

            neg_flex.loc[i] = [neg_flex_t, neg_flex_t_c]
            pos_flex.loc[i] = [pos_flex_t, pos_flex_t_c]
                
        # drop all amounts == 0, später evtl. nicht mehr nötig, wenn ich eine Schleife in calc max_prod_segment habe
        neg_flex = neg_flex.drop(neg_flex[neg_flex['Amount']==0].index)
        pos_flex = pos_flex.drop(pos_flex[pos_flex['Amount']==0].index)

        self.FlexNeg_total = neg_flex.groupby('Costs', as_index=False)['Amount'].sum()
        self.FlexPos_total = pos_flex.groupby('Costs', as_index=False,)['Amount'].sum()

        self.FlexPos_total = self.FlexPos_total.sort_values('Costs',ascending= False)
        self.FlexPos_total = self.FlexPos_total.reset_index(drop=True)
        
        return self.FlexNeg_total, self.FlexPos_total


    def calc_flex_CRMP(self, t, flex):
        if t % self.segment == 0:
            if flex == "pos":
                self.FlexNeg_total, self.FlexPos_total = self.calc_flex_base(t)
        else:
            if self.confEnCRM_neg[t-1] and flex == "neg":
                Flex_called_before = self.confEnCRM_neg[t-1]
                self.FlexPos_total = self.called_flex(FlexCalled = Flex_called_before, Flex_total = self.FlexPos_total)
            if self.confEnCRM_pos[t-1] and flex == "pos":
                Flex_called_before = self.confEnCRM_pos[t-1]
                self.FlexNeg_total = self.called_flex(FlexCalled = Flex_called_before, Flex_total = self.FlexNeg_total)
        # Problem: Wie behandele ich zurückgehalten Kapazität, rechne ich sie aus der Flex Liste raus? Dann muss sie aber vorm CRME wieder eingerechnet werden?
        
        return self.FlexNeg_total, self.FlexPos_total


    def calc_flex_EOM(self, t, CRM = True):
        OptSegment = t // self.segment

        if CRM:
            if t % self.crmTime != 0:
                if t % self.segment == 0:
                    self.FlexNeg_total, self.FlexPos_total = self.calc_flex_base(t)
                else:
                    if self.confEnCRM_neg[t-1]:
                        Flex_called_before = self.confEnCRM_neg[t-1]
                        self.FlexPos_total = self.called_flex(FlexCalled = Flex_called_before, Flex_total = self.FlexPos_total)
                    if self.confEnCRM_pos[t-1]:
                        Flex_called_before = self.confEnCRM_pos[t-1]
                        self.FlexNeg_total = self.called_flex(FlexCalled = Flex_called_before, Flex_total = self.FlexNeg_total)
        else:
            if t % self.segment == 0:
                self.FlexNeg_total, self.FlexPos_total = self.calc_flex_base()
            else:
                # only negative flex can be called
                Flex_called_before = (self.dictCapacity[t-1] - self.CapacityOptimization[t - (OptSegment * self.segment)-1])
                self.FlexPos_total = self.called_flex(FlexCalled = Flex_called_before, Flex_total = self.FlexPos_total)
        
        return self.FlexNeg_total, self.FlexPos_total


    def calc_flex_CRME(self, t):
        OptSegment = t // self.segment

        # pnle negative flax can be called at EOM
        Flex_called_before = self.confQtyEOM[t] - self.CapacityOptimization[t - (OptSegment * self.segment)]
        self.FlexPos_total = self.called_flex(FlexCalled = Flex_called_before, Flex_total = self.FlexPos_total)

        return self.FlexNeg_total, self.FlexPos_total


    def calc_opportunity_costs(self, t, bid,Flex_total, Flextype):
        # bid = bidQtyCRM_pos or bidQtyCRM_neg 
        Flex_total_temp = Flex_total.copy()
        OptSegment = t // self.segment
        PFC_EOM = self.dicPFC
        

        cost_change = 0
        for i in range(t - (OptSegment * self.segment), t - (OptSegment * self.segment) + self.crmTime):
            cost_change += bid * PFC_EOM[i]

        amount_add = self.crmTime * bid
        cost_replacement = 0
        for index, row in Flex_total_temp.iterrows():
                if amount_add <= 0:
                    break
                if row['Amount'] <= amount_add:
                    cost_replacement += row['Costs'] * row['Amount']
                    amount_add -= row['Amount']
                    row['Amount'] = 0
                    Flex_total_temp = Flex_total_temp.drop(index)
                else:
                    cost_replacement += row['Costs'] * amount_add
                    row['Amount'] -= amount_add
                    amount_add = 0

        if Flextype == "neg":
            cost_add = cost_change
            cost_safes = cost_replacement
            opportunity_costs = (cost_add - cost_safes)/(self.crmTime * bid)
        else:
            cost_add = cost_replacement
            cost_safes = cost_change
            opportunity_costs = (cost_add - cost_safes)/(self.crmTime * bid)
        
        return opportunity_costs
    
    
    

