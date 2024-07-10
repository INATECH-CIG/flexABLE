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
                 yearlyProductionGoal = 60000,
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


        self.confQtyEOM = {n:0 for n in self.world.snapshots}

        self.dicPFC = self.world.PFC
        df_PFC = pd.DataFrame(self.dicPFC)
        df_PFC.to_csv(f'output/2016example/SteelPlant/PFC.csv', index=False)


        # Unit status parameters
        self.sentBids=[]
        self.sentBids_dict = {}
        self.slag = []
        
        # additional parameters


        self.segment = 96 # Describes the length of a segment for detail optimization
        self.segmentFlex = self.segment * 2 # Describes the length of a segment for the flex switch
        self.section = 32 # Describes the length of a section for the production goal optimization (non detailed)
        self.Tprevious = 24
        self.reproduction_time = 1

        self.resultsSegment = pd.DataFrame()
        self.resultsSegment_all = pd.DataFrame()
        self.previousSegment = pd.DataFrame()
        self.productionGoalSegment = []
        

        self.shutDownCost = 1000000
        self.slagCost = 100000000



        
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

        
        self.sentBids_dict[self.world.currstep] = self.sentBids.copy()
        self.sentBids = []
        
        
    def feedback(self, bid):
        if bid.status == "Confirmed":

            if 'supplyEOM' in bid.ID:
                self.confQtyEOM[self.world.currstep] -= bid.confirmedAmount
            if 'demandEOM' in bid.ID:
                self.confQtyEOM[self.world.currstep] += bid.confirmedAmount

       

            if round(self.confQtyEOM[self.world.currstep],2) != round(self.resultsSegment_all.iloc[self.world.currstep]["production"],2):
                print("Flex bid accepted at time: ", self.world.currstep)
                self.resultsSegment_all.to_csv(f'output/2016example/SteelPlant/prod_opt_{self.world.currstep}_before.csv', index=True)
                self.resultsSegment_all.iloc[self.world.currstep:self.world.currstep+timestampsSectionFlex+1] = SectionModelFlex[0][-(timestampsSectionFlex+1):].reset_index(drop=True)
                self.resultsSegment_all.to_csv(f'output/2016example/SteelPlant/prod_opt_{self.world.currstep}after.csv', index=True)

                print("production goal before flex: ", self.productionGoalSegment)
                self.slagFlex = sum(SectionModelFlex[0]["slag"])
                print("slagFlex: ", self.slagFlex)
                self.updateProductionGoal(self.slagFlex, self.world.currstep)
                print("production goal after flex: ", self.productionGoalSegment)

                


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
                            ID = "{}_SteelPlant_demandEOM".format(self.name),
                            price =  BidsDict['bidPrice_plan'],
                            amount = BidsDict['bidQuantity_plan'],
                            status = "Sent",
                            bidType = "Demand",
                            node = self.node))

     

            bids.append(Bid(issuer = self,
                            ID = "{}_SteelPlant_supplyEOM".format(self.name),
                            price = BidsDict['bidPrice_flex'],
                            amount = BidsDict['bidQuantity_flex'],
                            status = "Sent",
                            bidType = "Supply",
                            node = self.node))
        

        return bids
    
    def updateProductionGoal(self,slag, t):
        OptSegment = t // self.segment
        self.maxProdSegment = self.maxProdSection * (self.segment/self.section)
        counter = 0
        print("SLAG: ",slag)
        while slag > 0:
            print("OptSegment: ", OptSegment)
            print("counter: ", counter)
            if (OptSegment + counter + 1) >= len(self.productionGoalSegment):
                print("PRODUCTION GOAL NOT REACHED")
                break
            else:
                print("PRODUCTION GOAL REACHED")
                if self.productionGoalSegment[OptSegment+counter+1] < self.maxProdSegment:
                    addProduction = self.maxProdSegment - self.productionGoalSegment[OptSegment+counter+1]
                    if slag < addProduction:
                        self.productionGoalSegment[OptSegment+counter+1] += slag
                        slag = 0
                    else:
                        self.productionGoalSegment[OptSegment+counter+1] = self.maxProdSegment
                        slag -= addProduction
                        counter += 1
                else:
                    counter += 1


    

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
                # 1. calculate max production of one section
                maxProdSectionModel = self.steelOptBase(
                    optHorizon = self.section, 
                    timestampsPreviousSection = Tprevious, 
                    PFC = [abs(value) for value in self.dicPFC[(t-Tprevious):(t+self.segment)]], #erstmal nur positive um Überprodukion zu verhindern
                    previousSection = self.previousSegment,
                    productionGoal = 0, 
                    maxPower = self.maxPower, 
                    SOCStart = 0,
                    shutDownCosts=self.shutDownCost,
                    slagCosts=self.slagCost, 
                    objective="maximize_production")[0]
                
                
                self.maxProdSection = sum(maxProdSectionModel["production"])
               
                

                # 2. calculate opt production for each segment
                productionGoalSectionModel = self.prodGoalOpt(
                    timestampsTotal = len(self.world.snapshots),
                    timestampsSection = self.section, # kleiner als self.segment um Randeffekte zu minimieren
                    PFC = [abs(value) for value in self.dicPFC], #erstmal nur positive um Überprodukion zu verhindern
                    productionGoal = self.yearlyProductionGoal,
                    maxProductionSection = self.maxProdSection)
                
                

                productionGoalSection = [productionGoalSectionModel.production_section[t]() for t in productionGoalSectionModel.timesteps]
                
                


                if self.segment != self.section:
                    x = int(self.segment/self.section)
                    for i in range(0, len(productionGoalSection), x):
                        group = productionGoalSection[i:i+x]
                        sums = sum(group)
                        self.productionGoalSegment.append(sums)
                else:
                    self.productionGoalSegment = productionGoalSection

                
                print("productionGoalSection:", productionGoalSection)
                print("productionGoalSegment:", self.productionGoalSegment)
                
        else:
            # get values from previous segment
            self.previousSegment = self.resultsSegment_all.iloc[t-self.segment:t].reset_index(drop=True)
            Tprevious = self.Tprevious
            SOCStart = self.resultsSegment_all["SOC"].iloc[t-self.Tprevious-1]


        # optimize segment
        self.resultsSegment = self.steelOptBase(
            optHorizon = self.segment, 
            timestampsPreviousSection = Tprevious, 
            PFC = [abs(value) for value in self.dicPFC[(t-Tprevious):(t+self.segment)]], #erstmal nur positive um Überprodukion zu verhindern
            previousSection = self.previousSegment.iloc[-Tprevious:].reset_index(drop=True),
            productionGoal = self.productionGoalSegment[t//self.segment], 
            maxPower = self.maxPower, 
            SOCStart = SOCStart,
            shutDownCosts=self.shutDownCost,
            slagCosts=self.slagCost, 
            objective="minimize_cost")[0]
        
        self.resultsSegment_all = pd.concat([self.resultsSegment_all[0:t-Tprevious], self.resultsSegment], ignore_index=True)


        self.resultsSegment.to_csv(f'output/2016example/SteelPlant/prod_opt_{OptSegment}.csv', index=True)

        self.slag.append(sum(self.resultsSegment["slag"]))
        print(self.slag[-1])
        print("production goal: ",self.productionGoalSegment)
        self.updateProductionGoal(self.slag[-1],t)
        print("production goal: ",self.productionGoalSegment)

        
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
        
        if t > self.Tprevious: # Müsste man noch anpassen, will ich gerade nicht ### Check ###
            if productionHour > 0: # Check if production in considered hour
                if startHour > 0: # Check if start of batch in considered hour
                                        
                    print("calculateFlexBids at time: ", t)
                    flexAmountI = self.resultsSegment_all["production"][t]

                    # 2.1. Determine start index of batch
                    startIndex = t

                    # 2.2. Determine flexibility amount and flexibility price for different flexibility options

                    # 2.2.1. Make a new optimization with blocked start index

                    # set optimization horizon

                    timestampsSectionFlex = self.segment - t % self.segment - 1            # nur für restzeit in diesem segment
                    timestampsPreviousSectionFlex = self.Tprevious 

                    # get values of previous segment
                    startFlex = t - timestampsPreviousSectionFlex + 1
                    endFlex = t + 1 # because df[x:y] is exclusive y

                    flexSection = self.resultsSegment_all[startFlex:endFlex].reset_index(drop=True)

                    # set values for blocked timestamp t
                    
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
                        productionGoal=sum(self.resultsSegment_all["production"][startFlex:t+timestampsSectionFlex]), 
                        maxPower=self.maxPower, 
                        SOCStart=self.resultsSegment_all['SOC'][startFlex-1],
                        shutDownCosts=self.shutDownCost,
                        slagCosts=self.slagCost, 
                        objective="minimize_cost")
    
                    if t==32:
                        print("Stop")
                    
                    # prdoction costs old

                    productionCostSegmentOld = sum([self.resultsSegment_all["el_consumption"].iloc[i] * abs(self.dicPFC[i-1]) + self.resultsSegment_all["shutDown"].iloc[i] * self.shutDownCost for i in range(startFlex, t + timestampsSectionFlex)])
                    productionCostSegementNew = sum([SectionModelFlex[0]["el_consumption"].iloc[i] * abs(self.dicPFC[startFlex + i -1]) + SectionModelFlex[0]["shutDown"].iloc[i] * self.shutDownCost for i in range(0, len(SectionModelFlex[0]))])

                    print("production cost new",productionCostSegementNew)
                    print("production cost old",productionCostSegmentOld)
                    print("Cost objective: ", SectionModelFlex[1])
                    print("Slag: ", SectionModelFlex[2])

                    # if t == 28:# or t == 50 or t == 91:
                    #     flexPriceI  = -1000
                    # else:
                    #     flexAmountI = 0
                    #     flexPriceI = 1000000

                    flexPriceI = productionCostSegementNew - productionCostSegmentOld ### aktuell teilweise mit slag (neue Berehcnung), teilweise ohne slag (alte Berechnung)

                    # check if slag due to flex can´t be produced in next segment (reproduction_time)
                    # self.slagFlex = sum(SectionModelFlex[0]["slag"])
                    # freeCap = 0
                    # reproductionTime_temp = self.reproduction_time
                    # if len(self.productionGoalSegment) - (t//self.segment) - 1 >= reproductionTime_temp:
                    #     for i in range(1,reproductionTime_temp+1):
                    #         freeCap += (self.maxProdSegment - self.productionGoalSegment[(t//self.segment)+i])
                    # else:
                    #     reproductionTime_temp = len(self.productionGoalSegment) - (t//self.segment) - 1
                    #     for i in range(1,reproductionTime_temp+1):
                    #         freeCap += (self.maxProdSegment - self.productionGoalSegment[(t//self.segment)+i])

                    # if freeCap < self.slagFlex:
                    #     flexAmountI = 0
                    #     flexPriceI = 0


                    
                  
                    



              






                    
                    
                    
            return flexAmountI, flexPriceI
        else:
            return 0, 0


                    


    
    def calculateBidEOM(self, t):
        BidsEOM = {}
        OptSegment = t // self.segment

        # calculate baseline bids
        if t % self.segment == 0:
            self.resultsSegment_all = self.calculateBaseline(t)
            

        
        BidsEOM['bidQuantity_plan'] = self.resultsSegment_all["production"][t]
        BidsEOM['bidPrice_plan'] = 3000 # forecast wird erwartet, deswegen wird teuer in den Markt geboten
    
        # calculate flexibility bids

        BidsEOM['bidQuantity_flex'], BidsEOM['bidPrice_flex'] = self.calculateFlexBids(t)


    
        
        return BidsEOM


    
                    

    def checkAvailability(self, t):
        pass
 

   

