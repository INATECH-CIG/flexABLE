from .auxFunc import initializer
from .bid import Bid
import pandas as pd
from .electrolyzerOptimization import elecOptBase
import logging



class ElectrolyzerPlant():
    

    @initializer
    def __init__(self,  # HERE: Müssen noch angepasst werden
                 agent = None,
                 node = 'Bus_DE',
                 world = None,
                 technology = "industry",
                 minLoad = 0.1, #%
                 maxLoad = 1.2, #%
                 Capacity = 100, #[MW] installed capacity
                 effElec = 0.7, #electrolyzer efficiency[%]
                 minDownTime  = 2, #minimum downtime,
                 coldStartUpCost = 50, # Euro per MW installed capacity,
                 maxAllowedColdStartups = 3000, #yearly allowed max cold startups,
                 standbyCons = 0.05, #% of installed capacity 
                 comprCons = 0.0012, #MWh/kg  compressor specific consumptin
                 maxSOC = 2000, #Kg
                 slagCost = 1000000, #Euro per kg slag
                 **kwargs):
        
        # get necessary functions
        self.elecOptBase = elecOptBase

        # bid status parameters
        self.sentBids=[]

        self.dictCapacity = {n:None for n in self.world.snapshots}
        self.dictCapacity[-1] = 0


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
        self.section = 32 # Describes the length of a section for the production goal optimization (non detailed)
        self.Tprevious = 24
        self.reproduction_time = 1

        self.resultsSegment = pd.DataFrame()
        self.resultsSegment_all = pd.DataFrame()
        self.previousSegment = pd.DataFrame()
        self.productionGoalSegment = []
        

        self.industrial_demand = pd.read_csv("input/2016/electrolyzer_demand.csv", index_col=0, sep=';')
        self.industrial_demand = list(self.industrial_demand["Iron_steel"])


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

    

            if round(self.confQtyEOM[self.world.currstep],2) != round(self.resultsSegment_all.iloc[self.world.currstep]["optimalBidamount"],2):
                print("Flex bid accepted at time: ", self.world.currstep)
                self.resultsSegment_all.to_csv(f'output/2016example/Electrolyzer/prod_opt_{self.world.currstep}_before.csv', index=True)
                SectionModelFlex.to_csv(f'output/2016example/Electrolyzer/flexSection_{self.world.currstep}.csv', index=True)
                self.resultsSegment_all.iloc[self.world.currstep:self.world.currstep+timestampsSectionFlex+1] = SectionModelFlex[-(timestampsSectionFlex+1):].reset_index(drop=True)
                self.resultsSegment_all.to_csv(f'output/2016example/Electrolyzer/prod_opt_{self.world.currstep}after.csv', index=True)




                


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

    def calculateBaseline(self, t):  #HERE: Alles muss noch angepasst werden
        logging.debug("Optimiere Baseline für Segment: ", t//self.segment)
        #calculate the baseline based on the PFC for given length of segment
        OptSegment = t // self.segment
        
        if t == 0:
                # set parameter and determine production goal
                self.previousSegment = pd.DataFrame()
                Tprevious = 0
                SOCStart = 0
                maxAllowedColdStartups_horizon = 3000
       
        else:
            # get values from previous segment
            self.previousSegment = self.resultsSegment_all.iloc[t-self.Tprevious:t].reset_index(drop=True)
            Tprevious = self.Tprevious 
            SOCStart = self.resultsSegment_all["currentSOC"].iloc[t-self.Tprevious-1]
            maxAllowedColdStartups_horizon = sum(self.resultsSegment_all["isColdStarted"].iloc[t-self.segment:t]) + 3000



        # optimize segment
        self.resultsSegment = self.elecOptBase(
            optHorizon = self.segment, 
            timestampsPreviousSection = Tprevious,
            previousSection = self.previousSegment,
            PFC = [abs(value) for value in self.dicPFC[(t-Tprevious):(t+self.segment)]], #erstmal nur positive um Überprodukion zu verhindern
            minLoad=0.1,
            maxLoad=1.2,
            Capacity=100,
            effElec=0.7,
            minDownTime=0.5,
            coldStartUpCost=50,
            maxAllowedColdStartups=maxAllowedColdStartups_horizon,
            standbyCons=0.05,
            comprCons=0.0012,
            maxSOC=2000,
            industry_demand = self.industrial_demand[(t-Tprevious):(t+self.segment+1)],
            slagCost = self.slagCost)[0]
        
        self.resultsSegment.to_csv(f'output/2016example/Electrolyzer/prod_opt_{t}.csv', index=True)
        
        self.resultsSegment_all = pd.concat([self.resultsSegment_all[0:t-Tprevious], self.resultsSegment], ignore_index=True)

        
        
        return self.resultsSegment_all
    
    def calculateFlexBids(self, t):
        global SectionModelFlex
        global timestampsSectionFlex

        

        # check if flex bid is possible (on to standby - standyb to off is neglected)

        if t > 0 and self.resultsSegment_all["isRunning"][t] == 1 and self.resultsSegment_all["currentSOC"][t-1] >= self.resultsSegment_all["H2Demand"][t]:
            elecFlex = True
            #calculate standby consumption
            standbyCons = self.Capacity * self.standbyCons
        else:
            elecFlex = False

        
        # set optimization horizon

        timestampsSectionFlex = self.segment - t % self.segment - 1            # nur für restzeit in diesem segment
        
        if t < self.Tprevious:
            timestampsPreviousSectionFlex = t 
        else:
            timestampsPreviousSectionFlex = self.Tprevious 


        startFlex = t - timestampsPreviousSectionFlex + 1
        endFlex = t + 1

        

        flexSection = self.resultsSegment_all.iloc[startFlex:endFlex].reset_index(drop=True)

        if elecFlex is True:
            flexSectionI = flexSection.copy() # just in case, if second flex option is implemented
   
            flexAmount = flexSectionI["elecCons"][flexSectionI.index[-1]] - standbyCons

            flexSectionI["optimalBidamount"][flexSectionI.index[-1]] = standbyCons
            flexSectionI["elecCons"][flexSectionI.index[-1]] = standbyCons
            flexSectionI["elecStandByCons"][flexSectionI.index[-1]] = standbyCons
            flexSectionI["comprCons"][flexSectionI.index[-1]] = 0
            flexSectionI["prodH2"][flexSectionI.index[-1]] = 0
            flexSectionI["elecToPlantUse_kg"][flexSectionI.index[-1]] = 0
            flexSectionI["elecToStorage_kg"][flexSectionI.index[-1]] = 0
            flexSectionI["storageToPlantUse_kg"][flexSectionI.index[-1]] = flexSectionI["H2Demand"][flexSectionI.index[-1]]
            flexSectionI["currentSOC"][flexSectionI.index[-1]] = flexSectionI["currentSOC"][flexSectionI.index[-2]] - flexSectionI["H2Demand"][flexSectionI.index[-1]]
            flexSectionI["isRunning"][flexSectionI.index[-1]] = 0
            flexSectionI["isStandBy"][flexSectionI.index[-1]] = 1
            flexSectionI["isIdle"][flexSectionI.index[-1]] = 0
            flexSectionI["isColdStarted"][flexSectionI.index[-1]] = 0

            if timestampsPreviousSectionFlex >= self.Tprevious:
                addCount = 1
            else:
                addCount = 0

            SectionModelFlex = self.elecOptBase(
                optHorizon = timestampsSectionFlex, 
                timestampsPreviousSection = timestampsPreviousSectionFlex,
                previousSection = flexSectionI,
                PFC = [abs(value) for value in self.dicPFC[(t-timestampsPreviousSectionFlex+addCount):(t+timestampsSectionFlex+1)]], #erstmal nur positive um Überprodukion zu verhindern
                minLoad=0.1,
                maxLoad=1.2,
                Capacity=100,
                effElec=0.7,
                minDownTime=0.5,
                coldStartUpCost=50,
                maxAllowedColdStartups=3000,
                standbyCons=0.05,
                comprCons=0.0012,
                maxSOC=2000,
                industry_demand = self.industrial_demand[startFlex:(t+timestampsSectionFlex+1)],
                slagCost = self.slagCost)[0]
        
            # production costs old and new

            if t <= self.Tprevious:
                startFlex_cost = 0
            else:
                startFlex_cost = startFlex
            #Nötig weil: Wenn man sonst t<= self.Tprecios hat, ist startFlex=1, somit fehlt der index 0 zu Berechnung der Kosten

            if t == 86:
                print("STOP")

            productionCostSegmentOld = sum([(self.resultsSegment_all["optimalBidamount"].iloc[i] * abs(self.dicPFC[i]) + self.resultsSegment_all["isColdStarted"].iloc[i] * self.coldStartUpCost + self.resultsSegment_all['slag'].iloc[i] * self.slagCost) for i in range(startFlex_cost, t + timestampsSectionFlex+1)]) 
            productionCostSegementNew = sum([(SectionModelFlex["optimalBidamount"].iloc[i] * abs(self.dicPFC[startFlex_cost+i]) + SectionModelFlex["isColdStarted"].iloc[i] * self.coldStartUpCost + self.resultsSegment_all['slag'].iloc[i] * self.slagCost) for i in range(0, len(SectionModelFlex))])
            print(t, "Production cost old: ", productionCostSegmentOld
            , "Production cost new: ", productionCostSegementNew)


            flexPrice = int(productionCostSegementNew - productionCostSegmentOld)

            return flexAmount, flexPrice
        else:
            return 0, 0   



    def calculateBidEOM(self, t):
        BidsEOM = {}
        OptSegment = t // self.segment

        # calculate baseline bids
        if t % self.segment == 0:
            self.resultsSegment_all = self.calculateBaseline(t)
            

        
        BidsEOM['bidQuantity_plan'] = self.resultsSegment_all["optimalBidamount"][t]
        BidsEOM['bidPrice_plan'] = 3000 # forecast wird erwartet, deswegen wird teuer in den Markt geboten
    
        # calculate flexibility bids

        BidsEOM['bidQuantity_flex'], BidsEOM['bidPrice_flex'] = self.calculateFlexBids(t)


    
        
        return BidsEOM
    



    
    def checkAvailability(self, t):
        pass