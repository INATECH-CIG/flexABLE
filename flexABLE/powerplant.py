 # -*- coding: utf-8 -*-
"""
Created on Sun Apr  19 16:06:57 2020

@author: intgridnb-02
"""
from .auxFunc import initializer
from .bid import Bid
import random

class Powerplant():
    
    @initializer
    def __init__(self,agent=None,
                name='KKW ISAR 2',
                technology='nuclear',
                fuel='uranium',
                maxPower=1500,
                minPower=600,
                efficiency=0.3,
                rampUp=890,
                rampDown=890,
                variableCosts=10.3,
                hotStartCosts=140,
                warmStartCosts=140,
                coldStartCosts=140,
                minOperatingTime=72,
                minDowntime=10,
                heatExtraction=False,
                maxExtraction=0,
                heatingDistrict='BW',
                company='UNIPER',
                year=1988,
                node='Bus_DE',
                world=None,
                Redispatch=False,
                maxAvailability=None,
                emission=None):
        

        self.minDowntime /= self.world.dt          # This was added to consider dt 15 mins
        self.minOperatingTime /= self.world.dt     # This was added to consider dt 15 mins
        self.foresight = int(self.minDowntime)
        # bids status parameters
        self.dictCapacity = {n:0 for n in self.world.snapshots}
        self.dictCapacityMR = {n:(0,0) for n in self.world.snapshots}
        self.dictCapacityFlex = {n:(0,0) for n in self.world.snapshots}
        self.dictCapacity[-1] = self.maxPower/2
        self.confQtyCRM_neg = {n:0 for n in self.world.snapshots}
        self.confQtyCRM_pos = {n:0 for n in self.world.snapshots}
        self.confQtyDHM_steam = {n:0 for n in self.world.snapshots}
        self.powerLoss_CHP = {n:0 for n in self.world.snapshots}
        self.maxExtraction /= self.world.dt
        # performance parameter for ML
        self.performance = 0
        self.emission = self.world.emissionFactors[self.fuel] if self.emission is None else self.emission
        
        self.hotStartCosts*=self.maxPower
        self.warmStartCosts*=self.maxPower
        self.coldStartCosts*=self.maxPower
        # Unit status parameters
        self.meanMarketSuccess = 0
        self.marketSuccess = [0]
        self.currentDowntime = self.minDowntime # Keeps track of the powerplant if it reached the minimum shutdown time
        self.currentStatus = 0 # 0 means the power plant is currently off, 1 means it is on
        self.averageDownTime = [0] # average downtime during the simulation
        self.currentCapacity = 0
        self.sentBids=[]
        if maxAvailability is None:
            self.maxAvailability = [self.maxPower for _ in self.world.snapshots]
        else:
            self.maxAvailability = maxAvailability
    def step(self):
        # Calculate the sum of confirmed bids
        self.dictCapacity[self.world.currstep] = 0
        for bid in self.sentBids:
            if 'mrEOM' in bid.ID or 'flexEOM' in bid.ID:
                self.dictCapacity[self.world.currstep] += bid.confirmedAmount
                if 'mrEOM' in bid.ID:
                    self.dictCapacityMR[self.world.currstep] = (bid.confirmedAmount, bid.price)
                else:
                    self.dictCapacityFlex[self.world.currstep] = (bid.confirmedAmount, bid.price)
        
        if self.world.currstep % 16:
            self.confQtyCRM_pos[self.world.currstep] = self.confQtyCRM_pos[self.world.currstep-1]
            self.confQtyCRM_neg[self.world.currstep] = self.confQtyCRM_neg[self.world.currstep-1]
            
        # self.dictCapacity[self.world.currstep] += self.confQtyCRM_pos[self.world.currstep]
        # self.dictCapacity[self.world.currstep] -= self.confQtyCRM_neg[self.world.currstep]
        #self.dictCapacity[self.world.currstep] += self.powerLoss_CHP[self.world.currstep]
        if self.dictCapacity[self.world.currstep] < 0:
            self.dictCapacity[self.world.currstep] = 0
            self.performance -=2

        # Calculates market success
        if self.dictCapacity[self.world.currstep] > 0:
            self.marketSuccess[-1] += 1
        else:
            if self.marketSuccess[-1] !=0:
                self.meanMarketSuccess = sum(self.marketSuccess)/len(self.marketSuccess)
                self.marketSuccess.append(0)
            
        # Checks if the powerplant is shutdown and whether it can start-up
        if self.currentStatus==0:
            #Power plant is off
            if self.dictCapacity[self.world.currstep - 1] == 0:
                # Adds to the counter of the number of steps it was off
                self.currentDowntime +=1
                
            if self.currentDowntime >= self.minDowntime:
                # Powerplant can turn on
                if self.dictCapacity[self.world.currstep]>=self.minPower:
                    self.averageDownTime.append(self.currentDowntime)
                    self.currentDowntime = 0
                    self.currentStatus = 1

                else:
                    self.dictCapacity[self.world.currstep] = 0
                    self.currentStatus = 0
        else:
            if (self.dictCapacity[self.world.currstep] < self.minPower):
                self.currentStatus = 0
                self.currentDowntime = 1
            else:
                self.currentStatus = 1

        
        # self.world.ResultsWriter.writeCapacity(self,self.world.currstep, writeBidsInDB=True)
        # self.world.ResultsWriter.writeBids(self,self.world.currstep)
        self.sentBids=[]
    def checkAvailability(self,t):
        self.maxPower = self.maxAvailability[t]
    def feedback(self, bid):
        if bid.status == "Confirmed":
            if 'CRMPosDem' in bid.ID:
                self.confQtyCRM_pos.update({self.world.currstep+_:bid.confirmedAmount for _ in range(16)})
            if 'CRMNegDem' in bid.ID:
                self.confQtyCRM_neg.update({self.world.currstep+_:bid.confirmedAmount for _ in range(16)})
            if 'steam' in bid.ID:
                self.confQtyDHM_steam[self.world.currstep] = bid.confirmedAmount
            self.performance+=1
        elif bid.status =="PartiallyConfirmed":
            if 'CRMPosDem' in bid.ID:
                self.confQtyCRM_pos.update({self.world.currstep+_:bid.confirmedAmount for _ in range(16)})
            if 'CRMNegDem' in bid.ID:
                self.confQtyCRM_neg.update({self.world.currstep+_:bid.confirmedAmount for _ in range(16)})
            if 'steam' in bid.ID:
                self.confQtyDHM_steam[self.world.currstep] = bid.confirmedAmount
            self.performance+=0.5
        else:
            self.performance-=2
        if 'steam' in bid.ID:
            self.powerLossFPP(self.world.currstep, bid)
        self.sentBids.append(bid)

    def powerLossFPP(self, t, bid):
        if bid.confirmedAmount > 0:
            if self.technology in ['lignite', 'hard coal', 'combined cycle gas turbine']:
                powerLoss = (self.maxPower - ((-0.12 * min((bid.confirmedAmount) / self.maxPower, 1.25) + 1) * self.maxPower))
                # über ein Wärme-Strom-Verhältnis von 1.2 hinaus setzt die Zusatzfeuerung ein
                self.powerLoss_CHP[t] = powerLoss

    def requestBid(self, t, market="EOM"):
        bids = []
        if self.maxPower == 0:
            return bids
        if market=="EOM":
            bidQuantity_mr, bidPrice_mr, bidQuantity_flex, bidPrice_flex = self.calculateBidEOM(t)
            bids.append(Bid(issuer = self,
                            ID = "{}_mrEOM".format(self.name,t),
                            price = bidPrice_mr,
                            amount = bidQuantity_mr,
                            status = "Sent",
                            bidType = "Supply",
                            node = self.node))
            bids.append(Bid(issuer = self,
                            ID = "{}_flexEOM".format(self.name,t),
                            price = bidPrice_flex,
                            amount = bidQuantity_flex,
                            status = "Sent",
                            bidType = "Supply",
                            node = self.node))
        elif market=="DHM": 
            bids.extend(self.calculateBidDHM(t))

        elif market=="posCRMDemand": 
            bids.extend(self.calculatingBidsFPP_CRM_pos(t))

        elif market=="negCRMDemand":
            bids.extend(self.calculatingBidsFPP_CRM_neg(t))
            
            
        return bids
    
    def marginalCostsFPP(self, t, efficiencyDependence, passedCapacity):
        """
        Parameters
        ----------
        t : timestamp
            Defines the fuel price and CO2 prices at that timestep.
        efficiencyDependence : Bool
            DESCRIPTION.
        passedCapacity : float
            Specified the current power level, required to .

        Returns
        -------
        marginalCosts : TYPE
            DESCRIPTION.
        """
    
        fuelPrice = self.world.fuelPrices[self.fuel][t]
        co2price = self.world.fuelPrices['co2'][t]
    
        emissionFactor = self.world.emissionFactors[self.fuel]
        if t > 0:
            if passedCapacity > 0:
                currentCapacity = passedCapacity
            elif self.dictCapacity[t-1] >= self.minPower:
                currentCapacity = self.dictCapacity[t-1]
            else:
                currentCapacity = self.maxPower
        else:
            currentCapacity = self.maxPower
    
        # Wirkungsgradunabhängige Grenzkosten
        marginalCosts = (fuelPrice / self.efficiency) + (co2price * (self.emission / self.efficiency)) + self.variableCosts
    
        # Partial load efficiency dependent marginal costs
        # The values has to be rechecked -> RQ 14.04.2020
        if efficiencyDependence:
    
            capacityRatio = currentCapacity / self.maxPower
    
            if self.fuel in ['lignite', 'hard coal']:
                etaLoss = 0.095859 * (capacityRatio ** 4) - 0.356010 * (capacityRatio ** 3) \
                          + 0.532948 * (capacityRatio ** 2) - 0.447059 * capacityRatio + 0.174262
            elif self.fuel == 'combined cycle gas turbine':
                etaLoss = 0.178749 * (capacityRatio ** 4) - 0.653192 * (capacityRatio ** 3) \
                          + 0.964704 * (capacityRatio ** 2) - 0.805845 * capacityRatio + 0.315584
            elif self.fuel == 'open cycle gas turbine':
                etaLoss = 0.485049 * (capacityRatio ** 4) - 1.540723 * (capacityRatio ** 3) \
                          + 1.899607 * (capacityRatio ** 2) - 1.251502 * capacityRatio + 0.407569
            else:
                etaLoss = 0

            marginalCosts = round(
                (fuelPrice / (self.efficiency - etaLoss)) + (co2price * (self.emission / (self.efficiency - etaLoss))) + self.variableCosts, 2)
    
        return marginalCosts
    


    def calculateBidEOM(self, t):
        '''
        This is currently hard coded, but should be removed into input files
        '''
        bidQuantity_mr,bidPrice_mr, bidQuantity_flex, bidPrice_flex = 0,0,0,0
        maxDowntime_hotStart = 32 # represents 8h in 15min res, for source go back to Thomas diss
        maxDowntime_warmStart = 192
        if ((self.currentStatus) or (not(self.currentStatus) and (self.currentDowntime >= self.minDowntime))):
            # =============================================================================
            # Powerplant is either on, or is able to turn on
            # Calculating possible bid amount          
            # =============================================================================
            mustRunPowerFPP = (max(self.dictCapacity[t-1] - self.rampDown + self.confQtyCRM_neg[t], self.minPower + self.confQtyCRM_neg[t]))
            bidQuantity_mr = mustRunPowerFPP if mustRunPowerFPP > 0 else 0
            
            if bidQuantity_mr >= self.world.minBidEOM:
                flexPowerFPP = min(self.dictCapacity[t-1] + self.rampUp - self.confQtyCRM_pos[t] - mustRunPowerFPP,
                                   self.maxPower - self.powerLoss_CHP[t] - self.confQtyCRM_pos[t] - mustRunPowerFPP)
                bidQuantity_flex = flexPowerFPP if flexPowerFPP > 0 else 0
                
                totalOutputCapacity = mustRunPowerFPP + flexPowerFPP
            else:
                print(self.name)
            # =============================================================================
            # Calculating possible price       
            # =============================================================================
            if not(self.currentStatus):
                # The powerplant is currently off and calculates a startup markup as an extra
                # to the marginal cost
                # Calculating the average uninterrupted operating period
                averageOperatingTime = max(self.meanMarketSuccess, self.minOperatingTime, 1) #1 prevents division by 0

                
                if self.currentDowntime < maxDowntime_hotStart:
                    startingCosts = (self.hotStartCosts)
                elif self.currentDowntime >= maxDowntime_hotStart and self.currentDowntime < maxDowntime_warmStart:
                    startingCosts = (self.warmStartCosts)
                else:
                    startingCosts = (self.coldStartCosts)
                
                # start-up markup   
                markup = startingCosts / averageOperatingTime / bidQuantity_mr
                
                marginalCosts_eta = self.marginalCostsFPP(t, 1, mustRunPowerFPP)
                
                
                bidPrice_mr = min(marginalCosts_eta + markup, 3000.12)
            else:
                '''
                Check the description provided by Thomas in last version, the average downtime is not available
                '''
                avgDT = max(self.minDowntime,1) # minDownTime is divided by 4 since it is given in 15 min resolution
                
                if avgDT < maxDowntime_hotStart:
                    startingCosts = (self.hotStartCosts)
                elif avgDT >= maxDowntime_hotStart and avgDT < maxDowntime_warmStart:
                    startingCosts = (self.warmStartCosts)
                else:
                    startingCosts = (self.coldStartCosts)
                # restart markup
                priceReduction_restart = startingCosts / avgDT / abs(bidQuantity_mr)
                
                if self.confQtyDHM_steam[t] > 0:
                    eqHeatGenCosts = (self.confQtyDHM_steam[t] * (self.world.fuelPrices['natural gas'][t]/ 0.9)) / abs(bidQuantity_mr)
                else:
                    eqHeatGenCosts = 0.00

                marginalCosts_eta = self.marginalCostsFPP(t, 1, totalOutputCapacity)
                
                if self.specificRevenueEOM(t, self.foresight, marginalCosts_eta, 'all') >=0:
                    if self.world.dictPFC[t] < marginalCosts_eta:
                        marginalCosts_eta=0

                bidPrice_mr = max(-priceReduction_restart - eqHeatGenCosts + marginalCosts_eta, -2999.00)

            
            if self.confQtyDHM_steam[t] > 0:
                powerLossRatio = round((self.powerLoss_CHP[t] / (self.confQtyDHM_steam[t])), 2)
            else:
                powerLossRatio = 0
                
            # Flex-bid price formulation
            bidPrice_flex = (1 - powerLossRatio) * self.marginalCostsFPP(t, 1, totalOutputCapacity) if abs(bidQuantity_flex) > 0 else 0.00

        return (bidQuantity_mr,bidPrice_mr, bidQuantity_flex, bidPrice_flex)

    def calculateBidDHM(self, t, dt=1):
        bidsDHM = []
        # =========================================================================
        #     -> This filter can be applied to the list before it is sent to loop
        #     if cogeneration == "yes" and maxExtraction > 0:
        # =========================================================================
        if ((self.currentStatus) or (not(self.currentStatus) and (self.currentDowntime >= self.minDowntime))):
            elCapacity = max(self.dictCapacity[t-1], self.minPower)
            # Steam power plants
            if self.technology in ['lignite', 'hard coal', 'combined cycle gas turbine']:
    
                # Steam extraction: Twice the amount of output electricity, limited to 1.2 times the normalized nominal electricity output
                thPower_process = min(elCapacity * 2, self.maxPower * 1.2)
                heatExtraction_process = thPower_process
    
                # Auxiliary firing on plant site
                heatExtraction_auxFiring = max(self.maxExtraction - (self.maxPower * 1.2), 0)
                
                # heat to power-ratio
                heat_to_power_ratio = heatExtraction_process / (elCapacity)
    
                # Evaluation of power loss ratio
                if thPower_process > 0:
                    if self.technology in ['lignite', 'hard coal']:
                        powerLossRatio = 1.018222848803E-13 *(heat_to_power_ratio **6) \
                                         - 5.46518761407738E-11 * (heat_to_power_ratio **5) \
                                         + 1.04891194269589E-08 * (heat_to_power_ratio**4) \
                                         - 8.90214921246953E-07 * (heat_to_power_ratio **3) \
                                         + 0.0000392158875692142 * (heat_to_power_ratio **2) \
                                         - 0.000921199029083447 * heat_to_power_ratio \
                                         + 0.156897578188381
                    # CCGTs
                    else:
                        powerLossRatio = -0.0000026638327514537 * (heat_to_power_ratio **2) \
                                         + 0.00105199966687901 * heat_to_power_ratio \
                                         + 0.108494099491879
    
                else:
                    powerLossRatio = 0
    
            # Open cycle gas turbine
            else:
                heatExtraction_process = elCapacity * 2
                heatExtraction_auxFiring = max(self.maxExtraction - (self.maxPower * 2), 0)
    
                heat_to_power_ratio = heatExtraction_process/(elCapacity)
    
                powerLossRatio = -0.0000026638327514537 * (heat_to_power_ratio ** 2) \
                                 + 0.00105199966687901 * heat_to_power_ratio \
                                 + 0.108494099491879
    
            # Evaluation of heat price (EUR/MWh)
            heatPrice_process = round(powerLossRatio * self.marginalCostsFPP(t,0,0), 2)
            heatPrice_auxFiring = round(self.world.fuelPrices['natural gas'][t] / 0.9, 2)

            # Eintragen der Wärmemarktgebote
            bidsDHM.append(Bid(issuer = self,
                               ID = "Bu{}t{}_steam".format(self.name,t),
                               price = heatPrice_process,
                               amount = heatExtraction_process,
                               status = "Sent",
                               bidType = "Supply",
                               node = self.node))
            bidsDHM.append(Bid(issuer = self,
                               ID = "Bu{}t{}_auxFi".format(self.name,t),
                               price = heatPrice_auxFiring,
                               amount = heatExtraction_auxFiring,
                               status = "Sent",
                               bidType = "Supply",
                               node = self.node))
        else:
            bidsDHM.append(Bid(issuer = self,
                               ID = "Bu{}t{}_steam".format(self.name,t),
                               price = 0,
                               amount = 0,
                               status = "Sent",
                               bidType = "Supply",
                               node = self.node))
            bidsDHM.append(Bid(issuer = self,
                               ID = "Bu{}t{}_auxFi".format(self.name,t),
                               price = 0,
                               amount = 0,
                               status = "Sent",
                               bidType = "Supply",
                               node = self.node))
    
        return bidsDHM

    def calculatingBidsFPP_CRM_pos(self, t):
        bidsCRM = []
    
        lastCapacity = self.dictCapacity[t-1]
        rampUpPower_BPM = ((1 / 3) * self.rampUp)

        # available power (pos. BP FPP)
        if  ((self.currentStatus) or (not(self.currentStatus) and (self.currentDowntime >= self.minDowntime))):
            availablePower_BP_pos = (min(self.maxPower - lastCapacity, rampUpPower_BPM))
        else:
            availablePower_BP_pos = 0

        # Gebotsmenge am Regelleistungsmarkt (pos. RL FPP)
        bidQuantityBPM_pos = availablePower_BP_pos if availablePower_BP_pos >= self.world.minBidCRM else 0

        if bidQuantityBPM_pos > 0:
            # Leistungspreis (pos. RL FPP)
            specificRevenueEOM_dtau = self.specificRevenueEOM(t, 16, self.marginalCostsFPP(t, 1, 0), 'all')
            if specificRevenueEOM_dtau >= 0:
                capacityPrice = specificRevenueEOM_dtau * bidQuantityBPM_pos
            else:
                capacityPrice = ((abs(specificRevenueEOM_dtau) * self.minPower) / bidQuantityBPM_pos)

            # Arbeitspreis (pos. RL FPP)
            energyPrice = self.marginalCostsFPP(t, 1, 0)

            # Gebot eintragen
            bidsCRM.append(Bid(issuer=self,
                               ID = "Bu{}t{}_CRMPosDem".format(self.name,t),
                               price = capacityPrice,
                               amount = bidQuantityBPM_pos,
                               energyPrice = energyPrice,
                               status = "Sent",
                               bidType = "Supply",
                               node = self.node))

        else:
            bidsCRM.append(Bid(issuer=self,
                               ID = "Bu{}t{}_CRMPosDem".format(self.name,t),
                               price = 0,
                               amount = 0,
                               energyPrice = 0,
                               status = "Sent",
                               bidType = "Supply",
                               node = self.node))
    
        return bidsCRM

    def calculatingBidsFPP_CRM_neg(self, t):
        bidsCRM = []
    
        lastCapacity = self.dictCapacity[t-1]
        rampDownPower_CRM = ((1 / 3) * self.rampDown)

        # Gebotsmenge
        if  ((self.currentStatus) or (not(self.currentStatus) and (self.currentDowntime >= self.minDowntime))):
            bidQtyCRM_neg = (min(lastCapacity - self.minPower, rampDownPower_CRM))
        else:
            bidQtyCRM_neg = 0

        if bidQtyCRM_neg > self.world.minBidCRM:

            # Leistungspreis
            specificRevenueEOM_dtau = self.specificRevenueEOM(t, 16, self.marginalCostsFPP(t, 1, 0), 'all')
            if specificRevenueEOM_dtau < 0 and bidQtyCRM_neg > 0:
                capacityPrice = round(((abs(specificRevenueEOM_dtau) * (self.minPower + bidQtyCRM_neg)) / bidQtyCRM_neg), 2)
            else:
                capacityPrice = 0.00

            # Arbeitspreis
            energyPrice = -self.marginalCostsFPP(t,  1, 0)

            # Gebot eintragen
            bidsCRM.append(Bid(issuer=self,
                               ID = "Bu{}t{}_CRMNegDem".format(self.name,t),
                               price = capacityPrice,
                               amount = bidQtyCRM_neg,
                               energyPrice = energyPrice,
                               status = "Sent",
                               bidType = "Supply",
                               node = self.node))
        else:
            bidsCRM.append(Bid(issuer=self,
                               ID = "Bu{}t{}_CRMNegDem".format(self.name,t),
                               price = 0,
                               amount = 0,
                               energyPrice = 0,
                               status = "Sent",
                               bidType = "Supply",
                               node = self.node))
        #bidsCRM = []
        return bidsCRM


    def specificRevenueEOM(self,t, foresight, marginalCosts, horizon):
        # listPFC = self.getPart_PFC(t, foresight)
        listPFC = []
        
            
        if t + foresight > len(self.world.dictPFC):
            listPFC = self.world.dictPFC[t:] + self.world.dictPFC[:t+foresight-len(self.world.dictPFC)]
        else:
            listPFC = self.world.dictPFC[t:t+foresight]
    
        if horizon == 'positive':
            specificRevenue_sum = round(sum([(marketPrice - marginalCosts) * self.world.dt for marketPrice
                                             in listPFC if marginalCosts < marketPrice]), 2)
        elif horizon == 'negative':
            specificRevenue_sum = round(sum([(marketPrice - marginalCosts) * self.world.dt for marketPrice
                                             in listPFC if marginalCosts > marketPrice]), 2)
        else:
            specificRevenue_sum = round(sum([(marketPrice - marginalCosts) * self.world.dt for marketPrice
                                             in listPFC]), 2)
            

        return specificRevenue_sum
    
    def getPart_PFC(self, t, foresight):
        
        if t + foresight > len(self.world.dictPFC):
            listPFC = [self.world.dictPFC[t:], self.world.dictPFC[:t+foresight-len(self.world.dictPFC)]]
        else:
            listPFC = self.world.dictPFC[t:t+foresight]
        
        # listPFC = []
        # lengthPFC = len(self.world.dictPFC)
    
        # if (t + foresight) > lengthPFC:
        #     overhang = (t + foresight) - lengthPFC
        #     for tick in range(t, lengthPFC):  # verbleibende Marktpreise in der PFC
        #         listPFC.append([int(tick), float(round(self.world.dictPFC[tick], 2))])
        #     for tick in range(0, overhang):  # Auffüllen mit Preisen vom Anfang der PFC
        #         listPFC.append([int(lengthPFC + tick), float(round(self.world.dictPFC[tick], 2))])
        # else:
        #     for tick in range(t, int(t + foresight)):
        #         listPFC.append([int(tick), float(round(self.world.dictPFC[tick], 2))])
    
        return listPFC
    
    def plotResults(self, ax=None, legend=True, **kwargs):
        ax = ax or plt.gci()
        ax.step(range(len(self.world.snapshots)), list(self.dictCapacity.values())[0:-1],'r-', label='Total Capacity')
        ax.step(range(len(self.world.snapshots)), [-_ for _ in list(self.confQtyCRM_neg.values())],'b--', label='Negative CRM')
        ax.step(range(len(self.world.snapshots)), list(self.confQtyCRM_pos.values()),'g--',  label='Positive CRM')
        
        ax.step(range(len(self.world.snapshots)), [i+j for i,j in zip(list(self.confQtyCRM_pos.values()),list(self.dictCapacity.values())[0:-1]) ],'y--',  label='Positive CRM')
        
        ax.step(range(len(self.world.snapshots)),[self.maxPower for _ in range(len(self.world.snapshots))],'r:', label='Maximum Power')
        ax.step(range(len(self.world.snapshots)),[self.minPower for _ in range(len(self.world.snapshots))],'r:', label='Minimum Power')
        ax.set_ylabel('Power [MW]')
        ax.set_title(self.name)
        if legend: ax.legend()
        return ax