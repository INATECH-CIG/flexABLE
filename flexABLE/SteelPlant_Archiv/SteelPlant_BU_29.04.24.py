# -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 17:04:23 2020

@author: intgridnb-02
"""
from .auxFunc import initializer
from .bid import Bid
import pandas as pd
from .steelPlantOptimization import steelOptBase
from .productionGoalOptimization import prodGoalOpt

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
        
        # get necessary functions
        self.steelOptBase = steelOptBase
        self.prodGoalOpt = prodGoalOpt

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

        self.CapacityOptimization = pd.DataFrame()
        self.CapacityOptimization_all = pd.DataFrame()
        self.segment = 96 # Describes the length of a segment for detail optimization
        self.segmentFlex = self.segment * 2 # Describes the length of a segment for the flex switch
        self.section = 32 # Describes the length of a section for the production goal optimization (non detailed)
        self.Tprevious = 24
        self.yearlyProductionGoal = 100000

        self.resultsSegment = pd.DataFrame()
        self.resultsSegment_all = pd.DataFrame()
        self.previousSegment = pd.DataFrame()
        self.productionGoalSegment = []

        self.shutDownCost = 1000000



        
    def step(self):
        self.dictCapacity[self.world.currstep] = 0
        
        for bid in self.sentBids:
            if 'supplyEOM' in bid.ID in bid.ID:
                self.dictCapacity[self.world.currstep] -= bid.confirmedAmount
                
            if 'demandEOM' in bid.ID:
                self.dictCapacity[self.world.currstep] += bid.confirmedAmount
        
        
        for bid in self.sentBids:
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
                if self.confQtyEOM[self.world.currstep] != self.resultsSegment_all.iloc[self.world.currstep]["production"]:
                    self.resultsSegment_all.iloc[self.world.currstep:self.world.currstep+timestampsSectionFlex+1] = SectionModelFlex[0][-timestampsSectionFlex:].reset_index(drop=True)

                
                
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
                self.confQtyEOM.update({self.world.currstep+_:bid.confirmedAmount for _ in range(self.Time)})


        #self.write_to_db(self.world.currstep, bid)

        self.sentBids.append(bid)

    def write_to_db(self,t, bid):
        self.world.ResultsWriter.writeBid(self, t, bid)

    def requestBid(self, t, market):
        bids = []

        if market == "EOM":
            BidsDict = self.calculateBidEOM(t)           
            # if BidsDict['bidQuantity_plan'] != 0:
            bids.append(Bid(issuer = self,
                            ID = "{}_demandEOM".format(self.name),
                            price =  BidsDict['bidPrice_plan'],
                            amount = BidsDict['bidQuantity_plan'],
                            status = "Sent",
                            bidType = "Demand",
                            node = self.node))

     

            bids.append(Bid(issuer = self,
                            ID = "{}_supplyEOM".format(self.name),
                            price = BidsDict['bidPrice_flex'],
                            amount = BidsDict['bidQuantity_flex'],
                            status = "Sent",
                            bidType = "Supply",
                            node = self.node))
        

        return bids
    


    

    # def calcPrevSegment(self, t):
    #     # check if previous segment scheduled as planed
    #     previousProduction = []
    #     previousSegment = pd.DataFrame()
    #     for i in range(0,self.segment):
    #         previousProduction.append(self.dictCapacity[t-(self.segment-i)])
    #         if self.resultsSegment["production"].equals(pd.Series(previousProduction)):
    #             print("production as planed")
    #             previousSegment = 



    #     return previousSegment
    

    def calculateBaseline(self, t):
        print("Optimiere Baseline für Segment: ", t//self.segment)
        #calculate the baseline based on the PFC for given length of segment
        OptSegment = t // self.segment
        
        if t == 0:
                # set parameter and determine production goal
                self.previousSegment = pd.DataFrame()
                Tprevious = 0
                SOCStart = 0
                # calulate production for every segment
                # 1. calculate max production of one segment
                maxProdSegmentModel = self.steelOptBase(
                    optHorizon = self.segment, 
                    timestampsPreviousSection = Tprevious, 
                    PFC = [abs(value) for value in self.dicPFC[(t-Tprevious):(t+self.segment)]], #erstmal nur positive um Überprodukion zu verhindern
                    previousSection = self.previousSegment,
                    productionGoal = 0, 
                    maxPower = self.maxPower, 
                    SOCStart = 0, 
                    objective="maximize_production")[0]
                
                
                maxProdSegment = sum(maxProdSegmentModel["production"])
               
                # 2. calculate opt production for each segment
                productionGoalSegmentModel = self.prodGoalOpt(
                    timestampsTotal = len(self.world.snapshots),
                    timestampsSection = self.section, # kleiner als self.segment um Randeffekte zu minimieren
                    PFC = [abs(value) for value in self.dicPFC], #erstmal nur positive um Überprodukion zu verhindern
                    productionGoal = self.yearlyProductionGoal,
                    maxProductionSection = maxProdSegment)
                
                

                productionGoalSection = [productionGoalSegmentModel.production_section[t]() for t in productionGoalSegmentModel.timesteps]
                
                if self.segment != self.section:
                    x = int(self.segment/self.section)
                    for i in range(0, len(productionGoalSection), x):
                        group = productionGoalSection[i:i+x]
                        sums = sum(group)
                        self.productionGoalSegment.append(sums)
                else:
                    self.productionGoalSegment = productionGoalSection

                print("productionGoalSectioin:", productionGoalSection)
                print("productionGoalSegment:", self.productionGoalSegment)
                
        else:
            # get values from previous segment
            self.previousSegment = self.resultsSegment
            Tprevious = self.Tprevious
            SOCStart = self.resultsSegment["SOC"].iloc[-self.Tprevious-1]

        self.resultsSegment = self.resultsSegment.drop(self.resultsSegment.index)

        # optimize segment
        self.resultsSegment = self.steelOptBase(
            optHorizon = self.segment, 
            timestampsPreviousSection = Tprevious, 
            PFC = [abs(value) for value in self.dicPFC[(t-Tprevious):(t+self.segment)]], #erstmal nur positive um Überprodukion zu verhindern
            previousSection = self.previousSegment.iloc[-Tprevious:].reset_index(drop=True),
            productionGoal = self.productionGoalSegment[t//self.segment], 
            maxPower = self.maxPower, 
            SOCStart = SOCStart, 
            objective="minimize_cost")[0]
        
        self.resultsSegment_all = pd.concat([self.resultsSegment_all[0:t-Tprevious], self.resultsSegment], ignore_index=True)


        self.resultsSegment.to_csv(f'output/2016example/SteelPlant/prod_opt_{OptSegment}.csv', index=True)
        

        print("resultSegment all: ",self.resultsSegment_all)
        
        return self.resultsSegment_all
    

    def calculateFlexBids(self, t):

        global SectionModelFlex
        global timestampsSectionFlex
        
       


        # Determine production and start of batch in considered hour
        productionHour = self.resultsSegment_all["production"][t]
        startHour = self.resultsSegment_all["nextBatch"][t]
        dischargeRate = 30/32 * self.maxPower

        # set default values for price and amount
        flexAmountI = 0
        flexPriceI = 0

        # 2. Start flex calculation
        
        if t > self.Tprevious: # Müsste man noch anpassen, will ich gerade nicht
            if productionHour > 0: # Check if production in considered hour
                if startHour > 0: # Check if start of batch in considered hour
                                        
                    print("calculateFlexBids at time: ", t)
                    flexAmountI = self.resultsSegment_all["production"][t]
                    print("flexAmountI: ", flexAmountI)

                    # 2.1. Determine start index of batch
                    startIndex = t

                    # 2.2. Determine flexibility amount and flexibility price for different flexibility options

                    # 2.2.1. Make a new optimization with blocked start index

                    # set optimization horizon

                    timestampsSectionFlex = self.segment - t % self.segment            # nur für restzeit in diesem segment
                    timestampsPreviousSectionFlex = self.Tprevious 

                    # get values of previous section
                    startFlex = t - timestampsPreviousSectionFlex
                    endFlex = t + 1 # because df[x:y] is exclusive y

                    flexSection = self.resultsSegment_all[startFlex:endFlex].reset_index(drop=True)

                    # set values for blocked timestamp t

                    # print("startFlex: ", startFlex)
                    # print("flexSection: ", flexSection)

                    for columnname in flexSection.columns:
                        if columnname != "SOC" and columnname != "discharge" and columnname != "shutDown":

                            flexSection[columnname][flexSection.index[-1]] = 0

                        else:
                            if columnname == "SOC":
                                if self.resultsSegment_all['SOC'][startIndex - 1] >= dischargeRate: # wirklich start index - 1
                                    flexSection['SOC'][len(flexSection['SOC'])-1] = flexSection['SOC'][len(flexSection['SOC'])-2] - dischargeRate 
                                    flexSection['discharge'][flexSection.index[-1]] = 1
                                else:
                                    flexSection['SOC'][flexSection.index[-1]] = 0
                                    flexSection['discharge'][flexSection.index[-1]] = 0                        


                    SectionModelFlex = self.steelOptBase(
                        optHorizon = timestampsSectionFlex, 
                        timestampsPreviousSection=timestampsPreviousSectionFlex, 
                        PFC = [abs(value) for value in self.dicPFC[(t-timestampsPreviousSectionFlex):(t+timestampsSectionFlex)]],
                        previousSection = flexSection,
                        productionGoal=self.productionGoalSegment[t//self.segment], 
                        maxPower=self.maxPower, 
                        SOCStart=self.resultsSegment_all['SOC'][startFlex-1], 
                        objective="minimize_cost")
                    
                    
                    
                    # prdoction costs old

                    productionCostSegmentOld = sum([self.resultsSegment_all["production"].iloc[i] * abs(self.dicPFC[i-1]) + self.resultsSegment_all["shutDown"].iloc[i] * self.shutDownCost for i in range(startFlex, t + timestampsSectionFlex)])

                    print("productionCostSegmentOld: ", productionCostSegmentOld)
                    

                    flexPriceI = 7 #SectionModelFlex[1][0] - productionCostSegmentOld ### aktuell teilweise mit slag (neue Berehcnung), teilweise ohne slag (alte Berechnung)
                    
                    print("flexPriceI: ", flexPriceI)

                    # Das ist quasi das Feedback, das muss noch anders eingebaut werden, soll nur passieren, wenn flex gebote akzeptiert
                    self.resultsSegment_all.iloc[t:t+timestampsSectionFlex+1] = SectionModelFlex[0][-timestampsSectionFlex:].reset_index(drop=True)

                    
                    
                    
            return flexAmountI, flexPriceI
        else:
            return 0, 0


                    


    
    def calculateBidEOM(self, t):
        BidsEOM = {}
        OptSegment = t // self.segment

        # calculate baseline bids
        if t % self.segment == 0:
            self.resultsSegment_all = self.calculateBaseline(t)
            self.resultsSegment_all.to_csv(f'output/2016example/SteelPlant/prod_gesamt.csv', index=True)

        
        BidsEOM['bidQuantity_plan'] = self.resultsSegment_all["production"][t]
        BidsEOM['bidPrice_plan'] = 3000 # forecast wird erwartet, deswegen wird teuer in den Markt geboten
    
        # calculate flexibility bids

        BidsEOM['bidQuantity_flex'], BidsEOM['bidPrice_flex'] = self.calculateFlexBids(t)


    
        
        return BidsEOM


    
                    

    def checkAvailability(self, t):
        pass
 

   

