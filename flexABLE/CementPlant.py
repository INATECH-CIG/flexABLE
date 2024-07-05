# -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 17:04:23 2020

@author: intgridnb-02
"""
from .auxFunc import initializer
from .bid import Bid
import pandas as pd
from .cementPlantOptimization import cementOptBase
from .productionGoalOptimization import prodGoalOpt
import logging

class CementPlant():
    

    @initializer
    def __init__(self,
                 agent = None,
                 minPowerRawMill = 260,
                 maxPowerRawMill = 260,
                 minPowerKiln = 130,
                 maxPowerKiln = 130,
                 minPowerCementMill = 390,
                 maxPowerCementMill = 390,
                 maxCapRawMealSilo = 22000,
                 maxCapClinkerDome = 22000,
                 elConsRawMill = 0.023, # electricity consumption mwh of raw mill per ton
                 elConsKiln = 0.030, # electricity consumption mwh of kiln per ton
                 elConsCementMill = 0.040, # electricity consumption mwh of cement mill per ton
                 node = 'Bus_DE',
                 world = None,
                 yearlyProductionGoal = 23000,
                 technology = "industry",
                 **kwargs):
        
        # get necessary functions
        self.cementOptBase = cementOptBase
        self.prodGoalOpt = prodGoalOpt

        # bid status parameters
        self.sentBids=[]

        self.dictCapacity = {n:None for n in self.world.snapshots}
        self.maxPower = self.maxPowerRawMill * elConsRawMill + self.maxPowerKiln * elConsKiln + self.maxPowerCementMill * elConsCementMill
        self.dictCapacity[self.world.snapshots[0]] = self.maxPower
        self.dictCapacity[-1] = self.maxPower

        self.dictCapacityMR = {n:(0,0) for n in self.world.snapshots}
        self.dictCapacityFlex = {n:(0,0) for n in self.world.snapshots}


        self.confQtyEOM = {n:0 for n in self.world.snapshots}

        self.dicPFC = self.world.PFC



        # Unit status parameters
        self.sentBids=[]
        self.sentBids_dict = {}
        self.slag = []
        
        # additional parameters


        self.segment = 96 # Describes the length of a segment for detail optimization
        self.segmentFlex = self.segment * 2 # Describes the length of a segment for the flex switch
        self.section = 96 # Describes the length of a section for the production goal optimization (non detailed)
        self.Tprevious = 24
        self.reproduction_time = 1

        self.resultsSegment = pd.DataFrame()
        self.resultsSegment_all = pd.DataFrame()
        self.previousSegment = pd.DataFrame()
        self.productionGoalSegment = []

        self.rawMillClinkerFactor = 1.61 # t rawmill/t clinker #HERE not sure if i use it right maybe "kehrwert"
        self.clinkerCementFactor = 0.86 # t clinker/t cement #HERE not sure if i use it right maybe "kehrwert"
        
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

            if round(self.confQtyEOM[self.world.currstep],2) != round(self.resultsSegment_all.iloc[self.world.currstep]["el_cons_total"],2):
                logging.debug("Flex bid accepted at time: ", self.world.currstep)
                self.resultsSegment_all.to_csv(f'output/2016example/CementPlant/prod_opt_{self.world.currstep}_before.csv', index=True)
                self.resultsSegment_all.iloc[self.world.currstep:self.world.currstep+timestampsSectionFlex+1] = SectionModelFlex[-(timestampsSectionFlex+1):].reset_index(drop=True)
                self.resultsSegment_all.to_csv(f'output/2016example/CementPlant/prod_opt_{self.world.currstep}after.csv', index=True)

 

                self.slagFlex = sum(SectionModelFlex["slag"])
                # print("Slag Flex: ", self.slagFlex)
                # print("production goal before", self.productionGoalSegment)
                self.updateProductionGoal(self.slagFlex, self.world.currstep)
                # print("production goal after", self.productionGoalSegment)

        self.sentBids.append(bid)


    def write_to_db(self,t, bid):
        self.world.ResultsWriter.writeBid(self, t, bid)

    def requestBid(self, t, market):
        bids = []
        
        if market == "EOM":
            BidsDict = self.calculateBidEOM(t)           
            # if BidsDict['bidQuantity_plan'] != 0:
            bids.append(Bid(issuer = self,
                            ID = "{}_CementPlant_demandEOM".format(self.name),
                            price =  BidsDict['bidPrice_plan'],
                            amount = BidsDict['bidQuantity_plan'],
                            status = "Sent",
                            bidType = "Demand",
                            node = self.node))

     
            if BidsDict['bidQuantity_flex'] == 0:
                pass
            else:
                bids.append(Bid(issuer = self, 
                                ID = "{}_CementPlant_supplyEOM".format(self.name),
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
        while slag > 0:
            if (OptSegment + counter + 1) >= len(self.productionGoalSegment):
                break
            else:
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
        logging.debug("Optimiere Baseline für Segment: ", t//self.segment)
        #calculate the baseline based on the PFC for given length of segment
        OptSegment = t // self.segment
        
        

        if t == 0:
                # set parameter and determine production goal
                self.previousSegment = pd.DataFrame()
                Tprevious = 0
                SOCStart = 0
                # calulate production for every segment
                # 1. calculate max production of one section
                maxProdSectionModel = self.cementOptBase(
                    optHorizon = self.section, 
                    timestampsPreviousSection = Tprevious, 
                    PFC = [abs(value) for value in self.dicPFC[(t-Tprevious):(t+self.segment)]], #erstmal nur positive um Überprodukion zu verhindern
                    previousSection = self.previousSegment,
                    productionGoal = 0, 
                    minPowerRawMill = self.minPowerRawMill,
                    maxPowerRawMill = self.maxPowerRawMill,
                    minPowerKiln = self.minPowerKiln,
                    maxPowerKiln = self.maxPowerKiln,
                    minPowerCementMill = self.minPowerCementMill,
                    maxPowerCementMill = self.maxPowerCementMill,
                    maxCapRawMealSilo = self.maxCapRawMealSilo,
                    maxCapClinkerDome = self.maxCapClinkerDome,
                    elConsRawMill = self.elConsRawMill,
                    elConsKiln = self.elConsKiln,
                    elConsCementMill = self.elConsCementMill, 
                    slagCosts=self.slagCost, 
                    objective="maximize_production")[0]
                
                # maxProdSectionModel.to_csv(f'output/2016example/CementPlant/maxProdSection_{OptSegment}.csv', index=True)
                
                
                self.maxProdSection = sum(maxProdSectionModel["output_cement_mill"])
               
                

                # 2. calculate opt production for each segment 
                productionGoalSectionModel = self.prodGoalOpt(
                    timestampsTotal = len(self.world.snapshots),
                    timestampsSection = self.section, # kleiner als self.segment um Randeffekte zu minimieren
                    PFC = [abs(value) for value in self.dicPFC], #erstmal nur positive um Überprodukion zu verhindern
                    productionGoal = self.yearlyProductionGoal,
                    maxProductionSection = self.maxProdSection)
                
                

                productionGoalSection = [productionGoalSectionModel.production_section[t]() for t in productionGoalSectionModel.timesteps]
                slagproductionGoal = sum([productionGoalSectionModel.slag[t]() for t in productionGoalSectionModel.timesteps])

                if slagproductionGoal >= 0:
                    logging.debug("Total production goal can´t be reached by:", slagproductionGoal)


                if self.segment != self.section:
                    x = int(self.segment/self.section)
                    for i in range(0, len(productionGoalSection), x):
                        group = productionGoalSection[i:i+x]
                        sums = sum(group)
                        self.productionGoalSegment.append(sums)
                else:
                    self.productionGoalSegment = productionGoalSection


                
        else:
            # get values from previous segment
            self.previousSegment = self.resultsSegment_all.iloc[t-self.segment:t].reset_index(drop=True)
            Tprevious = self.Tprevious

            # self.previousSegment.to_csv(f'output/2016example/CementPlant/previous_segment_{OptSegment}.csv', index=True)

        # optimize segment
        self.resultsSegment = self.cementOptBase(
            optHorizon = self.segment, 
            timestampsPreviousSection = Tprevious, 
            PFC = [abs(value) for value in self.dicPFC[(t-Tprevious):(t+self.segment)]], #erstmal nur positive um Überprodukion zu verhindern
            previousSection = self.previousSegment.iloc[-Tprevious:].reset_index(drop=True),
            productionGoal = self.productionGoalSegment[t//self.segment],
            minPowerRawMill = self.minPowerRawMill,
            maxPowerRawMill = self.maxPowerRawMill,
            minPowerKiln = self.minPowerKiln,
            maxPowerKiln = self.maxPowerKiln,
            minPowerCementMill = self.minPowerCementMill,
            maxPowerCementMill = self.maxPowerCementMill,
            maxCapRawMealSilo = self.maxCapRawMealSilo,
            maxCapClinkerDome = self.maxCapClinkerDome,
            elConsRawMill = self.elConsRawMill,
            elConsKiln = self.elConsKiln,
            elConsCementMill = self.elConsCementMill,
            slagCosts=self.slagCost, 
            objective="minimize_cost")[0]
        
        self.resultsSegment_all = pd.concat([self.resultsSegment_all[0:t-Tprevious], self.resultsSegment], ignore_index=True)


        self.resultsSegment.to_csv(f'output/2016example/CementPlant/prod_opt_{OptSegment}.csv', index=True)

        self.slag.append(sum(self.resultsSegment["slag"]))
        self.updateProductionGoal(self.slag[-1],t)

        
        return self.resultsSegment_all



    def calculateFlexBids(self, t): 

        global SectionModelFlex
        global timestampsSectionFlex

        SectionModelFlex = pd.DataFrame()
        SectionModelFlex_I = pd.DataFrame()
        SectionModelFlex_II = pd.DataFrame()
        SectionModelFlex_III = pd.DataFrame()

        flexSectionI = pd.DataFrame()
        flexSectionII = pd.DataFrame()
        flexSectionIII = pd.DataFrame()
        
        # check if raw_mill can be turned off
        if t > 16 and t%96 <= (self.segment-5) and self.resultsSegment_all["raw_meal_silo"][t-1] >= self.maxPowerKiln * self.rawMillClinkerFactor and self.resultsSegment_all["raw_mill_start"][t-16:t].sum() == 0 and self.resultsSegment_all["raw_mill_on"][t] == 1:
            # check if flex leads to shutdwon
            if self.resultsSegment_all["raw_mill_stop"].iloc[t-4] == 1 and sum(self.resultsSegment_all["raw_mill_on"].iloc[t-4:t]) == 0:
                # check if shutdown is possible
                if self.resultsSegment_all["raw_meal_silo"].iloc[t-1] >= (self.maxPowerKiln * self.rawMillClinkerFactor * 16):
                    RawMillFlex = True
                else:
                    RawMillFlex = False
            else:
                RawMillFlex = True        
        else:
            RawMillFlex = False

        # check if cement_mill can be turned off
        if t > 16 and t%96 <= (self.segment-5) and self.resultsSegment_all["clinker_dome"][t-1] + self.minPowerKiln <= self.maxCapClinkerDome and self.resultsSegment_all["cement_mill_start"][t-16:t].sum() == 0 and self.resultsSegment_all["cement_mill_on"][t] == 1:
            # check if flex leads to shutdwon
            if self.resultsSegment_all["cement_mill_stop"].iloc[t-4] == 1 and sum(self.resultsSegment_all["cement_mill_on"].iloc[t-4:t]) == 0:
                # check if shutdown is possible
                if self.maxCapClinkerDome >= self.resultsSegment_all["clinker_dome"].iloc[t-1] + (self.minPowerKiln * 16):
                    CementMillFlex = True
                else:
                    CementMillFlex = False
            else:
                CementMillFlex = True                
        else:
            CementMillFlex = False


        # set default values for price and amount
        BidI = 0
        BidII = 0
        BidIII = 0
        flexAmountI = 0
        flexPriceI = 0
        flexAmountII = 0
        flexPriceII = 0
        flexAmountIII = 0
        flexPriceIII = 0

        # set optimization horizon

        timestampsSectionFlex = self.segment - t % self.segment - 1            # nur für restzeit in diesem segment
        
        if t < self.Tprevious:
            timestampsPreviousSectionFlex = t 
        else:
            timestampsPreviousSectionFlex = self.Tprevious 

        # get values of previous segment
        startFlex = t - timestampsPreviousSectionFlex + 1
        endFlex = t + 1 # because df[x:y] is exclusive y


        flexSection = self.resultsSegment_all[startFlex:endFlex].reset_index(drop=True)

        






        # set values for blocked timestamps

        if CementMillFlex == True and RawMillFlex == True:
            # print(t, "CementMillFlex and RawMillFlex ------------------------------------------")
            flexSectionI = flexSection.copy()
            
            flexAmountI = float(flexSectionI["el_cons_raw_mill"][flexSectionI.index[-1]]) + int(flexSectionI["el_cons_cement_mill"][flexSectionI.index[-1]])

            # cement mill
            flexSectionI["clinker_dome"][flexSectionI.index[-1]] = flexSectionI["clinker_dome"][flexSectionI.index[-1]] + flexSectionI["input_cement_mill"][flexSectionI.index[-1]]
            flexSectionI["input_cement_mill"][flexSectionI.index[-1]] = 0
            flexSectionI["output_cement_mill"][flexSectionI.index[-1]] = 0
            flexSectionI["el_cons_cement_mill"][flexSectionI.index[-1]] = 0
            flexSectionI["cement_mill_on"][flexSectionI.index[-1]] = 0

            if flexSectionI["cement_mill_stop"][flexSectionI.index[-5]] == 1 and flexSectionI["cement_mill_on"].iloc[-5:-1].sum() == 0:
                flexSectionI["cement_mill_shut_down_change"][flexSectionI.index[-1]] = 0
            else:
                flexSectionI["cement_mill_shut_down_change"][flexSectionI.index[-1]] = 1

            if flexSectionI["cement_mill_stop"].iloc[-4:-1].sum() == 1:
                flexSectionI["cement_mill_shut_down"][flexSectionI.index[-1]] = 1
            else:
                if flexSectionI["cement_mill_start"][flexSectionI.index[-1]] == 1:
                    flexSectionI["cement_mill_stop"][flexSectionI.index[-1]] = 0
                    flexSectionI["cement_mill_shut_down"][flexSectionI.index[-1]] = 0
                else:
                    flexSectionI["cement_mill_stop"][flexSectionI.index[-1]] = 1
                    flexSectionI["cement_mill_shut_down"][flexSectionI.index[-1]] = 1
            flexSectionI["cement_mill_start"][flexSectionI.index[-1]] = 0

            
            # raw mill
            flexSectionI["raw_meal_silo"][flexSectionI.index[-1]] = flexSectionI["raw_meal_silo"][flexSectionI.index[-1]] - flexSectionI["output_raw_mill"][flexSectionI.index[-1]]
            flexSectionI["output_raw_mill"][flexSectionI.index[-1]] = 0
            flexSectionI["el_cons_raw_mill"][flexSectionI.index[-1]] = 0
            flexSectionI["raw_mill_on"][flexSectionI.index[-1]] = 0

            if flexSectionI["raw_mill_stop"][flexSectionI.index[-5]] == 1 and flexSectionI["raw_mill_on"].iloc[-5:-1].sum() == 0:
                flexSectionI["raw_mill_shut_down_change"][flexSectionI.index[-1]] = 0
            else:
                flexSectionI["raw_mill_shut_down_change"][flexSectionI.index[-1]] = 1


            if flexSectionI["raw_mill_stop"].iloc[-4:-1].sum() == 1:
                flexSectionI["raw_mill_shut_down"][flexSectionI.index[-1]] = 1
            else:
                if flexSectionI["raw_mill_start"][flexSectionI.index[-1]] == 1:
                    flexSectionI["raw_mill_stop"][flexSectionI.index[-1]] = 0
                    flexSectionI["raw_mill_shut_down"][flexSectionI.index[-1]] = 0
                else:
                    flexSectionI["raw_mill_stop"][flexSectionI.index[-1]] = 1
                    flexSectionI["raw_mill_shut_down"][flexSectionI.index[-1]] = 1
            flexSectionI["raw_mill_start"][flexSectionI.index[-1]] = 0

            # flexSection.to_csv(f'output/2016example/CementPlant/flexSection_{t}.csv', index=True)

            if timestampsPreviousSectionFlex >= self.Tprevious:
                addCount = 1
            else:
                addCount = 0
            # benötigt man, beispiel: t = 26, timestampsPreviosuSection = 24 --> untere Grenze des PFC abrufs wird 2, aber t previous geht eigentlich von 3-26 (24 einheiten)


            SectionModelFlex_RawMill_CementMill = self.cementOptBase(
                optHorizon = timestampsSectionFlex, 
                timestampsPreviousSection = timestampsPreviousSectionFlex, 
                PFC = [abs(value) for value in self.dicPFC[(t-timestampsPreviousSectionFlex+addCount):(t+timestampsSectionFlex+1)]], #erstmal nur positive um Überprodukion zu verhindern
                previousSection = flexSectionI,
                productionGoal = sum(self.resultsSegment_all["output_cement_mill"][t:t+timestampsSectionFlex+1]), # kein t+1 da verlorene Produktion nachgeholt werden muss
                minPowerRawMill = self.minPowerRawMill,
                maxPowerRawMill = self.maxPowerRawMill,
                minPowerKiln = self.minPowerKiln,
                maxPowerKiln = self.maxPowerKiln,
                minPowerCementMill = self.minPowerCementMill,
                maxPowerCementMill = self.maxPowerCementMill,
                maxCapRawMealSilo = self.maxCapRawMealSilo,
                maxCapClinkerDome = self.maxCapClinkerDome,
                elConsRawMill = self.elConsRawMill,
                elConsKiln = self.elConsKiln,
                elConsCementMill = self.elConsCementMill, 
                slagCosts=self.slagCost, 
                objective="minimize_cost")
            
            # production costs old and new

            SectionModelFlex_I = SectionModelFlex_RawMill_CementMill[0].copy()



            # production costs old and new

            if t <= self.Tprevious:
                startFlex_cost = 0
            else:
                startFlex_cost = startFlex
            #Nötig weil: Wenn man sonst t<= self.Tprecios hat, ist startFlex=1, somit fehlt der index 0 zu Berechnung der Kosten

            productionCostSegmentOld = sum([self.resultsSegment_all["el_cons_total"].iloc[i] * abs(self.dicPFC[i]) for i in range(startFlex_cost, t + timestampsSectionFlex+1)]) 
            productionCostSegementNew = sum([SectionModelFlex_I["el_cons_total"].iloc[i] * abs(self.dicPFC[startFlex_cost+i]) for i in range(0, len(SectionModelFlex_I))])

            flexPriceI = int(productionCostSegementNew - productionCostSegmentOld)

            # print("productionCostSegmentOld", productionCostSegmentOld)
            # print("productionCostSegementNew", productionCostSegementNew)
            # print("flexPriceI", flexPriceI)
            # print("flexAmountI", flexAmountI)

            # check if slag due to flex can´t be produced in next segment (reproduction_time)
            self.slagFlex = sum(SectionModelFlex_I["slag"])
            freeCap = 0
            reproductionTime_temp = self.reproduction_time
            if len(self.productionGoalSegment) - (t//self.segment) - 1 >= reproductionTime_temp:
                for i in range(1,reproductionTime_temp+1):
                    freeCap += (self.maxProdSegment - self.productionGoalSegment[(t//self.segment)+i])
            else:
                reproductionTime_temp = len(self.productionGoalSegment) - (t//self.segment) - 1
                for i in range(1,reproductionTime_temp+1):
                    freeCap += (self.maxProdSegment - self.productionGoalSegment[(t//self.segment)+i])

            if flexAmountI > 0:
                BidI = flexPriceI/flexAmountI
            # print("BidI", BidI)
            
            if freeCap < self.slagFlex:
                flexAmountI = 0
                flexPriceI = 0




        





        

        if RawMillFlex == True:
            # print(t, "RawMillFlex")

            flexSectionII = flexSection.copy()

            flexAmountII = float(flexSection["el_cons_raw_mill"][flexSection.index[-1]])
            
            flexSectionII["raw_meal_silo"][flexSectionII.index[-1]] = flexSectionII["raw_meal_silo"][flexSectionII.index[-1]] - flexSectionII["output_raw_mill"][flexSectionII.index[-1]]
            flexSectionII["output_raw_mill"][flexSectionII.index[-1]] = 0
            flexSectionII["el_cons_raw_mill"][flexSectionII.index[-1]] = 0
            flexSectionII["raw_mill_on"][flexSectionII.index[-1]] = 0

            if flexSectionII["raw_mill_stop"][flexSectionII.index[-5]] == 1 and flexSectionII["raw_mill_on"].iloc[-5:-1].sum() == 0:
                flexSectionII["raw_mill_shut_down_change"][flexSectionII.index[-1]] = 0
            else:
                flexSectionII["raw_mill_shut_down_change"][flexSectionII.index[-1]] = 1


            if flexSectionII["raw_mill_stop"].iloc[-4:-1].sum() == 1:
                flexSectionII["raw_mill_shut_down"][flexSectionII.index[-1]] = 1
            else:
                if flexSectionII["raw_mill_start"][flexSectionII.index[-1]] == 1:
                    flexSectionII["raw_mill_stop"][flexSectionII.index[-1]] = 0
                    flexSectionII["raw_mill_shut_down"][flexSectionII.index[-1]] = 0
                else:
                    flexSectionII["raw_mill_stop"][flexSectionII.index[-1]] = 1
                    flexSectionII["raw_mill_shut_down"][flexSectionII.index[-1]] = 1
            flexSectionII["raw_mill_start"][flexSectionII.index[-1]] = 0

            


            # flexSection.to_csv(f'output/2016example/CementPlant/flexSection_{t}.csv', index=True)

            if timestampsPreviousSectionFlex >= self.Tprevious:
                addCount = 1
            else:
                addCount = 0
            # benötigt man, beispiel: t = 26, timestampsPreviosuSection = 24 --> untere Grenze des PFC abrufs wird 2, aber t previous geht eigentlich von 3-26 (24 einheiten)





            SectionModelFlex_RawMill = self.cementOptBase(
                optHorizon = timestampsSectionFlex, 
                timestampsPreviousSection = timestampsPreviousSectionFlex, 
                PFC = [abs(value) for value in self.dicPFC[(t-timestampsPreviousSectionFlex+addCount):(t+timestampsSectionFlex+1)]], #erstmal nur positive um Überprodukion zu verhindern
                previousSection = flexSectionII,
                productionGoal = sum(self.resultsSegment_all["output_cement_mill"][t+1:t+timestampsSectionFlex+1]),  #+1 da sonst produktion aus t doppelt berechnet wird
                minPowerRawMill = self.minPowerRawMill,
                maxPowerRawMill = self.maxPowerRawMill,
                minPowerKiln = self.minPowerKiln,
                maxPowerKiln = self.maxPowerKiln,
                minPowerCementMill = self.minPowerCementMill,
                maxPowerCementMill = self.maxPowerCementMill,
                maxCapRawMealSilo = self.maxCapRawMealSilo,
                maxCapClinkerDome = self.maxCapClinkerDome,
                elConsRawMill = self.elConsRawMill,
                elConsKiln = self.elConsKiln,
                elConsCementMill = self.elConsCementMill, 
                slagCosts=self.slagCost, 
                objective="minimize_cost")
            
            # production costs old and new

            SectionModelFlex_II = SectionModelFlex_RawMill[0].copy()

            



            if t <= self.Tprevious:
                startFlex_cost = 0
            else:
                startFlex_cost = startFlex
            #Nötig weil: Wenn man sonst t<= self.Tprecios hat, ist startFlex=1, somit fehlt der index 0 zu Berechnung der Kosten

            productionCostSegmentOld = sum([self.resultsSegment_all["el_cons_total"].iloc[i] * abs(self.dicPFC[i]) for i in range(startFlex_cost, t + timestampsSectionFlex+1)]) 
            productionCostSegementNew = sum([SectionModelFlex_II["el_cons_total"].iloc[i] * abs(self.dicPFC[startFlex_cost+i]) for i in range(0, len(SectionModelFlex_II))])

            flexPriceII = int(productionCostSegementNew - productionCostSegmentOld)
            # print("productionCostSegmentOld", productionCostSegmentOld)
            # print("productionCostSegementNew", productionCostSegementNew)
            # print("flexPriceII", flexPriceII)
            # print("flexAmountII", flexAmountII)

            # check if slag due to flex can´t be produced in next segment (reproduction_time)
            self.slagFlex = sum(SectionModelFlex_II["slag"])
            freeCap = 0
            reproductionTime_temp = self.reproduction_time
            if len(self.productionGoalSegment) - (t//self.segment) - 1 >= reproductionTime_temp:
                for i in range(1,reproductionTime_temp+1):
                    freeCap += (self.maxProdSegment - self.productionGoalSegment[(t//self.segment)+i])
            else:
                reproductionTime_temp = len(self.productionGoalSegment) - (t//self.segment) - 1
                for i in range(1,reproductionTime_temp+1):
                    freeCap += (self.maxProdSegment - self.productionGoalSegment[(t//self.segment)+i])

            if flexAmountII > 0:
                BidII = flexPriceII/flexAmountII
            # print("BidII", BidII)
            
            if freeCap < self.slagFlex:
                # print("No free cap")
                flexAmountII = 0
                flexPriceII = 0



        
        



           
        if CementMillFlex == True:

            flexSectionIII = flexSection.copy()

            # print(t, "CementMillFlex")
            flexAmountIII = float(flexSection["el_cons_cement_mill"][flexSection.index[-1]])

            flexSectionIII["clinker_dome"][flexSectionIII.index[-1]] = flexSectionIII["clinker_dome"][flexSectionIII.index[-1]] + flexSectionIII["input_cement_mill"][flexSectionIII.index[-1]]
            flexSectionIII["input_cement_mill"][flexSectionIII.index[-1]] = 0
            flexSectionIII["output_cement_mill"][flexSectionIII.index[-1]] = 0
            flexSectionIII["el_cons_cement_mill"][flexSectionIII.index[-1]] = 0
            flexSectionIII["cement_mill_on"][flexSectionIII.index[-1]] = 0

            if flexSectionIII["cement_mill_stop"][flexSectionIII.index[-5]] == 1 and flexSectionIII["cement_mill_on"].iloc[-5:-1].sum() == 0:
                flexSectionIII["cement_mill_shut_down_change"][flexSectionIII.index[-1]] = 0
            else:
                flexSectionIII["cement_mill_shut_down_change"][flexSectionIII.index[-1]] = 1

            if flexSectionIII["cement_mill_stop"].iloc[-4:-1].sum() == 1:
                flexSectionIII["cement_mill_shut_down"][flexSectionIII.index[-1]] = 1
            else:
                if flexSectionIII["cement_mill_start"][flexSectionIII.index[-1]] == 1:
                    flexSectionIII["cement_mill_stop"][flexSectionIII.index[-1]] = 0
                    flexSectionIII["cement_mill_shut_down"][flexSectionIII.index[-1]] = 0
                else:
                    flexSectionIII["cement_mill_stop"][flexSectionIII.index[-1]] = 1
                    flexSectionIII["cement_mill_shut_down"][flexSectionIII.index[-1]] = 1
            flexSectionIII["cement_mill_start"][flexSectionIII.index[-1]] = 0

            

            if timestampsPreviousSectionFlex >= self.Tprevious:
                addCount = 1
            else:
                addCount = 0

            
        # benötigt man, beispiel: t = 26, timestampsPreviosuSection = 24 --> untere Grenze des PFC abrufs wird 2, aber t previous geht eigentlich von 3-26 (24 einheiten)

            SectionModelFlex_CementMill = self.cementOptBase(
                optHorizon = timestampsSectionFlex, 
                timestampsPreviousSection = timestampsPreviousSectionFlex, 
                PFC = [abs(value) for value in self.dicPFC[(t-timestampsPreviousSectionFlex+addCount):(t+timestampsSectionFlex+1)]], #erstmal nur positive um Überprodukion zu verhindern
                previousSection = flexSectionIII,
                productionGoal = sum(self.resultsSegment_all["output_cement_mill"][t:t+timestampsSectionFlex+1]), # kein t+1 da verlorene Produktion nachgeholt werden muss
                minPowerRawMill = self.minPowerRawMill,
                maxPowerRawMill = self.maxPowerRawMill,
                minPowerKiln = self.minPowerKiln,
                maxPowerKiln = self.maxPowerKiln,
                minPowerCementMill = self.minPowerCementMill,
                maxPowerCementMill = self.maxPowerCementMill,
                maxCapRawMealSilo = self.maxCapRawMealSilo,
                maxCapClinkerDome = self.maxCapClinkerDome,
                elConsRawMill = self.elConsRawMill,
                elConsKiln = self.elConsKiln,
                elConsCementMill = self.elConsCementMill, 
                slagCosts=self.slagCost, 
                objective="minimize_cost")
            
            SectionModelFlex_III = SectionModelFlex_CementMill[0].copy()
            
            # production costs old and new

            if t <= self.Tprevious:
                startFlex_cost = 0
            else:
                startFlex_cost = startFlex
            #Nötig weil: Wenn man sonst t<= self.Tprecios hat, ist startFlex=1, somit fehlt der index 0 zu Berechnung der Kosten

            productionCostSegmentOld = sum([self.resultsSegment_all["el_cons_total"].iloc[i] * abs(self.dicPFC[i]) for i in range(startFlex_cost, t + timestampsSectionFlex+1)]) 
            productionCostSegementNew = sum([SectionModelFlex_III["el_cons_total"].iloc[i] * abs(self.dicPFC[startFlex_cost+i]) for i in range(0, len(SectionModelFlex_III))])

            flexPriceIII = int(productionCostSegementNew - productionCostSegmentOld)

            # print("productionCostSegmentOld", productionCostSegmentOld)
            # print("productionCostSegementNew", productionCostSegementNew)
            # print("flexPriceIII", flexPriceIII)
            # print("flexAmountIII", flexAmountIII)

            # check if slag due to flex can´t be produced in next segment (reproduction_time)
            self.slagFlex = sum(SectionModelFlex_III["slag"])
            freeCap = 0
            reproductionTime_temp = self.reproduction_time
            if len(self.productionGoalSegment) - (t//self.segment) - 1 >= reproductionTime_temp:
                for i in range(1,reproductionTime_temp+1):
                    freeCap += (self.maxProdSegment - self.productionGoalSegment[(t//self.segment)+i])
            else:
                reproductionTime_temp = len(self.productionGoalSegment) - (t//self.segment) - 1
                for i in range(1,reproductionTime_temp+1):
                    freeCap += (self.maxProdSegment - self.productionGoalSegment[(t//self.segment)+i])

            if flexAmountIII > 0:
                BidIII = flexPriceIII/flexAmountIII
            # print("BidIII", BidIII)
            
            if freeCap < self.slagFlex:
                flexAmountIII = 0
                flexPriceIII = 0

        

        flex_bid_list = []
        flex_bid_list.append(("CaseI",flexAmountI, BidI))
        flex_bid_list.append(("CaseII",flexAmountII, BidII))
        flex_bid_list.append(("CaseIII",flexAmountIII, BidIII))

        flex_bid_list_filtered = [item for item in flex_bid_list if item[1] != 0]

        if not flex_bid_list_filtered:
            return 0,0
        else:
            cheapest_flex_bid = min(flex_bid_list_filtered, key=lambda x: x[2])
            if cheapest_flex_bid[0] == "CaseI":
                SectionModelFlex = SectionModelFlex_I.copy()
                flexSection = flexSectionI.copy()
                # print("RawMill and CementMill Flex")
                return flexAmountI, BidI
            else:
                if cheapest_flex_bid[0] == "CaseII":
                    SectionModelFlex = SectionModelFlex_II.copy()
                    flexSection = flexSectionII.copy()
                    # print("RawMill Flex")
                    return flexAmountII, BidII
                else:
                    SectionModelFlex = SectionModelFlex_III.copy()
                    flexSection = flexSectionIII.copy()
                    # print("CementMill Flex")
                    return flexAmountIII, BidIII



           



        
            

                    

            

 


    
    def calculateBidEOM(self, t):
        BidsEOM = {}
        OptSegment = t // self.segment

        # calculate baseline bids
        if t % self.segment == 0:
            self.resultsSegment_all = self.calculateBaseline(t)
            

        
        BidsEOM['bidQuantity_plan'] = self.resultsSegment_all["el_cons_total"][t]
        BidsEOM['bidPrice_plan'] = 3000 # forecast wird erwartet, deswegen wird teuer in den Markt geboten
    
        # calculate flexibility bids

        BidsEOM['bidQuantity_flex'], BidsEOM['bidPrice_flex'] = self.calculateFlexBids(t) 


    
        
        return BidsEOM


    
                    

    def checkAvailability(self, t):
        pass
 

   

