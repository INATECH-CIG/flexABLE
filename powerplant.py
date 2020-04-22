# -*- coding: utf-8 -*-
"""
Created on Mon Apr  6 16:06:57 2020

@author: intgridnb-02
"""
from auxFunc import initializer
from bid import Bid
from statistics import mean

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
                Node='Bus_DE',
                world=None):

        # bids status parameters
        self.dictCapacity = {n:0 for n in self.world.snapshots}
        self.dictCapacity[-1] = self.maxPower
        self.confQtyCRM_neg = {n:0 for n in self.world.snapshots}
        self.confQtyCRM_pos = {n:0 for n in self.world.snapshots}
        self.confQtyDHM_steam = {n:0 for n in self.world.snapshots}
        self.powerLoss_CHP = {n:0 for n in self.world.snapshots}
        
        # performance parameter for ML
        self.performance = 0
        # Unit status parameters
        self.marketSuccess = [0]
        self.currentDowntime = self.minDowntime # Keeps track of the powerplant if it reached the minimum shutdown time
        self.currentStatus = 0 # 0 means the power plant is currently off, 1 means it is on
        self.averageDownTime = [0] # average downtime during the simulation
        self.currentCapacity = 0
        self.sentBids=[]
        
    def step(self):
        # Calculate the sum of confirmed bids
        self.dictCapacity[self.world.currstep] = 0
        for bid in self.sentBids:
            self.dictCapacity[self.world.currstep] += bid.confirmedAmount
        self.sentBids=[]
        # Calculates market success
        if self.dictCapacity[self.world.currstep] > 0:
            self.marketSuccess[-1] += 1
        else:
            self.marketSuccess.append(0)
        # Checks if the powerplant is shutdown and whether it can start-up
        if (self.dictCapacity[self.world.currstep] < self.minPower) and self.currentDowntime==0 and self.marketSuccess[-1]>0:
            self.currentStatus = 0
            
        if self.currentStatus == 0:
            if self.dictCapacity[self.world.currstep - 1] == 0:
                self.currentDowntime +=1
                
        if self.currentDowntime >= self.minDowntime:
            self.averageDownTime.append(self.currentDowntime)
            self.currentDowntime = 0
            self.currentStatus = 1
        
        x=5

    def feedback(self, bid):
        if bid.status == "Confirmed": 
            self.performance+=1
        elif bid.status =="PartiallyConfirmed":
            self.performance+=0.5
        else:
            self.performance-=2
        if 'steam' in bid.ID:
            self.powerLossFPP(self.world.currstep, bid)
        self.sentBids.append(bid)

    def powerLossFPP(self, t, bid):
        if bid.confirmedAmount > 0:
            if self.technology in ['lignite', 'hard coal', 'combined cycle gas turbine']:
                powerLoss = (self.maxPower - ((-0.12 * min((bid.confirmedAmount) / self.maxPower, 1.2) + 1) * self.maxPower))
                # über ein Wärme-Strom-Verhältnis von 1.2 hinaus setzt die Zusatzfeuerung ein
                self.powerLoss_CHP[t] = powerLoss

    def requestBid(self, t, market="EOM"):
        bids = []
        if market=="EOM":
            bidQuantity_mr, bidPrice_mr, bidQuantity_flex, bidPrice_flex = self.calculateBidEOM(t)
            if bidQuantity_mr != 0:
                bids.append(Bid(self,
                                "Bu{}t{}_mr".format(self.name,t),
                                bidPrice_mr,
                                bidQuantity_mr,
                                "Sent",
                                "Supply"))
                
            if bidQuantity_flex !=0:
                bids.append(Bid(self,
                                "Bu{}t{}_flex".format(self.name,t),
                                bidPrice_flex,
                                bidQuantity_flex,
                                "Sent",
                                "Supply"))
        elif market=="DHM": 
            bids.extend(self.calculateBidDHM(t))
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
        marginalCosts = round((fuelPrice / self.efficiency) + (co2price * (emissionFactor / self.efficiency)) + self.variableCosts, 2)
    
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
                (fuelPrice / (self.efficiency - etaLoss)) + (co2price * (emissionFactor / (self.efficiency - etaLoss))) + self.variableCosts, 2)
    
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
            # Calculating possible bid amount          
            # =============================================================================
            mustRunPowerFPP = (max(self.dictCapacity[t-1] - self.rampDown + self.confQtyCRM_neg[t], self.minPower + self.confQtyCRM_neg[t]))
            bidQuantity_mr = mustRunPowerFPP if mustRunPowerFPP > 0 else 0
            
            if bidQuantity_mr >= self.world.minBidEOM:
                flexPowerFPP = min(self.dictCapacity[t-1] + self.rampUp - self.confQtyCRM_pos[t] - mustRunPowerFPP,
                                   self.maxPower - self.powerLoss_CHP[t] - self.confQtyCRM_pos[t] - mustRunPowerFPP)
                bidQuantity_flex = flexPowerFPP if flexPowerFPP > 0 else 0
                
                totalOutputCapacity = mustRunPowerFPP + flexPowerFPP
            # =============================================================================
            # Calculating possible price       
            # =============================================================================
            if not(self.currentStatus):
                # The powerplant is currently off and calculates a startup markup as an extra
                # to the marginal cost
                # Calculating the average uninterrupted operating period
                averageOperatingTime = max(mean(self.marketSuccess), self.minOperatingTime, 1)

                
                if self.currentDowntime < maxDowntime_hotStart:
                    startingCosts = (self.hotStartCosts * self.maxPower)
                elif self.currentDowntime >= maxDowntime_hotStart and self.currentDowntime < maxDowntime_warmStart:
                    startingCosts = (self.warmStartCosts * self.maxPower)
                else:
                    startingCosts = (self.coldStartCosts * self.maxPower)
                
                # start-up markup   
                markup = startingCosts / averageOperatingTime / bidQuantity_mr
                
                marginalCosts_eta = self.marginalCostsFPP(t, 1, mustRunPowerFPP)
                
                bidPrice_mr = min(marginalCosts_eta + markup, 3000.12)
            else:
                '''
                Check the description provided by Thomas in last version, the average downtime is not available
                '''
                avgDT = max(self.minDowntime,1)
                
                if avgDT < maxDowntime_hotStart:
                    startingCosts = (self.hotStartCosts * self.maxPower)
                elif avgDT >= maxDowntime_hotStart and avgDT < maxDowntime_warmStart:
                    startingCosts = (self.warmStartCosts * self.maxPower)
                else:
                    startingCosts = (self.coldStartCosts * self.maxPower)
                # restart markup
                priceReduction_restart = startingCosts / avgDT / abs(bidQuantity_mr)
                
                if self.confQtyDHM_steam[t] > 0:
                    eqHeatGenCosts = (self.confQtyDHM_steam[t] * (self.world.fuelPrices[self.fuel][t]/ 0.9)) / abs(bidQuantity_mr)
                else:
                    eqHeatGenCosts = 0.00
                
                marginalCosts_eta = self.marginalCostsFPP(t, 1, totalOutputCapacity)
                
                bidPrice_mr = max(-priceReduction_restart - eqHeatGenCosts + marginalCosts_eta, -2999.00)
            
            if self.confQtyDHM_steam[t] > 0:
                powerLossRatio = round((self.powerLoss_CHP[t] / (self.confQtyDHM_steam[t])), 2)
            else:
                powerLossRatio = 0
                
            # Flex-bid price formulation
            bidPrice_flex = (1 - powerLossRatio) * self.marginalCostsFPP(t, 1, totalOutputCapacity) if abs(
                bidQuantity_flex) > 0 else 0.00
            
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
                heatExtraction_process = thPower_process * dt
    
                # Auxiliary firing on plant site
                heatExtraction_auxFiring = max(self.maxExtraction - (self.maxPower * 1.2 * dt), 0)
    
                # heat to power-ratio
                heat_to_power_ratio = heatExtraction_process / (elCapacity * dt)
    
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
                heatExtraction_process = elCapacity * 2 * dt
                heatExtraction_auxFiring = max(self.maxExtraction - (self.maxPower * 2 * dt), 0)
    
                heat_to_power_ratio = heatExtraction_process/(elCapacity * dt)
    
                powerLossRatio = -0.0000026638327514537 * (heat_to_power_ratio ** 2) \
                                 + 0.00105199966687901 * heat_to_power_ratio \
                                 + 0.108494099491879
    
            # Evaluation of heat price (EUR/MWh)
            heatPrice_process = round(powerLossRatio * self.marginalCostsFPP(t,0,0), 2)
            heatPrice_auxFiring = round(self.world.fuelPrices['natural gas'][t] / 0.9, 2)

            # Eintragen der Wärmemarktgebote
            bidsDHM.append(Bid(self,
                               "Bu{}t{}_steam".format(self.name,t),
                               heatPrice_process,
                               heatExtraction_process,
                               "Sent",
                               "Supply"))
            bidsDHM.append(Bid(self,
                               "Bu{}t{}_auxFi".format(self.name,t),
                               heatPrice_auxFiring,
                               heatExtraction_auxFiring,
                               "Sent",
                               "Supply"))
        else:
            bidsDHM.append(Bid(self,
                               "Bu{}t{}_steam".format(self.name,t),
                               0,
                               0,
                               "Sent",
                               "Supply"))
            bidsDHM.append(Bid(self,
                               "Bu{}t{}_auxFi".format(self.name,t),
                               0,
                               0,
                               "Sent",
                               "Supply"))
    
        return bidsDHM
