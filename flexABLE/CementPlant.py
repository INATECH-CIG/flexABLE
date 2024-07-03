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
                 minPowerRawMill = 150,
                 maxPowerRawMill = 150,
                 minPowerKiln = 130,
                 maxPowerKiln = 130,
                 minPowerCementMill = 220,
                 maxPowerCementMill = 220,
                 maxCapRawMealSilo = 22000,
                 maxCapClinkerDome = 22000,
                 elConsRawMill = 23, # electricity consumption of raw mill per ton
                 elConsKiln = 30, # electricity consumption of kiln per ton
                 elConsCementMill = 40, # electricity consumption of cement mill per ton
                 node = 'Bus_DE',
                 world = None,
                 yearlyProductionGoal = 21000,
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
                # self.resultsSegment_all.to_csv(f'output/2016example/CementPlant/prod_opt_{self.world.currstep}_before.csv', index=True) 
                self.resultsSegment_all.iloc[self.world.currstep:self.world.currstep+timestampsSectionFlex+1] = SectionModelFlex[-(timestampsSectionFlex+1):].reset_index(drop=True)
                # self.resultsSegment_all.to_csv(f'output/2016example/CementPlant/prod_opt_{self.world.currstep}after.csv', index=True)

 

                self.slagFlex = sum(SectionModelFlex["slag"])

                self.updateProductionGoal(self.slagFlex, self.world.currstep)

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


        # self.resultsSegment.to_csv(f'output/2016example/CementPlant/prod_opt_{OptSegment}.csv', index=True)

        self.slag.append(sum(self.resultsSegment["slag"]))
        self.updateProductionGoal(self.slag[-1],t)

        
        return self.resultsSegment_all




    def calculateFlexBids(self, t): 

        global SectionModelFlex
        global timestampsSectionFlex

        SectionModelFlex = pd.DataFrame()
        
        # check if raw_mill can be turned off
        if t > 16 and self.resultsSegment_all["raw_meal_silo"][t-1] >= self.maxPowerKiln/self.rawMillClinkerFactor and self.resultsSegment_all["raw_mill_start"][t-16:t].sum() == 0 and self.resultsSegment_all["raw_mill_on"][t] == 1:
            RawMillFlex = True
        else:
            RawMillFlex = False

        # check if cement_mill can be turned off
        if t > 16 and self.resultsSegment_all["clinker_dome"][t] + self.minPowerKiln <= self.maxCapClinkerDome and self.resultsSegment_all["cement_mill_start"][t-16:t].sum() == 0 and self.resultsSegment_all["cement_mill_on"][t] == 1:
            CementMillFlex = True
        else:
            CementMillFlex = False


        # set default values for price and amount
        flexAmountI = 0
        flexPriceI = 0

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
            logging.debug(t, "CementMillFlex and RawMillFlex ------------------------------------------")
            flexAmountI = int(flexSection["el_cons_raw_mill"][flexSection.index[-1]]) + int(flexSection["el_cons_cement_mill"][flexSection.index[-1]])

            # cement mill
            flexSection["clinker_dome"][flexSection.index[-1]] = flexSection["clinker_dome"][flexSection.index[-1]] + flexSection["input_cement_mill"][flexSection.index[-1]]
            flexSection["input_cement_mill"][flexSection.index[-1]] = 0
            flexSection["output_cement_mill"][flexSection.index[-1]] = 0
            flexSection["el_cons_cement_mill"][flexSection.index[-1]] = 0
            flexSection["cement_mill_on"][flexSection.index[-1]] = 0
            if flexSection["cement_mill_stop"].iloc[-4:-1].sum() == 1:
                flexSection["cement_mill_shut_down"][flexSection.index[-1]] = 1
                if flexSection["cement_mill_shut_down_change"][flexSection.index[-4]] == 1:
                    flexSection["cement_mill_shut_down_change"][flexSection.index[-1]] = 0
            else:
                if flexSection["cement_mill_start"][flexSection.index[-1]] == 1:
                    flexSection["cement_mill_stop"][flexSection.index[-1]] = 0
                    flexSection["cement_mill_shut_down"][flexSection.index[-1]] = 0
                else:
                    flexSection["cement_mill_stop"][flexSection.index[-1]] = 1
                    flexSection["cement_mill_shut_down"][flexSection.index[-1]] = 1
            flexSection["cement_mill_start"][flexSection.index[-1]] = 0
            flexSection["cement_mill_shut_down_change"][flexSection.index[-1]] = 1
            
            # raw mill
            flexSection["raw_meal_silo"][flexSection.index[-1]] = flexSection["raw_meal_silo"][flexSection.index[-1]] - flexSection["output_raw_mill"][flexSection.index[-1]]
            flexSection["output_raw_mill"][flexSection.index[-1]] = 0
            flexSection["el_cons_raw_mill"][flexSection.index[-1]] = 0
            flexSection["raw_mill_on"][flexSection.index[-1]] = 0
            if flexSection["raw_mill_stop"].iloc[-4:-1].sum() == 1:
                flexSection["raw_mill_shut_down"][flexSection.index[-1]] = 1
                if flexSection["raw_mill_shut_down_change"][flexSection.index[-4]] == 1:
                    flexSection["raw_mill_shut_down_change"][flexSection.index[-1]] = 0
            else:
                if flexSection["raw_mill_start"][flexSection.index[-1]] == 1:
                    flexSection["raw_mill_stop"][flexSection.index[-1]] = 0
                    flexSection["raw_mill_shut_down"][flexSection.index[-1]] = 0
                else:
                    flexSection["raw_mill_stop"][flexSection.index[-1]] = 1
                    flexSection["raw_mill_shut_down"][flexSection.index[-1]] = 1
            flexSection["raw_mill_start"][flexSection.index[-1]] = 0
            flexSection["raw_mill_shut_down_change"][flexSection.index[-1]] = 1

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
                previousSection = flexSection,
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

            SectionModelFlex = SectionModelFlex_RawMill_CementMill[0].copy()



            # production costs old and new

            if t <= self.Tprevious:
                startFlex_cost = 0
            else:
                startFlex_cost = startFlex
            #Nötig weil: Wenn man sonst t<= self.Tprecios hat, ist startFlex=1, somit fehlt der index 0 zu Berechnung der Kosten

            productionCostSegmentOld = sum([self.resultsSegment_all["el_cons_total"].iloc[i] * abs(self.dicPFC[i]) for i in range(startFlex_cost, t + timestampsSectionFlex+1)]) 
            productionCostSegementNew = sum([SectionModelFlex["el_cons_total"].iloc[i] * abs(self.dicPFC[startFlex_cost+i]) for i in range(0, len(SectionModelFlex))])


            return flexAmountI, flexPriceI
        else:
            if RawMillFlex == True:
                logging.debug(t, "RawMillFlex")
                flexAmountI = int(flexSection["el_cons_raw_mill"][flexSection.index[-1]])
                
                flexSection["raw_meal_silo"][flexSection.index[-1]] = flexSection["raw_meal_silo"][flexSection.index[-1]] - flexSection["output_raw_mill"][flexSection.index[-1]]
                flexSection["output_raw_mill"][flexSection.index[-1]] = 0
                flexSection["el_cons_raw_mill"][flexSection.index[-1]] = 0
                flexSection["raw_mill_on"][flexSection.index[-1]] = 0
                if flexSection["raw_mill_stop"].iloc[-4:-1].sum() == 1:
                    flexSection["raw_mill_shut_down"][flexSection.index[-1]] = 1
                    if flexSection["raw_mill_shut_down_change"][flexSection.index[-4]] == 1:
                        flexSection["raw_mill_shut_down_change"][flexSection.index[-1]] = 0
                else:
                    if flexSection["raw_mill_start"][flexSection.index[-1]] == 1:
                        flexSection["raw_mill_stop"][flexSection.index[-1]] = 0
                        flexSection["raw_mill_shut_down"][flexSection.index[-1]] = 0
                    else:
                        flexSection["raw_mill_stop"][flexSection.index[-1]] = 1
                        flexSection["raw_mill_shut_down"][flexSection.index[-1]] = 1
                flexSection["raw_mill_start"][flexSection.index[-1]] = 0
                flexSection["raw_mill_shut_down_change"][flexSection.index[-1]] = 1

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
                    previousSection = flexSection,
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

                SectionModelFlex = SectionModelFlex_RawMill[0].copy()



                if t <= self.Tprevious:
                    startFlex_cost = 0
                else:
                    startFlex_cost = startFlex
                #Nötig weil: Wenn man sonst t<= self.Tprecios hat, ist startFlex=1, somit fehlt der index 0 zu Berechnung der Kosten

                productionCostSegmentOld = sum([self.resultsSegment_all["el_cons_total"].iloc[i] * abs(self.dicPFC[i]) for i in range(startFlex_cost, t + timestampsSectionFlex+1)]) 
                productionCostSegementNew = sum([SectionModelFlex["el_cons_total"].iloc[i] * abs(self.dicPFC[startFlex_cost+i]) for i in range(0, len(SectionModelFlex))])

                flexPriceI = int(productionCostSegmentOld - productionCostSegementNew)

                return flexAmountI, flexPriceI
            else:
                if CementMillFlex == True:

                    logging.debug(t, "CementMillFlex")
                    flexAmountI = int(flexSection["el_cons_cement_mill"][flexSection.index[-1]])

                    flexSection["clinker_dome"][flexSection.index[-1]] = flexSection["clinker_dome"][flexSection.index[-1]] + flexSection["input_cement_mill"][flexSection.index[-1]]
                    flexSection["input_cement_mill"][flexSection.index[-1]] = 0
                    flexSection["output_cement_mill"][flexSection.index[-1]] = 0
                    flexSection["el_cons_cement_mill"][flexSection.index[-1]] = 0
                    flexSection["cement_mill_on"][flexSection.index[-1]] = 0

                    if flexSection["cement_mill_start"][flexSection.index[-1]] == 1:
                        flexSection["cement_mill_start"][flexSection.index[-1]] = 0
                    else:
                        flexSection["cement_mill_start"][flexSection.index[-1]] = 0
                        flexSection["cement_mill_stop"][flexSection.index[-1]] = 1
                    if flexSection["output_cement_mill"].iloc[-5:-1].sum() == 0:
                        flexSection["cement_mill_shut_down"][flexSection.index[-1]] = 0
                        if flexSection["cement_mill_shut_down_change"].iloc[-5:-1].sum() == 4:
                            flexSection["cement_mill_shut_down_change"][flexSection.index[-1]] = 0
                        else:
                            flexSection["cement_mill_shut_down_change"][flexSection.index[-1]] = 1

                    # flexSection.to_csv(f'output/2016example/CementPlant/flexSection_{t}.csv', index=True)

                    if timestampsPreviousSectionFlex >= self.Tprevious:
                        addCount = 1
                    else:
                        addCount = 0

                # benötigt man, beispiel: t = 26, timestampsPreviosuSection = 24 --> untere Grenze des PFC abrufs wird 2, aber t previous geht eigentlich von 3-26 (24 einheiten)

                    SectionModelFlex_CementMill = self.cementOptBase(
                        optHorizon = timestampsSectionFlex, 
                        timestampsPreviousSection = timestampsPreviousSectionFlex, 
                        PFC = [abs(value) for value in self.dicPFC[(t-timestampsPreviousSectionFlex+addCount):(t+timestampsSectionFlex+1)]], #erstmal nur positive um Überprodukion zu verhindern
                        previousSection = flexSection,
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
                    
                    SectionModelFlex = SectionModelFlex_CementMill[0].copy()
                    
                    # production costs old and new

                    if t <= self.Tprevious:
                        startFlex_cost = 0
                    else:
                        startFlex_cost = startFlex
                    #Nötig weil: Wenn man sonst t<= self.Tprecios hat, ist startFlex=1, somit fehlt der index 0 zu Berechnung der Kosten

                    productionCostSegmentOld = sum([self.resultsSegment_all["el_cons_total"].iloc[i] * abs(self.dicPFC[i]) for i in range(startFlex_cost, t + timestampsSectionFlex+1)]) 
                    productionCostSegementNew = sum([SectionModelFlex["el_cons_total"].iloc[i] * abs(self.dicPFC[startFlex_cost+i]) for i in range(0, len(SectionModelFlex))])

                    flexPriceI = int(productionCostSegmentOld - productionCostSegementNew)

                    return flexAmountI, flexPriceI
                else:
                    return 0, 0
                    

            

 


    
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
 

   

